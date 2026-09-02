"""Validate + finalize a built onedir Executor.exe.

1. Patch SizeOfImage if PyInstaller (3.14) left it too small  -> avoids WinError 193.
2. Confirm the embedded resources include the requireAdministrator manifest.
3. Launch via CreateProcess (no auto-elevation) and read the error:
      740 = ERROR_ELEVATION_REQUIRED  -> PE valid AND admin manifest active  (PASS)
      193 = not a valid Win32 app     -> PE still corrupt                      (FAIL)
      0   = ran (already elevated, or no admin manifest)
"""
import struct, subprocess, sys, os
import pefile


def align_up(v, a):
    return (v + a - 1) // a * a


def fix_size_of_image(path):
    pe = pefile.PE(path, fast_load=True)
    align = pe.OPTIONAL_HEADER.SectionAlignment
    need = max(s.VirtualAddress + s.Misc_VirtualSize for s in pe.sections)
    correct = align_up(need, align)
    current = pe.OPTIONAL_HEADER.SizeOfImage
    off = pe.OPTIONAL_HEADER.get_field_absolute_offset('SizeOfImage')
    pe.close()
    if current >= correct:
        print(f'  SizeOfImage OK: 0x{current:x} (needs 0x{correct:x})')
        return
    with open(path, 'r+b') as f:
        f.seek(off); f.write(struct.pack('<I', correct))
    print(f'  SizeOfImage PATCHED 0x{current:x} -> 0x{correct:x}')


def check_manifest(path):
    pe = pefile.PE(path)
    found = False
    if hasattr(pe, 'DIRECTORY_ENTRY_RESOURCE'):
        for entry in pe.DIRECTORY_ENTRY_RESOURCE.entries:
            if entry.id == 24:  # RT_MANIFEST
                data_rva = entry.directory.entries[0].directory.entries[0].data.struct.OffsetToData
                size = entry.directory.entries[0].directory.entries[0].data.struct.Size
                blob = pe.get_data(data_rva, size)
                txt = blob.decode('utf-8', 'replace')
                found = 'requireAdministrator' in txt
                print('  manifest present; requireAdministrator =', found)
    pe.close()
    if not found:
        print('  WARNING: no requireAdministrator manifest found')
    return found


def probe_launch(path):
    try:
        p = subprocess.Popen([path], cwd=os.path.dirname(path))
        # if it started (elevated session or no manifest), let it live briefly then kill
        try:
            p.wait(timeout=6)
            print(f'  launch: process exited rc={p.returncode}')
        except subprocess.TimeoutExpired:
            p.kill()
            print('  launch: process STARTED and is running (valid PE)')
    except OSError as e:
        we = getattr(e, 'winerror', None)
        names = {740: 'ELEVATION_REQUIRED  -> VALID PE + admin manifest (PASS)',
                 193: 'not a valid Win32 app -> PE STILL CORRUPT (FAIL)'}
        print(f'  launch: WinError {we}: {names.get(we, str(e))}')
        return we
    return 0


if __name__ == '__main__':
    exe = sys.argv[1]
    print('== finalize', exe, f'({os.path.getsize(exe)} bytes)')
    fix_size_of_image(exe)
    check_manifest(exe)
    probe_launch(exe)
