import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

import check_release_ready
import verify_install

SHA = "a" * 40


def workflow_run(**overrides):
    run = {"id": 2, "head_sha": SHA, "head_branch": "main", "event": "push",
           "status": "completed", "conclusion": "success",
           "html_url": "https://github.com/oceanbase/seekdb-go/actions/runs/2"}
    return {**run, **overrides}


class ReleaseGateTests(unittest.TestCase):
    def check(self, runs):
        payload = json.dumps({"workflow_runs": runs}).encode()
        with patch("urllib.request.urlopen", side_effect=lambda *args, **kwargs: io.BytesIO(payload)) as request:
            result = check_release_ready.check("git@github.com:oceanbase/seekdb-go.git", SHA)
        return result, request.call_args

    def test_requires_success_for_the_exact_main_push(self):
        for run in [workflow_run(head_sha="b" * 40), workflow_run(head_branch="feature"),
                    workflow_run(event="workflow_dispatch"), workflow_run(conclusion="failure"),
                    workflow_run(status="in_progress", conclusion=None)]:
            with self.subTest(run=run), self.assertRaises(ValueError):
                self.check([run])
        with self.assertRaises(ValueError):
            self.check([])

    def test_previous_success_does_not_hide_a_new_failed_run(self):
        with self.assertRaises(ValueError):
            self.check([workflow_run(id=1), workflow_run(id=2, conclusion="failure")])

    def test_queries_the_public_install_workflow(self):
        result, call = self.check([workflow_run()])
        self.assertTrue(result.endswith("/2"))
        url = call.args[0].full_url
        self.assertIn("/release-validation.yml/runs?", url)
        self.assertIn(f"head_sha={SHA}", url)
        self.assertEqual(call.kwargs["timeout"], 30)

    def test_public_validation_cannot_hide_failed_source_tests(self):
        failed = json.dumps({"workflow_runs": [workflow_run(conclusion="failure")]}).encode()
        with patch("urllib.request.urlopen", return_value=io.BytesIO(failed)) as request:
            with self.assertRaises(ValueError):
                check_release_ready.check("https://github.com/oceanbase/seekdb-go.git", SHA)
        self.assertIn("/test.yml/runs?", request.call_args.args[0].full_url)
        self.assertEqual(request.call_count, 1)

    def test_source_success_does_not_bypass_failed_public_validation(self):
        responses = [io.BytesIO(json.dumps({"workflow_runs": [run]}).encode())
                     for run in [workflow_run(), workflow_run(conclusion="failure")]]
        with patch("urllib.request.urlopen", side_effect=responses) as request:
            with self.assertRaises(ValueError):
                check_release_ready.check("https://github.com/oceanbase/seekdb-go.git", SHA)
        self.assertEqual(request.call_count, 2)
        self.assertIn("/release-validation.yml/runs?", request.call_args.args[0].full_url)

    def test_rejects_unexpected_remote_and_revision(self):
        for remote in ["https://example.com/oceanbase/seekdb-go", "../repository"]:
            with self.assertRaises(ValueError):
                check_release_ready.check(remote, SHA)
        with self.assertRaises(ValueError):
            check_release_ready.check("https://github.com/oceanbase/seekdb-go.git", "main")


class PublicInstallTests(unittest.TestCase):
    def test_does_not_inherit_local_workspace_or_private_proxy_bypasses(self):
        poisoned = {"GOWORK": "/source/go.work", "GOPROXY": "direct", "GOSUMDB": "off",
                    "GOPRIVATE": "*", "GONOPROXY": "*", "GONOSUMDB": "*",
                    "GOINSECURE": "*", "GOFLAGS": "-modfile=/source/local.mod"}
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory) / "consumer"
            with patch.dict(os.environ, poisoned), patch.object(verify_install, "run") as run:
                verify_install.verify(SHA, work)
            calls = run.call_args_list
            self.assertEqual(calls[0].args[0], ["go", "mod", "init", "seekdb-install-check"])
            self.assertIn(f"github.com/oceanbase/seekdb-go@{SHA}", calls[1].args[0])
            self.assertEqual(calls[2].args[0][:4], ["go", "run", "-mod=readonly", "."])
            env = calls[0].args[2]
            self.assertEqual(env["GOWORK"], "off")
            self.assertEqual(env["GOENV"], "off")
            self.assertEqual(env["GOPROXY"], "https://proxy.golang.org")
            self.assertEqual(env["GOSUMDB"], "sum.golang.org")
            for name in ["GOPRIVATE", "GONOPROXY", "GONOSUMDB", "GOINSECURE", "GOFLAGS"]:
                self.assertEqual(env[name], "")
            for name in ["GOPATH", "GOMODCACHE", "GOCACHE"]:
                self.assertEqual(Path(env[name]).parent, work)
                self.assertFalse(Path(env[name]).exists())
            self.assertTrue((work / "main.go").exists())
            self.assertTrue((work / "pipe_windows.go").exists())
            self.assertFalse((work / "go.work").exists())

    def test_refuses_a_reused_work_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            (work / "go.mod").write_text("module an-existing-project\n")
            with patch.object(verify_install, "run") as run, self.assertRaises(ValueError):
                verify_install.verify(SHA, work)
            run.assert_not_called()

    def test_failed_download_cannot_proceed_to_a_local_build(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory) / "consumer"
            with patch.object(verify_install, "run", side_effect=[
                    None, subprocess.CalledProcessError(1, ["go", "get"])]) as run:
                with self.assertRaises(subprocess.CalledProcessError):
                    verify_install.verify(SHA, work)
            self.assertEqual(run.call_count, 2)
            self.assertTrue(work.exists())


class ReleaseScriptTests(unittest.TestCase):
    def exercise(self, scenario):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "scripts").mkdir()
            (root / "inputs").mkdir()
            (root / "bin").mkdir()
            script = root / "scripts/release.sh"
            script.write_text((SCRIPTS / "release.sh").read_text())
            # Exercise the real shell control flow without publishing anything.
            stub = """#!/usr/bin/env python3
import json, os, pathlib, sys
tool = pathlib.Path(sys.argv[0]).name
args = sys.argv[1:]
root = pathlib.Path(os.environ['FIXTURE'])
scenario = os.environ['SCENARIO']
with (root/'calls.jsonl').open('a') as out: out.write(json.dumps([tool, *args])+'\\n')
sha = 'a'*40
if tool == 'git':
    if args[:2] == ['branch','--show-current']: print('main')
    elif args[:2] == ['status','--porcelain']:
        if len(args)>2 and scenario=='dependencies-changed': print(' M go.sum')
    elif args[:1] == ['ls-remote']:
        print(('b'*40 if scenario=='stale-main' else sha)+'\\trefs/heads/main')
    elif args[:2] == ['rev-parse','HEAD']: print(sha)
    elif args[:1] == ['rev-parse']: sys.exit(1)
    elif args[:3] == ['remote','get-url','origin']: print('https://github.com/oceanbase/seekdb-go.git')
elif tool == 'go' and args == ['list','-m']: print('github.com/oceanbase/seekdb-go')
elif tool == 'python3' and 'check_release_ready.py' in args[0] and scenario=='validation-failed':
    sys.exit(1)
"""
            for tool in ["git", "go", "python3"]:
                path = root / "bin" / tool
                # Use the real interpreter so the python3 stub never recurses.
                path.write_text(stub.replace("#!/usr/bin/env python3", f"#!{sys.executable}"))
                path.chmod(0o755)
            env = {**os.environ, "PATH": f"{root / 'bin'}{os.pathsep}{os.environ['PATH']}",
                   "FIXTURE": str(root), "SCENARIO": scenario}
            result = subprocess.run(["bash", str(script), "v1.4.0", "v1.4.0", str(root / "inputs")],
                                    env=env, text=True, capture_output=True)
            calls = [json.loads(line) for line in (root / "calls.jsonl").read_text().splitlines()]
            return result, calls

    def test_stale_main_cannot_push_any_tags(self):
        result, calls = self.exercise("stale-main")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any(call[:2] == ["git", "push"] for call in calls))

    def test_changed_dependencies_stop_before_root_publication(self):
        result, calls = self.exercise("dependencies-changed")
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(any(call[:2] == ["git", "push"] for call in calls))
        self.assertNotIn(["git", "tag", "v1.4.0"], calls)

    def test_failed_public_validation_cannot_publish_root(self):
        result, calls = self.exercise("validation-failed")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn(["git", "tag", "v1.4.0"], calls)
        self.assertNotIn(["git", "push", "origin", "refs/tags/v1.4.0"], calls)

    def test_checks_exact_commit_before_root_publication(self):
        result, calls = self.exercise("ready")
        self.assertEqual(result.returncode, 0, result.stderr)
        gate = ["python3", "scripts/check_release_ready.py",
                "https://github.com/oceanbase/seekdb-go.git", SHA]
        self.assertLess(calls.index(gate), calls.index(["git", "tag", "v1.4.0"]))
        self.assertIn(["git", "push", "origin", "refs/tags/v1.4.0"], calls)


if __name__ == "__main__":
    unittest.main()
