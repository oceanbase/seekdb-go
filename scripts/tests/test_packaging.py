import hashlib
import io
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

import native_deps
import verify_bundles


class MacArchitectureTests(unittest.TestCase):
    def test_every_runtime_file_requires_arm64(self):
        for wrong in ["seekdb", "libseekdb.dylib", "libdependency.dylib"]:
            with self.subTest(wrong=wrong), tempfile.TemporaryDirectory() as directory:
                stage = Path(directory)
                for name in ["seekdb", "libseekdb.dylib", "libdependency.dylib"]:
                    (stage / name).touch()

                def inspect(*args):
                    if args[0] == "lipo":
                        return "x86_64" if Path(args[-1]).name == wrong else "arm64"
                    return f"{args[-1]}:\n"

                with patch.object(native_deps, "run", side_effect=inspect):
                    with self.assertRaisesRegex(ValueError, f"{wrong} does not contain arm64"):
                        native_deps.verify_mac(stage)


@unittest.skipUnless(sys.platform == "darwin", "requires macOS clang, lipo and otool")
class MacPackagingCommandsTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.stage = self.root / "inputs" / "darwin-arm64"
        self.stage.mkdir(parents=True)
        self.source = self.root / "fixture.c"
        self.source.write_text("int main(void) { return 0; }\n")

    def compile(self, name, arch):
        command = ["clang", "-arch", arch, str(self.source), "-o", str(self.stage / name)]
        if name.endswith(".dylib"):
            command.append("-dynamiclib")
        subprocess.run(command, check=True, capture_output=True)

    def package(self):
        return subprocess.run([sys.executable, str(SCRIPTS / "package_native.py"),
                               "darwin-arm64", str(self.stage), str(self.root / "bundle.tar.gz")],
                              text=True, capture_output=True)

    def test_direct_packager_rejects_real_x86_64_files(self):
        for wrong in ["seekdb", "libseekdb.dylib", "libdependency.dylib"]:
            with self.subTest(wrong=wrong):
                for name in ["seekdb", "libseekdb.dylib", "libdependency.dylib"]:
                    self.compile(name, "x86_64" if name == wrong else "arm64")
                result = self.package()
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertIn(f"{wrong} does not contain arm64", result.stderr)
                self.assertFalse((self.root / "bundle.tar.gz").exists())

    def test_arm64_and_universal_inputs_are_accepted(self):
        self.compile("seekdb", "arm64")
        self.compile("libseekdb.dylib", "arm64")
        self.compile("libdependency.dylib", "x86_64")
        x86 = self.root / "x86.dylib"
        (self.stage / "libdependency.dylib").rename(x86)
        self.compile("libdependency.dylib", "arm64")
        subprocess.run(["lipo", "-create", str(x86), str(self.stage / "libdependency.dylib"),
                        "-output", str(self.stage / "libdependency.dylib")], check=True, capture_output=True)
        result = self.package()
        self.assertEqual(result.returncode, 0, result.stderr)
        with tarfile.open(self.root / "bundle.tar.gz") as archive:
            self.assertEqual(set(archive.getnames()),
                             {"seekdb", "seekdb.bin", "libseekdb.dylib", "libdependency.dylib"})

    def test_release_input_check_rejects_matching_wrong_architecture(self):
        self.compile("seekdb", "x86_64")
        self.compile("libseekdb.dylib", "arm64")
        # A matching checksum and matching archive bytes must not bypass the
        # architecture check on the supplied release inputs.
        destination = self.root / "native" / "darwin-arm64" / "bundle.tar.gz"
        destination.parent.mkdir(parents=True)
        with tarfile.open(destination, "w:gz") as archive:
            for name, contents in {
                "seekdb": b"#!/bin/sh\n",
                "seekdb.bin": (self.stage / "seekdb").read_bytes(),
                "libseekdb.dylib": (self.stage / "libseekdb.dylib").read_bytes(),
            }.items():
                entry = tarfile.TarInfo(name)
                entry.size = len(contents)
                archive.addfile(entry, io.BytesIO(contents))
        checksum = hashlib.sha256(destination.read_bytes()).hexdigest()
        readme = f"| macOS arm64 bundle | `{checksum}` |\n"
        with patch.object(verify_bundles, "ROOT", self.root):
            with self.assertRaisesRegex(ValueError, "seekdb does not contain arm64"):
                verify_bundles.verify("darwin-arm64", readme, self.root / "inputs")


if __name__ == "__main__":
    unittest.main()
