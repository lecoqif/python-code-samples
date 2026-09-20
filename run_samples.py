"""Run the library patches and standalone sample tests."""

from __future__ import annotations

import argparse
import importlib.metadata
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SAMPLES = json.loads((ROOT / "samples.json").read_text())
STANDALONE_TESTS = {
    "graph_crawler": "concurrency/test_graph_crawler.py",
    "bounded_map": "concurrency/test_bounded_map.py",
    "tokenizer": "tokenization/test_tokenizer.py",
    "replicated_reader": "replicated_reader/test_reader.py",
}
SAMPLE_NAMES = [*SAMPLES, *STANDALONE_TESTS]


def run_tests(test: Path, *, cwd: Path, env: dict[str, str]) -> int:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-c",
            str(ROOT / "pyproject.toml"),
            "--confcutdir",
            str(ROOT),
            str(test),
        ],
        cwd=cwd,
        env=env,
        check=False,
    ).returncode


def run_sample(name: str) -> int:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    if name in STANDALONE_TESTS:
        env["PYTHONPATH"] = str(ROOT)
        print(f"\n{name} — Python standard library", flush=True)
        return run_tests(ROOT / STANDALONE_TESTS[name], cwd=ROOT, env=env)

    spec = SAMPLES[name]
    installed = importlib.metadata.version(spec["distribution"])
    if installed != spec["version"]:
        raise RuntimeError(
            f"{name}: needs {spec['distribution']}=={spec['version']}, "
            f"found {installed}. Install requirements.txt in a virtual environment."
        )
    module = importlib.util.find_spec(spec["module"])
    if module is None or module.origin is None:
        raise RuntimeError(f"Cannot locate installed package {spec['module']}")

    runs = ROOT / ".runs"
    runs.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f"{name}-", dir=runs) as directory:
        checkout = Path(directory)
        pythonpath = checkout / spec["pythonpath"]
        package = pythonpath / spec["module"]
        shutil.copytree(
            Path(module.origin).parent,
            package,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        # Give git apply its own root even when this runner lives in a Git repo.
        subprocess.run(["git", "init", "-q", str(checkout)], check=True)
        # Wheels omit upstream documentation. Apply runtime hunks only; the
        # complete patch can also be applied to the pinned source repository.
        includes = [
            f"--include={path}"
            for path in spec["files"]
            if path.endswith((".py", ".pyi"))
        ]
        patch = str(ROOT / spec["patch"])
        subprocess.run(
            ["git", "apply", "--check", *includes, patch], cwd=checkout, check=True
        )
        subprocess.run(["git", "apply", *includes, patch], cwd=checkout, check=True)

        env["PYTHONPATH"] = str(pythonpath)
        # Verify the import location so an unpatched wheel cannot pass tests.
        subprocess.run(
            [
                sys.executable,
                "-c",
                "import importlib, pathlib, sys; "
                "p = pathlib.Path(importlib.import_module(sys.argv[1]).__file__); "
                "assert p.resolve().is_relative_to(pathlib.Path(sys.argv[2]).resolve()), p",
                spec["module"],
                str(package),
            ],
            cwd=checkout,
            env=env,
            check=True,
        )
        print(f"\n{name} — {spec['distribution']} {installed}", flush=True)
        return run_tests(ROOT / spec["test"], cwd=checkout, env=env)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "sample", choices=["all", *SAMPLE_NAMES], default="all", nargs="?"
    )
    args = parser.parse_args()
    names = SAMPLE_NAMES if args.sample == "all" else [args.sample]
    results = {name: run_sample(name) for name in names}
    print(
        "\n"
        + ", ".join(
            f"{name}: {'PASS' if code == 0 else 'FAIL'}"
            for name, code in results.items()
        )
    )
    return int(any(results.values()))


if __name__ == "__main__":
    raise SystemExit(main())
