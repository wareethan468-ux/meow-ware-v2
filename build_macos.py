"""Build the native macOS Vellium Tweaker application bundle."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys


def build():
    if sys.platform != "darwin":
        raise SystemExit("macOS builds must be created on macOS; PyInstaller cannot cross-compile .app bundles.")

    root = os.path.dirname(os.path.abspath(__file__))
    os.chdir(root)
    if not shutil.which("npm"):
        raise SystemExit("Node.js/npm is required to compile the React interface.")
    subprocess.check_call(["npm", "ci"])
    subprocess.check_call(["npm", "run", "build"])
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt", "pyinstaller"])
    for folder in ("build-macos", "dist-macos"):
        if os.path.isdir(folder):
            shutil.rmtree(folder)

    separator = ":"
    subprocess.check_call([
        sys.executable, "-m", "PyInstaller", "--windowed", "--onedir",
        "--noconfirm", "--clean", "--name=Vellium Tweaker",
        "--distpath=dist-macos", "--workpath=build-macos",
        f"--add-data=src/gui/ui{separator}src/gui/ui",
        f"--add-data=version.json{separator}.",
        f"--add-data=src/data{separator}src/data",
        f"--add-data=meow-ware-icon.png{separator}.",
        f"--add-data=vellium-icon.png{separator}.",
        "main.pyw",
    ])
    print(os.path.abspath("dist-macos/Vellium Tweaker.app"))


if __name__ == "__main__":
    build()
