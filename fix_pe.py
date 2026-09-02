"""Repair PyInstaller (Python 3.14) exes whose SizeOfImage was left too small
after the resource section was injected, which makes Windows reject them with
[WinError 193] "%1 is not a valid Win32 application".

Recomputes SizeOfImage = align_up(max section VA+VirtualSize, SectionAlignment)
and patches just those 4 header bytes in place. The appended onefile PKG overlay
is untouched.
"""
import struct
import sys
import pefile


def align_up(value, alignment):
    return (value + alignment - 1) // alignment * alignment


def fix(path):
    pe = pefile.PE(path, fast_load=True)
    align = pe.OPTIONAL_HEADER.SectionAlignment
    need = max(s.VirtualAddress + s.Misc_VirtualSize for s in pe.sections)
    correct = align_up(need, align)
    current = pe.OPTIONAL_HEADER.SizeOfImage
    off = pe.OPTIONAL_HEADER.get_field_absolute_offset('SizeOfImage')
    pe.close()

    if current >= correct:
        print(f'  OK already: SizeOfImage=0x{current:x} >= required 0x{correct:x} — no change')
        return False

    with open(path, 'r+b') as f:
        f.seek(off)
        f.write(struct.pack('<I', correct))
    print(f'  PATCHED SizeOfImage 0x{current:x} -> 0x{correct:x} (field @ file offset 0x{off:x})')
    return True


if __name__ == '__main__':
    for p in sys.argv[1:]:
        print(p)
        fix(p)
