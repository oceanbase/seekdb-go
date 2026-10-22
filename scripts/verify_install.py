#!/usr/bin/env python3
"""Test a public module revision as a new user, outside the source workspace."""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE = "github.com/oceanbase/seekdb-go"


def public_environment(work: Path) -> dict[str, str]:
    env = os.environ.copy()
    env.update({
        "GOENV": "off", "GOWORK": "off", "GO111MODULE": "on", "GOFLAGS": "",
        "GOPROXY": "https://proxy.golang.org", "GOSUMDB": "sum.golang.org",
        "GOPRIVATE": "", "GONOPROXY": "", "GONOSUMDB": "", "GOINSECURE": "",
        "GOTOOLCHAIN": "local", "CGO_ENABLED": "1",
        "GOPATH": str(work / "gopath"), "GOMODCACHE": str(work / "modules"),
        "GOCACHE": str(work / "build"),
    })
    return env


def run(command: list[str], work: Path, env: dict[str, str]) -> None:
    description = json.dumps(command)
    print(f"Running {description}", flush=True)
    result = subprocess.run(command, cwd=work, env=env, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    with (work / "install.log").open("a", encoding="utf-8") as log:
        log.write(f"$ {description}\n{result.stdout}\n")
    print(result.stdout, end="", flush=True)
    result.check_returncode()


def verify(revision: str, work: Path) -> None:
    if not revision or revision.startswith("-") or any(c.isspace() for c in revision):
        raise ValueError("revision must be a Go version, commit, or latest")
    work.mkdir(parents=True, exist_ok=True)
    if any(work.iterdir()):
        raise ValueError(f"installation work directory must be empty: {work}")
    for source in (ROOT / "examples/sql").glob("*.go"):
        shutil.copy2(source, work / source.name)
    env = public_environment(work)
    run(["go", "mod", "init", "seekdb-install-check"], work, env)
    run(["go", "get", f"{MODULE}@{revision}",
         "github.com/go-sql-driver/mysql@v1.9.3",
         "github.com/Microsoft/go-winio@v0.6.2"], work, env)
    env["SEEKDB_TEST_ARTIFACT_DIR"] = str(work / "diagnostics")
    run(["go", "test", "-mod=readonly", "-v", "-count=1", "-timeout=10m", "."], work, env)
    run(["go", "run", "-mod=readonly", ".", "-db", str(work / "database")], work, env)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("revision", help="root module version, full commit SHA, or latest")
    parser.add_argument("--work-dir", type=Path, help="empty directory; retained for CI artifacts")
    args = parser.parse_args()
    work = (args.work_dir or Path(tempfile.mkdtemp(prefix="seekdb-install-"))).resolve()
    try:
        verify(args.revision, work)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"Public install failed: {error}\nDiagnostics retained at {work}", file=sys.stderr)
        return 1
    print(f"Public installation and SQL persistence passed: {args.revision}")
    if args.work_dir is None:
        shutil.rmtree(work)
    return 0


if __name__ == "__main__":
    sys.exit(main())
