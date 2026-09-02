import os
import subprocess
import sys
import shutil


def _use_stable_builder():
    """Re-launch under Python 3.13 when invoked from a newer interpreter.

    The Windows desktop stack used by this project (pywebview/pythonnet) is
    not release-safe when frozen from Python 3.14 yet.  Those builds can fail
    in the native .NET host before our Python entry point is reached and show
    the misleading "Platform not supported" dialog.
    """
    if sys.version_info[:2] <= (3, 13):
        return False

    launcher = shutil.which('py')
    if not launcher:
        raise RuntimeError(
            'Python 3.13 x64 is required to build VelliumTweaker.exe. '
            'Install it, then run: py -3.13 build_exe.py'
        )

    probe = subprocess.run(
        [launcher, '-3.13', '-c', 'import sys; print(sys.executable)'],
        capture_output=True,
        text=True,
    )
    if probe.returncode != 0:
        raise RuntimeError(
            'Python 3.13 x64 is required to build VelliumTweaker.exe. '
            'Install it, then run: py -3.13 build_exe.py'
        )

    print(f'[*] Re-launching stable build with {probe.stdout.strip()}')
    subprocess.check_call([launcher, '-3.13', os.path.abspath(__file__)])
    return True


def build():
    if _use_stable_builder():
        return

    print("[*] Starting Vellium Tweaker build...")
    print("[!] NOTE: this produces an UNSEALED debug build. For a shippable")
    print("[!]       release, use `..\\release.ps1` from the project root")
    print("[!]       instead. That path compiles first-party Python to native code.")

    # 1. Clean previous build output
    for folder in ['build', 'dist']:
        if os.path.exists(folder):
            print(f"[*] Removing old {folder} folder...")
            shutil.rmtree(folder, ignore_errors=True)

    # 2. Ensure the app and builder dependencies are installed for THIS
    # interpreter. This matters when the script selected a clean Python 3.13.
    try:
        import PyInstaller  # noqa: F401
        import webview  # noqa: F401
        import clr  # noqa: F401
    except ImportError:
        print("[*] Installing build dependencies for Python 3.13...")
        subprocess.check_call([
            sys.executable, "-m", "pip", "install",
            "-r", "requirements.txt", "pyinstaller",
        ])

    # 3. Define paths
    script_path = "main.pyw"
    icon_file = "meow-ware-icon.ico" if os.path.exists("meow-ware-icon.ico") else "vellium-icon.ico"

    # 4. Build command. Invoke via `<python> -m PyInstaller` so we don't
    # depend on the pyinstaller.exe shim being on PATH (it often isn't on
    # a fresh Windows Python install). Uses the same interpreter running
    # this script, so PyInstaller finds the packages we installed above.
    # On Windows, --add-data uses ';' between source and dest.
    separator = ";"
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconsole",
        "--onefile",
        "--collect-all=pythonnet",
        "--collect-all=roblox",
        "--collect-all=httpx",
        "--collect-all=anyio",
        f"--icon={icon_file}",
        f"--add-data=src/gui/ui{separator}src/gui/ui",
        f"--add-data=version.json{separator}.",
        f"--add-data=src/data{separator}src/data",
        f"--add-data=meow-ware-icon.png{separator}.",
        f"--add-data=vellium-icon.png{separator}.",
        "--name=VelliumTweaker",
        "--noconfirm",
        "--clean",
        script_path,
    ]

    print(f"[*] Executing: {' '.join(cmd)}")
    subprocess.check_call(cmd)

    print("\n[+] Build Complete!")
    print(f"[+] Standalone application: {os.path.abspath('dist/VelliumTweaker.exe')}")
    print("[+] This single EXE can be uploaded directly; no _internal folder is required.")
    print("[!] This debug build still contains decompilable Python bytecode. Do not distribute it.")

if __name__ == "__main__":
    build()
