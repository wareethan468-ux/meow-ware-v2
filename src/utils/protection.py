"""
protection.py - Anti-VM and Anti-Debug protection layer.

Performs environment checks at startup and periodically in the background.
Detected threats cause a clean, silent exit so reverse-engineers get no
useful diagnostic output.

Checks performed
================
Anti-Debug
----------
  1. IsDebuggerPresent (kernel32)        - standard Win32 debugger check
  2. CheckRemoteDebuggerPresent          - remote / attached debugger
  3. NtQueryInformationProcess (0x07)    - ProcessDebugPort via NT API
  4. sys.gettrace / sys.getprofile       - Python-level tracing/profiling
  5. Heap flags (NtQueryInformationProcess 0x12) - heap flag tamper
  6. Parent-process name heuristic       - known debugger/analysis parents

Anti-VM
-------
  1. Registry keys                       - VMware, VirtualBox, QEMU, Hyper-V, etc.
  2. Running processes                   - vmtoolsd, vboxservice, vmusrvc, etc.
  3. CPUID hypervisor flag               - hypervisor present bit via shellcode
  4. MAC address OUI                     - VM-vendor NIC prefixes
  5. System manufacturer / model         - WMI Win32_ComputerSystem
  6. Disk model                          - WMI Win32_DiskDrive (Virtual HD, VBOX, etc.)
  7. Username / hostname heuristics      - sandbox/analysis-box names
  8. Screen resolution                   - many sandboxes use < 900x700
  9. Uptime                              - fresh VMs typically have very short uptimes
 10. CPU count / RAM floor               - sandboxes often have 1 CPU and <= 2 GB RAM
"""

from __future__ import annotations

import os
import sys
import ctypes
import threading
import subprocess
import winreg
import socket
import uuid
import time


# -- internal exit helper ------------------------------------------------------

def _die() -> None:
    """Silent, hard exit with no traceback."""
    try:
        os._exit(0)
    except Exception:
        raise SystemExit(0)


# -- Anti-Debug ----------------------------------------------------------------

_k32 = ctypes.WinDLL('kernel32', use_last_error=True)
_nt  = ctypes.WinDLL('ntdll',    use_last_error=True)


def _check_is_debugger_present() -> bool:
    try:
        return bool(_k32.IsDebuggerPresent())
    except Exception:
        return False


def _check_remote_debugger() -> bool:
    try:
        result = ctypes.c_bool(False)
        _k32.CheckRemoteDebuggerPresent(
            _k32.GetCurrentProcess(),
            ctypes.byref(result)
        )
        return result.value
    except Exception:
        return False


def _check_nt_debug_port() -> bool:
    """NtQueryInformationProcess(ProcessDebugPort=7): non-zero means debugger."""
    try:
        port = ctypes.c_longlong(0)
        status = _nt.NtQueryInformationProcess(
            _k32.GetCurrentProcess(),
            7,
            ctypes.byref(port),
            ctypes.sizeof(port),
            None
        )
        return status == 0 and port.value != 0
    except Exception:
        return False


def _check_heap_flags() -> bool:
    """Check PEB.NtGlobalFlag: bits 0x70 are set under a debugger."""
    try:
        class _PBI(ctypes.Structure):
            _fields_ = [
                ('ExitStatus',                   ctypes.c_ulong),
                ('PebBaseAddress',               ctypes.c_void_p),
                ('AffinityMask',                 ctypes.c_size_t),
                ('BasePriority',                 ctypes.c_ulong),
                ('UniqueProcessId',              ctypes.c_size_t),
                ('InheritedFromUniqueProcessId', ctypes.c_size_t),
            ]
        pbi = _PBI()
        status = _nt.NtQueryInformationProcess(
            _k32.GetCurrentProcess(),
            0,
            ctypes.byref(pbi),
            ctypes.sizeof(pbi),
            None,
        )
        if status != 0 or not pbi.PebBaseAddress:
            return False
        flag = ctypes.c_ulong(0)
        _k32.ReadProcessMemory(
            _k32.GetCurrentProcess(),
            ctypes.c_void_p(pbi.PebBaseAddress + 0xBC),
            ctypes.byref(flag),
            ctypes.sizeof(flag),
            None,
        )
        return bool(flag.value & 0x70)
    except Exception:
        return False


def _check_python_trace() -> bool:
    """Detect Python-level debuggers (pdb, pydevd, etc.)."""
    try:
        if sys.gettrace() is not None:
            return True
        if sys.getprofile() is not None:
            return True
    except Exception:
        pass
    return False


_DEBUGGER_PARENT_NAMES: set = {
    'ollydbg.exe', 'x64dbg.exe', 'x32dbg.exe', 'windbg.exe',
    'ida.exe', 'ida64.exe', 'idaq.exe', 'idaq64.exe',
    'idaw.exe', 'idaw64.exe', 'devenv.exe',
    'processhacker.exe', 'procmon.exe', 'procmon64.exe',
    'wireshark.exe', 'fiddler.exe', 'charles.exe',
    'frida.exe', 'frida-server.exe', 'dnspy.exe', 'de4dot.exe',
    'pestudio.exe', 'lordpe.exe', 'cff explorer.exe',
    'immunity debugger.exe', 'radare2.exe', 'r2.exe',
    'cheatengine.exe', 'cheatengine-x86_64.exe',
    'scylla.exe', 'scylla_x64.exe', 'scylla_x86.exe',
    'api monitor.exe', 'apimon.exe',
}


def _check_parent_process() -> bool:
    try:
        import psutil
        parent = psutil.Process(os.getpid()).parent()
        if parent and parent.name().lower() in _DEBUGGER_PARENT_NAMES:
            return True
    except Exception:
        pass
    return False


def is_debugged() -> bool:
    """Return True if any anti-debug check fires."""
    return (
        _check_is_debugger_present()
        or _check_remote_debugger()
        or _check_nt_debug_port()
        or _check_heap_flags()
        or _check_python_trace()
        or _check_parent_process()
    )


# -- Anti-VM -------------------------------------------------------------------

_VM_REGISTRY_KEYS = [
    (winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\VMware, Inc.\VMware Tools',          None),
    (winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\Oracle\VirtualBox Guest Additions',  None),
    (winreg.HKEY_LOCAL_MACHINE, r'HARDWARE\ACPI\DSDT\VBOX__',                  None),
    (winreg.HKEY_LOCAL_MACHINE, r'HARDWARE\ACPI\FADT\VBOX__',                  None),
    (winreg.HKEY_LOCAL_MACHINE, r'HARDWARE\ACPI\RSDT\VBOX__',                  None),
    (winreg.HKEY_LOCAL_MACHINE, r'SYSTEM\ControlSet001\Services\VBoxGuest',     None),
    (winreg.HKEY_LOCAL_MACHINE, r'SYSTEM\ControlSet001\Services\VBoxMouse',     None),
    (winreg.HKEY_LOCAL_MACHINE, r'SYSTEM\ControlSet001\Services\VBoxService',   None),
    (winreg.HKEY_LOCAL_MACHINE, r'SYSTEM\ControlSet001\Services\VBoxSF',        None),
    (winreg.HKEY_LOCAL_MACHINE, r'SYSTEM\ControlSet001\Services\vmci',          None),
    (winreg.HKEY_LOCAL_MACHINE, r'SYSTEM\ControlSet001\Services\vmhgfs',        None),
    (winreg.HKEY_LOCAL_MACHINE, r'SYSTEM\ControlSet001\Services\vmmouse',       None),
    (winreg.HKEY_LOCAL_MACHINE, r'SYSTEM\ControlSet001\Services\VMTools',       None),
    (winreg.HKEY_LOCAL_MACHINE, r'SYSTEM\ControlSet001\Services\VMMEMCTL',      None),
    (winreg.HKEY_LOCAL_MACHINE, r'SYSTEM\ControlSet001\Services\vmware',        None),
    (winreg.HKEY_LOCAL_MACHINE, r'SYSTEM\ControlSet001\Services\vmx86',         None),
    (winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\Microsoft\Virtual Machine\Guest\Parameters', None),
]

_VM_PROCESS_NAMES: set = {
    'vmtoolsd.exe', 'vmwaretray.exe', 'vmwareuser.exe', 'vmacthlp.exe',
    'vmnat.exe', 'vmnetdhcp.exe', 'vmount2.exe', 'vmusrvc.exe',
    'vboxservice.exe', 'vboxtray.exe',
    'qemu-ga.exe', 'spice-vdagent.exe',
    'xenservice.exe', 'xenfilt.exe',
    'prl_tools.exe', 'prl_cc.exe',
    'vgauthservice.exe',
    'sbiectrl.exe', 'sandboxiedcomlaunch.exe', 'sbiesvc.exe',
}

_VM_MAC_PREFIXES: set = {
    '00:05:69',  # VMware
    '00:0c:29',  # VMware
    '00:1c:14',  # VMware
    '00:50:56',  # VMware
    '08:00:27',  # VirtualBox
    '52:54:00',  # QEMU / KVM
    '00:16:3e',  # Xen
    '00:1a:4a',  # Red Hat / KVM
    '00:03:ff',  # Hyper-V
    '00:15:5d',  # Hyper-V
}

_VM_DISK_STRINGS = [
    'virtual', 'vbox', 'vmware', 'qemu', 'virtio', 'vhd', 'xen',
]

_VM_MANUFACTURER_STRINGS = [
    'vmware', 'virtualbox', 'qemu', 'bochs', 'xen', 'parallels',
    'microsoft corporation',
    'innotek', 'oracle',
]

_SANDBOX_USERNAMES: set = {
    'sandbox', 'virus', 'malware', 'analysis', 'analyst', 'tester',
    'vmware', 'vboxuser', 'currentuser', 'sample',
}

_SANDBOX_HOSTNAMES: set = {
    'sandbox', 'malware', 'virus', 'analysis', 'cuckoo',
    'anyrun', 'joeboxserver', 'joeboxcontrol',
    'vmware', 'virtualbox', 'vbox',
}


def _check_vm_registry() -> bool:
    for hive, path, value in _VM_REGISTRY_KEYS:
        try:
            key = winreg.OpenKey(hive, path)
            if value:
                winreg.QueryValueEx(key, value)
            winreg.CloseKey(key)
            return True
        except OSError:
            pass
    return False


def _check_vm_processes() -> bool:
    try:
        out = subprocess.check_output(
            ['wmic', 'process', 'get', 'name'],
            stderr=subprocess.DEVNULL,
            timeout=5
        ).decode(errors='ignore').lower()
        for name in _VM_PROCESS_NAMES:
            if name in out:
                return True
    except Exception:
        pass
    try:
        import psutil
        running = {p.name().lower() for p in psutil.process_iter(['name'])}
        return bool(running & _VM_PROCESS_NAMES)
    except Exception:
        pass
    return False


def _check_vm_mac() -> bool:
    try:
        mac_int = uuid.getnode()
        mac_str = ':'.join('{:02x}'.format((mac_int >> (5 - i) * 8) & 0xff) for i in range(6))
        prefix = mac_str[:8]
        return prefix in _VM_MAC_PREFIXES
    except Exception:
        return False


def _check_vm_wmi(wmic_alias, field, badstrings) -> bool:
    try:
        out = subprocess.check_output(
            ['wmic', wmic_alias, 'get', field],
            stderr=subprocess.DEVNULL,
            timeout=5
        ).decode(errors='ignore').lower()
        for s in badstrings:
            if s in out:
                return True
    except Exception:
        pass
    return False


def _check_vm_manufacturer() -> bool:
    return _check_vm_wmi('computersystem', 'manufacturer,model', _VM_MANUFACTURER_STRINGS)


def _check_vm_disk() -> bool:
    return _check_vm_wmi('diskdrive', 'model', _VM_DISK_STRINGS)


def _check_vm_username_hostname() -> bool:
    try:
        user = os.environ.get('USERNAME', '').lower().strip()
        host = socket.gethostname().lower().strip()
        if user in _SANDBOX_USERNAMES:
            return True
        for s in _SANDBOX_HOSTNAMES:
            if s in host:
                return True
    except Exception:
        pass
    return False


def _check_vm_screen() -> bool:
    try:
        w = ctypes.windll.user32.GetSystemMetrics(0)
        h = ctypes.windll.user32.GetSystemMetrics(1)
        if w < 900 or h < 700:
            return True
    except Exception:
        pass
    return False


def _check_vm_cpuid() -> bool:
    """Check the hypervisor-present CPUID bit (ECX bit 31 of leaf 1)."""
    try:
        _SC = bytes([
            0x48, 0x83, 0xEC, 0x28,        # sub rsp, 0x28
            0xB8, 0x01, 0x00, 0x00, 0x00,  # mov eax, 1
            0x33, 0xC9,                    # xor ecx, ecx
            0x0F, 0xA2,                    # cpuid
            0xC1, 0xE9, 0x1F,              # shr ecx, 31
            0x8B, 0xC1,                    # mov eax, ecx
            0x48, 0x83, 0xC4, 0x28,        # add rsp, 0x28
            0xC3,                          # ret
        ])
        buf = ctypes.create_string_buffer(_SC)
        addr = ctypes.cast(buf, ctypes.c_void_p).value
        old = ctypes.c_ulong(0)
        ctypes.windll.kernel32.VirtualProtect(
            ctypes.c_void_p(addr), len(_SC), 0x40, ctypes.byref(old)
        )
        proto = ctypes.CFUNCTYPE(ctypes.c_uint32)
        fn = proto(addr)
        result = fn()
        return bool(result & 1)
    except Exception:
        return False


def _check_vm_uptime() -> bool:
    """Uptime < 5 minutes is suspicious (freshly spun VM)."""
    try:
        uptime_ms = ctypes.windll.kernel32.GetTickCount64()
        return uptime_ms < 5 * 60 * 1000
    except Exception:
        return False


def _check_vm_cpu_ram() -> bool:
    """1 CPU or <= 2 GB RAM is typical in automated sandboxes."""
    try:
        if os.cpu_count() is not None and os.cpu_count() <= 1:
            return True
    except Exception:
        pass
    try:
        class _MEMSTATUS(ctypes.Structure):
            _fields_ = [
                ('dwLength',                ctypes.c_ulong),
                ('dwMemoryLoad',            ctypes.c_ulong),
                ('ullTotalPhys',            ctypes.c_ulonglong),
                ('ullAvailPhys',            ctypes.c_ulonglong),
                ('ullTotalPageFile',        ctypes.c_ulonglong),
                ('ullAvailPageFile',        ctypes.c_ulonglong),
                ('ullTotalVirtual',         ctypes.c_ulonglong),
                ('ullAvailVirtual',         ctypes.c_ulonglong),
                ('ullAvailExtendedVirtual', ctypes.c_ulonglong),
            ]
        ms = _MEMSTATUS()
        ms.dwLength = ctypes.sizeof(ms)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(ms))
        total_gb = ms.ullTotalPhys / (1024 ** 3)
        if total_gb <= 2.0:
            return True
    except Exception:
        pass
    return False


def is_vm() -> bool:
    """Return True if any anti-VM check fires."""
    checks = [
        _check_vm_registry,
        _check_vm_processes,
        _check_vm_mac,
        _check_vm_manufacturer,
        _check_vm_disk,
        _check_vm_username_hostname,
        _check_vm_screen,
        _check_vm_cpuid,
        _check_vm_uptime,
        _check_vm_cpu_ram,
    ]
    for fn in checks:
        try:
            if fn():
                return True
        except Exception:
            pass
    return False


# -- Public entry points -------------------------------------------------------

def run_checks() -> None:
    """Run all checks synchronously. Call at startup BEFORE the UI launches."""
    if is_debugged():
        _die()
    if is_vm():
        _die()


def start_background_monitor(interval: float = 10.0) -> None:
    """Spawn a daemon thread that re-runs anti-debug checks every `interval`
    seconds. Anti-VM checks are NOT repeated (they are slow/noisy)."""
    def _loop() -> None:
        while True:
            time.sleep(interval)
            try:
                if is_debugged():
                    _die()
            except Exception:
                pass

    t = threading.Thread(target=_loop, daemon=True, name='ProtectionMonitor')
    t.start()
