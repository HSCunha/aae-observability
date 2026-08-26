"""Fail-fast checks for aae-observability release artifacts."""

from __future__ import annotations

import argparse
import re
import sys
import tarfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION_FILE = ROOT / "src" / "aae_observability" / "_version.py"
PYPROJECT = ROOT / "pyproject.toml"


def version_from(path: Path) -> str:
    match = re.search(r'(?m)^(?:__version__|version)\s*=\s*"([^"]+)"', path.read_text())
    if match is None:
        raise ValueError(f"version not found in {path}")
    return match.group(1)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", help="Expected release tag, for example v0.6.3")
    args = parser.parse_args()

    project_version = version_from(PYPROJECT)
    runtime_version = version_from(VERSION_FILE)
    if project_version != runtime_version:
        raise SystemExit(
            f"version mismatch: pyproject={project_version}, runtime={runtime_version}"
        )
    if args.tag and args.tag != f"v{project_version}":
        raise SystemExit(f"tag {args.tag!r} does not match v{project_version}")

    wheel = ROOT / "dist" / f"aae_observability-{project_version}-py3-none-any.whl"
    sdist = ROOT / "dist" / f"aae_observability-{project_version}.tar.gz"
    if not wheel.is_file() or not sdist.is_file():
        raise SystemExit("expected wheel and sdist are missing")

    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        if not any(name.endswith("aae_observability/__init__.py") for name in names):
            raise SystemExit("wheel does not contain the import package")
        forbidden = [name for name in names if "/tests/" in name or name.startswith("tests/")]
        if forbidden:
            raise SystemExit("wheel unexpectedly contains tests")

    with tarfile.open(sdist, "r:gz") as archive:
        names = archive.getnames()
        required = ("README.md", "LICENSE", "RELEASE.md", "MIGRATION.md")
        for filename in required:
            if not any(name.endswith(f"/{filename}") for name in names):
                raise SystemExit(f"sdist is missing {filename}")

    print(f"release artifacts validated for {project_version}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
