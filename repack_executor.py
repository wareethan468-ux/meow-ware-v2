"""Repack a PyInstaller onefile so it actually runs on this Python 3.14 setup.

PyInstaller 6.22.2's pefile-based resource injection corrupts the bootloader PE
under Python 3.14 (WinError 193 / 0xC0000005). The appended archive (overlay) is
fine, though. So we:

  1. take the *pristine* windowed bootloader (runw.exe) that PyInstaller ships,
  2. embed a requireAdministrator manifest into it via the Windows resource API
     (BeginUpdateResource/UpdateResource/EndUpdateResource) which recomputes the
     PE headers correctly (unlike pefile), then
  3. append the archive overlay extracted from PyInstaller's build.

Result: a valid, admin-elevated onefile that Windows will load and run.
"""
import ctypes
import os
import shutil
import struct
import sys
import tempfile
from ctypes import wintypes

import pefile
import PyInstaller

RT_MANIFEST = 24
CREATEPROCESS_MANIFEST_RESOURCE_ID = 1
LANG_NEUTRAL = 0x0409

ADMIN_MANIFEST = b"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<assembly xmlns="urn:schemas-microsoft-com:asm.v1" manifestVersion="1.0">
  <assemblyIdentity type="win32" name="Executor" version="1.0.0.0" processorArchitecture="*"/>
  <trustInfo xmlns="urn:schemas-microsoft-com:asm.v3">
    <security>
      <requestedPrivileges>
        <requestedExecutionLevel level="requireAdministrator" uiAccess="false"/>
      </requestedPrivileges>
    </security>
  </trustInfo>
  <compatibility xmlns="urn:schemas-microsoft-com:compatibility.v1">
    <application>
      <supportedOS Id="{8e0f7a12-bfb3-4fe8-b9a5-48fd50a15a9a}"/>
      <supportedOS Id="{1f676c76-80e1-4239-95bb-83d0f6d0da78}"/>
    </application>
  </compatibility>
  <application xmlns="urn:schemas-microsoft-com:asm.v3">
    <windowsSettings>
      <dpiAware xmlns="http://schemas.microsoft.com/SMI/2005/WindowsSettings">true/pm</dpiAware>
      <dpiAwareness xmlns="http://schemas.microsoft.com/SMI/2016/WindowsSettings">permonitorv2,permonitor</dpiAwareness>
    </windowsSettings>
  </application>
</assembly>
""".strip()


def _make_int_resource(i):
    return ctypes.cast(ctypes.c_void_p(i & 0xFFFF), wintypes.LPCWSTR)


def fix_size_of_image(exe_path):
    """Correct SizeOfImage if a resource edit left it smaller than the sections
    actually span. Both pefile and the Win32 UpdateResource API get this wrong
    on this Python 3.14 / Windows setup, and the too-small value makes the
    loader reject the image with WinError 193.
    """
    pe = pefile.PE(exe_path, fast_load=True)
    align = pe.OPTIONAL_HEADER.SectionAlignment
    need = max(s.VirtualAddress + s.Misc_VirtualSize for s in pe.sections)
    correct = (need + align - 1) // align * align
    current = pe.OPTIONAL_HEADER.SizeOfImage
    off = pe.OPTIONAL_HEADER.get_field_absolute_offset('SizeOfImage')
    pe.close()
    if current >= correct:
        return False
    with open(exe_path, 'r+b') as f:
        f.seek(off)
        f.write(struct.pack('<I', correct))
    print('  fixed SizeOfImage 0x%x -> 0x%x' % (current, correct))
    return True


def embed_admin_manifest(exe_path):
    k = ctypes.WinDLL('kernel32', use_last_error=True)
    k.BeginUpdateResourceW.restype = wintypes.HANDLE
    k.BeginUpdateResourceW.argtypes = [wintypes.LPCWSTR, wintypes.BOOL]
    k.UpdateResourceW.restype = wintypes.BOOL
    k.UpdateResourceW.argtypes = [wintypes.HANDLE, wintypes.LPCWSTR, wintypes.LPCWSTR,
                                  wintypes.WORD, wintypes.LPVOID, wintypes.DWORD]
    k.EndUpdateResourceW.restype = wintypes.BOOL
    k.EndUpdateResourceW.argtypes = [wintypes.HANDLE, wintypes.BOOL]

    h = k.BeginUpdateResourceW(exe_path, False)
    if not h:
        raise ctypes.WinError(ctypes.get_last_error())
    buf = ctypes.create_string_buffer(ADMIN_MANIFEST, len(ADMIN_MANIFEST))
    ok = k.UpdateResourceW(h, _make_int_resource(RT_MANIFEST),
                           _make_int_resource(CREATEPROCESS_MANIFEST_RESOURCE_ID),
                           LANG_NEUTRAL, ctypes.cast(buf, wintypes.LPVOID), len(ADMIN_MANIFEST))
    if not ok:
        err = ctypes.get_last_error()
        k.EndUpdateResourceW(h, True)
        raise ctypes.WinError(err)
    if not k.EndUpdateResourceW(h, False):
        raise ctypes.WinError(ctypes.get_last_error())


def repack(built_exe, out_exe, windowed=True):
    boot_name = 'runw.exe' if windowed else 'run.exe'
    boot = os.path.join(os.path.dirname(PyInstaller.__file__),
                        'bootloader', 'Windows-64bit-intel', boot_name)
    if not os.path.exists(boot):
        raise FileNotFoundError(boot)

    # Extract the archive overlay from PyInstaller's (corrupt-header) build.
    pe = pefile.PE(built_exe, fast_load=True)
    ov_off = pe.get_overlay_data_start_offset()
    pe.close()
    if ov_off is None:
        raise RuntimeError('no overlay found in %s (not a onefile build?)' % built_exe)
    overlay = open(built_exe, 'rb').read()[ov_off:]

    # Embed the admin manifest into a pristine bootloader copy (OS fixes headers).
    fd, tmp_boot = tempfile.mkstemp(suffix='.exe')
    os.close(fd)
    try:
        shutil.copy(boot, tmp_boot)
        embed_admin_manifest(tmp_boot)
        fix_size_of_image(tmp_boot)
        boot_bytes = open(tmp_boot, 'rb').read()
    finally:
        try:
            os.remove(tmp_boot)
        except OSError:
            pass

    with open(out_exe, 'wb') as f:
        f.write(boot_bytes + overlay)

    print('  bootloader  : %s (%d bytes, +admin manifest)' % (boot_name, len(boot_bytes)))
    print('  overlay     : %d bytes (from %s)' % (len(overlay), os.path.basename(built_exe)))
    print('  wrote       : %s (%d bytes)' % (out_exe, os.path.getsize(out_exe)))


if __name__ == '__main__':
    built = sys.argv[1]
    out = sys.argv[2]
    windowed = '--console' not in sys.argv[3:]
    repack(built, out, windowed=windowed)
