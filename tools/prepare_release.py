"""Create a clean ClipGen release folder and zip from the local build output."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from clipgen import __version__  # noqa: E402
from tools.check_release_artifacts import check_release_dir  # noqa: E402


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _copy_lang(source: Path, target: Path) -> None:
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target)


def prepare_release(output_root: Path) -> Path:
    dist = ROOT / "dist"
    exe = dist / "ClipGen.exe"
    if not exe.exists():
        raise FileNotFoundError("dist/ClipGen.exe is missing; run PyInstaller first")

    lang_source = dist / "lang"
    if not lang_source.exists():
        lang_source = ROOT / "lang"
    if not lang_source.exists():
        raise FileNotFoundError("lang directory is missing")

    stamp = time.strftime("%Y%m%d-%H%M%S")
    release_name = f"ClipGen-{__version__}-{stamp}"
    release_dir = output_root / release_name
    release_dir.mkdir(parents=True, exist_ok=False)

    shutil.copy2(exe, release_dir / "ClipGen.exe")
    _copy_lang(lang_source, release_dir / "lang")

    problems = check_release_dir(release_dir)
    if problems:
        shutil.rmtree(release_dir, ignore_errors=True)
        joined = "\n".join(f"- {problem}" for problem in problems)
        raise RuntimeError(f"release artifact check failed:\n{joined}")

    zip_base = output_root / release_name
    zip_path = Path(shutil.make_archive(str(zip_base), "zip", release_dir))
    checksums = {
        "ClipGen.exe": _sha256(release_dir / "ClipGen.exe"),
        zip_path.name: _sha256(zip_path),
    }
    checksum_path = output_root / f"{release_name}.sha256.json"
    checksum_path.write_text(
        json.dumps(checksums, ensure_ascii=False, indent=4) + "\n",
        encoding="utf-8",
    )

    return release_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare a clean ClipGen release package.")
    parser.add_argument(
        "--output",
        default=str(ROOT / "release"),
        help="Output directory for release folders and zip files.",
    )
    args = parser.parse_args(argv)

    release_dir = prepare_release(Path(args.output).resolve())
    print(f"Release prepared: {release_dir}")
    print(f"Zip: {release_dir}.zip")
    print(f"SHA256: {release_dir}.sha256.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
