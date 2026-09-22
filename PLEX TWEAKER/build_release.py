"""Build a hardened, distributable Vellium Tweaker executable with Nuitka.

PyInstaller is intentionally not used here: it packages importable Python
bytecode, which public extractors can recover. Nuitka translates first-party
modules to C and then native machine code. This raises the reverse-engineering
cost substantially while keeping the app as a single Windows executable.

No desktop program can make client-side logic impossible to reverse engineer.
Secrets and privileged decisions must live on a server, never in this binary.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist-release"
REPORT = ROOT / "build-release-report.xml"


def _require_nuitka() -> None:
    try:
        import nuitka  # noqa: F401
    except ImportError as exc:
        raise SystemExit(
            "Nuitka is required for release builds. Install build dependencies with:\n"
            f'  "{sys.executable}" -m pip install -r requirements-build.txt'
        ) from exc


def _clean_output() -> Path:
    # Keep debug build/dist untouched. Release output has its own narrow paths.
    # A running onefile executable is locked on Windows. Try successive
    # release folders instead of terminating any user-owned app instance.
    output_dir = None
    candidates = [DIST, ROOT / "dist-release-next"] + [
        ROOT / f"dist-release-next-{index}" for index in range(2, 20)
    ]
    for candidate in candidates:
        try:
            if candidate.exists():
                shutil.rmtree(candidate)
            output_dir = candidate
            break
        except PermissionError:
            continue
    if output_dir is None:
        raise RuntimeError("No unlocked release output folder is available")

    for path in (ROOT / "main.build", ROOT / "main.dist", ROOT / "main.onefile-build"):
        if path.exists():
            shutil.rmtree(path)
    if REPORT.exists():
        REPORT.unlink()
    return output_dir


def build() -> Path:
    os.chdir(ROOT)
    _require_nuitka()
    output_dir = _clean_output()
    output_dir.mkdir(parents=True, exist_ok=True)

    icon = ROOT / "meow-ware-icon.ico"
    if not icon.is_file():
        raise SystemExit(f"Missing Windows icon: {icon}")

    cmd = [
        sys.executable,
        "-m", "nuitka",
        "--mode=onefile",
        "--assume-yes-for-downloads",
        "--windows-console-mode=disable",
        f"--windows-icon-from-ico={icon}",
        "--output-filename=VelliumTweaker.exe",
        f"--output-dir={output_dir}",
        f"--report={REPORT}",
        "--include-package=src",
        "--include-package=pystray",
        "--include-package=roblox",
        "--include-package=pythonnet",
        "--include-package=clr_loader",
        "--include-package-data=pythonnet",
        "--include-data-dir=src/gui/ui=src/gui/ui",
        "--include-data-dir=src/data=src/data",
        "--include-data-files=version.json=version.json",
        "--include-data-files=meow-ware-icon.png=meow-ware-icon.png",
        "--nofollow-import-to=pytest",
        "--nofollow-import-to=unittest",
        "--nofollow-import-to=tkinter",
        "main.pyw",
    ]
    print("[*] Building native release with Nuitka...")
    subprocess.check_call(cmd)

    exe = output_dir / "VelliumTweaker.exe"
    if not exe.is_file():
        raise SystemExit(f"Release compiler completed but {exe} was not produced")

    subprocess.check_call([sys.executable, "scripts/audit_release.py", str(exe), str(REPORT)])
    print(f"[+] Hardened release ready: {exe}")
    return exe


if __name__ == "__main__":
    build()
