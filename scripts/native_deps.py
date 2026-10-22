"""Collect and validate the native dependencies of a seekdb Go bundle.

Run on the target platform: ldd resolves Linux libraries, and otool resolves
macOS install names. The release input binaries are trusted build artifacts.
"""

from __future__ import annotations

import filecmp
import os
import re
import shutil
import subprocess
from collections import deque
from pathlib import Path


def run(*args: str, env: dict[str, str] | None = None) -> str:
    return subprocess.run(args, env=env, check=True, text=True, capture_output=True).stdout


def libraries(stage: Path) -> list[Path]:
    return sorted(path for path in stage.iterdir() if path.is_file())


def copy_dependency(source: Path, stage: Path) -> tuple[Path, bool]:
    target = stage / source.name
    if target.exists():
        if not filecmp.cmp(source, target, shallow=False):
            raise ValueError(f"different libraries share the name {source.name}: {source} and {target}")
        return target, False
    shutil.copy2(source, target)
    return target, True


GLIBC_NAMES = re.compile(
    r"^(?:linux-vdso\.so|ld-linux.*\.so|ld64.*\.so|libc\.so|libm\.so|"
    r"libdl\.so|libpthread\.so|librt\.so|libresolv\.so|libutil\.so|"
    r"libanl\.so|libBrokenLocale\.so|libnss_.*\.so|libthread_db\.so)(?:\.|$)"
)


def is_glibc(name: str) -> bool:
    return bool(GLIBC_NAMES.match(name))


def linux_dependencies(path: Path, search: list[Path]) -> list[tuple[str, Path]]:
    env = os.environ.copy()
    env["LD_LIBRARY_PATH"] = os.pathsep.join(map(str, search))
    output = run("ldd", str(path), env=env)
    found = []
    for line in output.splitlines():
        fields = line.strip().split()
        if not fields:
            continue
        if len(fields) >= 3 and fields[1] == "=>":
            if fields[2] == "not":
                raise ValueError(f"{path} has an unresolved dependency: {fields[0]}")
            if fields[2].startswith("/"):
                found.append((fields[0], Path(fields[2])))
        elif fields[0].startswith("/"):
            found.append((Path(fields[0]).name, Path(fields[0])))
    return found


def verify_linux(stage: Path) -> None:
    for path in libraries(stage):
        rpath = run("patchelf", "--print-rpath", str(path)).strip().split(":")
        if "$ORIGIN" not in rpath:
            raise ValueError(f"{path} must have a $ORIGIN runtime search path")
        for name, resolved in linux_dependencies(path, [stage]):
            if not is_glibc(name) and resolved.resolve().parent != stage.resolve():
                raise ValueError(f"{name} required by {path} resolves outside the bundle: {resolved}")


def verify_linux_static(stage: Path) -> None:
    """Check an already bundled ELF runtime without executing target binaries."""
    for path in libraries(stage):
        rpath = run("patchelf", "--print-rpath", str(path)).strip().split(":")
        if "$ORIGIN" not in rpath:
            raise ValueError(f"{path} must have a $ORIGIN runtime search path")
        for name in run("patchelf", "--print-needed", str(path)).splitlines():
            if not is_glibc(name) and not (stage / name).is_file():
                raise ValueError(f"{name} required by {path} is missing from the bundle")


def collect_linux(stage: Path, search: list[Path]) -> None:
    queue = deque([stage / "seekdb", stage / "libseekdb.so"])
    while queue:
        path = queue.popleft()
        for name, resolved in linux_dependencies(path, [stage, *search]):
            if is_glibc(name):
                continue
            target, created = copy_dependency(resolved, stage)
            if created:
                print(f"collected {target.name} from {resolved}")
                queue.append(target)
    for path in libraries(stage):
        if run("patchelf", "--print-rpath", str(path)).strip() != "$ORIGIN":
            run("patchelf", "--set-rpath", "$ORIGIN", str(path))
    verify_linux(stage)
    for path in libraries(stage):
        output = run("objdump", "-T", str(path))
        versions = [tuple(map(int, match.split("."))) for match in re.findall(r"GLIBC_(\d+(?:\.\d+)+)", output)]
        if versions and max(versions) > (2, 28):
            raise ValueError(f"{path} requires GLIBC_{'.'.join(map(str, max(versions)))}, above the 2.28 baseline")


def mac_dependencies(path: Path) -> list[str]:
    return [line.strip().split(" (")[0] for line in run("otool", "-L", str(path)).splitlines()[1:]]


def mac_rpaths(path: Path) -> list[str]:
    lines = run("otool", "-l", str(path)).splitlines()
    return [lines[i + 2].strip().split()[1] for i, line in enumerate(lines[:-2])
            if line.strip() == "cmd LC_RPATH" and lines[i + 2].strip().startswith("path ")]


def mac_system(name: str) -> bool:
    return name.startswith(("/usr/lib/", "/System/Library/"))


def resolve_mac(name: str, origin: Path, executable: Path, search: list[Path]) -> Path:
    candidates = []
    if name.startswith("@loader_path/"):
        candidates.append(origin.parent / name[len("@loader_path/"):])
    elif name.startswith("@executable_path/"):
        candidates.append(executable.parent / name[len("@executable_path/"):])
    elif name.startswith("@rpath/"):
        suffix = name[len("@rpath/"):]
        for rpath in mac_rpaths(origin):
            rpath = rpath.replace("@loader_path", str(origin.parent)).replace("@executable_path", str(executable.parent))
            candidates.append(Path(rpath) / suffix)
    elif name.startswith("/"):
        candidates.append(Path(name))
    candidates.extend(directory / Path(name).name for directory in [origin.parent, *search])
    for candidate in candidates:
        if candidate.is_file():
            # Keep the install-name basename when the candidate is a symlink.
            return candidate.absolute()
    raise ValueError(f"cannot resolve {name} required by {origin}; add its directory with --library-dir")


def verify_mac(stage: Path) -> None:
    for path in libraries(stage):
        if "arm64" not in run("lipo", "-archs", str(path)).split():
            raise ValueError(f"{path} does not contain arm64")
        for name in mac_dependencies(path):
            if mac_system(name) or Path(name).name == path.name:
                continue
            if not name.startswith("@loader_path/") or not (stage / name[len("@loader_path/"):]).is_file():
                raise ValueError(f"{path} references an unbundled dependency: {name}")


def collect_mac(stage: Path, support: Path, executable: Path, search: list[Path]) -> None:
    queue = deque([(stage / "seekdb", executable), (stage / "libseekdb.dylib", support / "libseekdb.dylib")])
    while queue:
        target, source = queue.popleft()
        for name in mac_dependencies(source):
            if mac_system(name) or Path(name).name == source.name:
                continue
            resolved = resolve_mac(name, source, executable, [support, *search])
            dependency, created = copy_dependency(resolved, stage)
            if created:
                print(f"collected {dependency.name} from {resolved}")
                queue.append((dependency, resolved))
    for path in libraries(stage):
        changed = False
        for name in mac_dependencies(path):
            if mac_system(name) or Path(name).name == path.name:
                continue
            replacement = f"@loader_path/{Path(name).name}"
            if name != replacement:
                run("install_name_tool", "-change", name, replacement, str(path))
                changed = True
        if path.suffix == ".dylib":
            current_id = mac_dependencies(path)[0]
            replacement_id = f"@loader_path/{path.name}"
            if current_id != replacement_id:
                run("install_name_tool", "-id", replacement_id, str(path))
                changed = True
        if changed:
            run("codesign", "--force", "--sign", "-", "--timestamp=none", str(path))
    verify_mac(stage)
