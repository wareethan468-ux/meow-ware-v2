import pefile, os, sys, PyInstaller

boot = os.path.join(os.path.dirname(PyInstaller.__file__), 'bootloader', 'Windows-64bit-intel', 'run.exe')
built = sys.argv[1]

for label, path in [('BOOTLOADER(ok)', boot), ('BUILT(bad)', built)]:
    print('=====', label, os.path.getsize(path), 'bytes')
    try:
        pe = pefile.PE(path, fast_load=True)
        oh = pe.OPTIONAL_HEADER
        fh = pe.FILE_HEADER
        print('  PE magic      : 0x%04x (%s)' % (oh.Magic, 'PE32+' if oh.Magic == 0x20b else 'PE32'))
        print('  Machine       : 0x%04x' % fh.Machine)
        print('  Subsystem     : %d' % oh.Subsystem)
        print('  Characteristics: 0x%04x' % fh.Characteristics)
        print('  NumSections   : %d' % fh.NumberOfSections)
        print('  SizeOfImage   : 0x%x' % oh.SizeOfImage)
        print('  SizeOfHeaders : 0x%x' % oh.SizeOfHeaders)
        print('  EntryPoint    : 0x%x' % oh.AddressOfEntryPoint)
        print('  FileAlign     : 0x%x   SectionAlign: 0x%x' % (oh.FileAlignment, oh.SectionAlignment))
        fsize = os.path.getsize(path)
        for s in pe.sections:
            name = s.Name.rstrip(b'\x00').decode(errors='replace')
            end = s.PointerToRawData + s.SizeOfRawData
            flag = '  <-- rawdata END > EOF!' if end > fsize else ''
            print('   sect %-8s VA=0x%06x Vsz=0x%06x raw=0x%06x rawsz=0x%06x end=0x%06x%s'
                  % (name, s.VirtualAddress, s.Misc_VirtualSize, s.PointerToRawData, s.SizeOfRawData, end, flag))
        # sanity checks
        last = pe.sections[-1]
        need = last.VirtualAddress + last.Misc_VirtualSize
        print('  last-sect VA+Vsz = 0x%x  vs SizeOfImage 0x%x  %s'
              % (need, oh.SizeOfImage, 'OK' if need <= oh.SizeOfImage else 'MISMATCH!'))
    except Exception as e:
        print('  pefile PARSE ERROR:', type(e).__name__, e)
