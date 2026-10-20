"""
Clean Distribution Packaging Tool for OpenCampus OSS.

Produces a sanitized source distribution archive (.zip) containing only
necessary production source code and configuration.

Guarantees:
- Strictly excludes virtual environments (venv/)
- Strictly excludes compiled bytecode (__pycache__/, *.pyc)
- Strictly excludes VCS internals (.git/)
- Strictly excludes local databases and crash logs (instance/)
- Strictly excludes temporary/debug scratchpads (*_debug.txt, temp_*.txt)

Usage:
    python scripts/package_dist.py [--format zip|tar.gz] [--output-dir dist]
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
import zipfile
import tarfile
from pathlib import Path

# Paths to strictly omit from any release bundle
EXCLUDED_PATTERNS = [
    r"^venv(/|\\|$)",
    r"^\.venv(/|\\|$)",
    r"^\.git(/|\\|$)",
    r"__pycache__",
    r"\.py[cod]$",
    r"^instance(/|\\|$)",
    r"^dist(/|\\|$)",
    r"^build(/|\\|$)",
    r"\.egg-info",
    r"\.pytest_cache",
    r"\.coverage",
    r"^\.vscode(/|\\|$)",
    r"^\.idea(/|\\|$)",
    r"crash_reports",
    r"\.db(-wal|-shm)?$",
    r"dead_letter_queue\.jsonl$",
    r"_debug\.txt$",
    r"temp_.*\.txt$",
    r"\.tmp$",
    r"\.bak$",
]

EXCLUDED_REGEXES = [re.compile(p, re.IGNORECASE) for p in EXCLUDED_PATTERNS]


def is_excluded(rel_path: str) -> bool:
    normalized = rel_path.replace("\\", "/")
    return any(rx.search(normalized) for rx in EXCLUDED_REGEXES)


def calculate_sha256(filepath: Path) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def create_clean_archive(project_root: Path, output_dir: Path, archive_name: str, fmt: str = "zip") -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    out_file = output_dir / f"{archive_name}.{fmt}"

    included_files: list[tuple[Path, str]] = []

    for root, dirs, files in os.walk(project_root):
        rel_dir = os.path.relpath(root, project_root)
        if rel_dir == ".":
            rel_dir = ""

        # Skip entire excluded directories in-place to avoid unnecessary traversal
        dirs[:] = [d for d in dirs if not is_excluded(os.path.join(rel_dir, d))]

        for file in files:
            rel_path = os.path.join(rel_dir, file)
            if not is_excluded(rel_path):
                included_files.append((Path(root) / file, rel_path.replace("\\", "/")))

    # Write out archive
    if fmt == "zip":
        with zipfile.ZipFile(out_file, "w", zipfile.ZIP_DEFLATED) as zf:
            for abs_path, arc_path in sorted(included_files, key=lambda x: x[1]):
                zf.write(abs_path, arcname=f"{archive_name}/{arc_path}")
    else:
        with tarfile.open(out_file, "w:gz") as tf:
            for abs_path, arc_path in sorted(included_files, key=lambda x: x[1]):
                tf.add(abs_path, arcname=f"{archive_name}/{arc_path}")

    return out_file


def audit_archive(archive_path: Path) -> list[str]:
    """Inspect the generated archive and flag any prohibited leakage."""
    violations = []
    if archive_path.suffix == ".zip":
        with zipfile.ZipFile(archive_path, "r") as zf:
            names = zf.namelist()
    else:
        with tarfile.open(archive_path, "r:gz") as tf:
            names = tf.getnames()

    for name in names:
        # Strip top-level directory prefix for relative path check
        parts = name.split("/", 1)
        rel = parts[1] if len(parts) > 1 else parts[0]
        if is_excluded(rel):
            violations.append(name)
    return violations


def main():
    parser = argparse.ArgumentParser(description="Package OpenCampus OSS clean source distribution")
    parser.add_argument("--format", choices=["zip", "tar.gz"], default="zip", help="Archive format")
    parser.add_argument("--version", default="2.0.0", help="Release version tag")
    parser.add_argument("--output-dir", default="dist", help="Output directory")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    output_dir = project_root / args.output_dir
    archive_name = f"opencampus-oss-v{args.version}"

    print(f"Packaging clean source distribution for OpenCampus OSS v{args.version}...")
    archive_path = create_clean_archive(project_root, output_dir, archive_name, fmt=args.format)

    # Run audit check
    leaks = audit_archive(archive_path)
    if leaks:
        print(f"\n[ERROR] Archive audit FAILED! Prohibited files detected:")
        for leak in leaks:
            print(f"  - {leak}")
        archive_path.unlink(missing_ok=True)
        sys.exit(1)

    size_kb = archive_path.stat().st_size / 1024
    checksum = calculate_sha256(archive_path)

    print("\nPackage generated successfully and verified clean:")
    print(f"  File:      {archive_path}")
    print(f"  Size:      {size_kb:.1f} KB")
    print(f"  SHA-256:   {checksum}")
    print("  Integrity: 0 bytecode, 0 venv, 0 vcs, 0 local db leaks.\n")


if __name__ == "__main__":
    main()
