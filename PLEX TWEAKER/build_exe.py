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

    print("[*] Starting Plex build...")
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
        import psutil  # noqa: F401
        import packaging  # noqa: F401
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
        "--onedir",
        "--collect-all=roblox",
        "--collect-all=httpx",
        "--collect-all=anyio",
        "--collect-all=psutil",
        # Do not inject a PE icon with this PyInstaller/pefile toolchain. Its
        # resource rewrite corrupts AddressOfEntryPoint on this host. Plex still
        # uses the branded icon in its title bar and notification tray.
        f"--add-data=src/gui/ui{separator}src/gui/ui",
        f"--add-data=version.json{separator}.",
        f"--add-data=src/data{separator}src/data",
        f"--add-data=meow-ware-icon.png{separator}.",
        f"--add-data=vellium-icon.png{separator}.",
        "--name=Plex",
        "--noconfirm",
        "--clean",
        script_path,
    ]

    print(f"[*] Executing: {' '.join(cmd)}")
    subprocess.check_call(cmd)

    # PyInstaller's pefile resource rewrite corrupts the bootloader entry point
    # on this host. Recombine the untouched windowed bootloader with the built
    # archive. This is not obfuscation: it restores the loader PyInstaller ships
    # and avoids the invalid resource-mutated executable.
    import pefile
    import PyInstaller
    built_exe = os.path.join('dist', 'Plex', 'Plex.exe')
    pe = pefile.PE(built_exe, fast_load=True)
    overlay_offset = pe.get_overlay_data_start_offset()
    pe.close()
    if overlay_offset is None:
        raise RuntimeError('Plex.exe does not contain a PyInstaller archive')
    bootloader = os.path.join(
        os.path.dirname(PyInstaller.__file__), 'bootloader',
        'Windows-64bit-intel', 'runw.exe',
    )
    clean_exe = built_exe + '.clean'
    with open(bootloader, 'rb') as source, open(clean_exe, 'wb') as output:
        output.write(source.read())
        with open(built_exe, 'rb') as packaged:
            packaged.seek(overlay_offset)
            shutil.copyfileobj(packaged, output)
    os.replace(clean_exe, built_exe)

    # Keep the .NET optimizer beside Plex instead of embedding it. This avoids
    # inheriting its runtime-host imports in Plex.exe and avoids dropped-DLL
    # behavior from a one-file extractor while preserving the product feature.
    output_dir = os.path.join('dist', 'Plex')
    optimizer_dir = os.path.join(output_dir, 'optimizer')
    shutil.copytree(
        os.path.join('vendor', 'plex-optimizer', 'win-x64-clean'),
        optimizer_dir,
        dirs_exist_ok=True,
    )
    shutil.copy2(
        os.path.join('vendor', 'plex-optimizer', 'LICENSE-66MODS.txt'),
        os.path.join(optimizer_dir, 'LICENSE-66MODS.txt'),
    )

    print("\n[+] Build Complete!")
    print(f"[+] Clean application folder: {os.path.abspath('dist/Plex')}")
    print(f"[+] Main executable: {os.path.abspath('dist/Plex/Plex.exe')}")
    print("[+] Keep the complete Plex folder together when distributing it.")
    print("[!] This debug build still contains decompilable Python bytecode. Do not distribute it.")

if __name__ == "__main__":
    build()
