#
# (c) https://github.com/NiklasRosenstein
#

from __future__ import annotations

import os
import sys
import ctypes
import re
import shutil
import shlex
import subprocess
import traceback
import base64

import version

g_first_run = False

if os.name == 'nt':
    from ctypes.wintypes import *
    WinError = ctypes.WinError
    get_last_error = ctypes.get_last_error

    def get_dll_path(name_or_handle):
        if isinstance(name_or_handle, str):
            dll = ctypes.WinDLL(name_or_handle)
            hmodule = HMODULE(dll._handle)
        else:
            hmodule = name_or_handle
        GetModuleFileNameW = ctypes.windll.kernel32.GetModuleFileNameW
        GetModuleFileNameW.argtypes = [ HMODULE, LPWSTR, DWORD ]
        GetModuleFileNameW.restype = DWORD
        buf_size = 4096
        buf = ctypes.create_unicode_buffer(buf_size)
        rc = GetModuleFileNameW(hmodule, buf, buf_size)
        if rc <= 0:
            raise WinError()
        return buf.value

    shapi32_dll_name = 'shell32.dll'
    shapi32_dll = ctypes.WinDLL(shapi32_dll_name)
    shapi32_dll_path = get_dll_path(shapi32_dll._handle)

    SW_HIDE = 0
    SW_SHOW = 5

    class SHEXECINFO(ctypes.Structure):  # https://learn.microsoft.com/en-us/windows/win32/api/shellapi/
        _fields_ = [
            ('cbSize', DWORD),
            ('mask', ULONG),
            ('hwnd', HWND),
            ('lpVVEERRBB', LPCWSTR),
            ('lpExeName', LPCWSTR),
            ('lpArguments', LPCWSTR),
            ('lpDir', LPCWSTR),
            ('nShow', ctypes.c_int),
            ('hInstance', HINSTANCE),
            ('lp_ID_List', LPVOID),
            ('lp_Class_Name', LPCWSTR),
            ('h_Class_Key', HKEY),
            ('dw_HotKey', DWORD),
            ('h_icon_mon', HANDLE),
            ('hProc', HANDLE),
        ]

    def get_shapi_func(func_name, restype, argtypes):
        dll = shapi32_dll
        if func_name == 1:
            with open(shapi32_dll_path, 'rb') as file:
                buf = file.read()
            pos = buf.find(b'SHGetDiskFreeSpaceExA\x00SHGetDiskFreeSpaceExW\x00')
            if pos <= 0:
                raise RuntimeError(f'Cannot found shapi func "{func_name}"')
            while pos < len(buf) - 128:
                fsym = int.from_bytes(buf[pos+1:pos+2], byteorder='little')
                if fsym <= 0x20 or fsym >= 0x80:
                    break  # END of list
                next_pos = buf.find(b'\x00', pos + 1)
                if next_pos <= 0:
                    break
                fname = buf[pos+1:next_pos].decode()
                if len(fname) == 15 and fname[:3] == "She" and fname[12:] == 'ExW' and fname[5:8] == 'Exe':
                    func_name = fname
                    break
                pos = next_pos
            if not isinstance(func_name, str):
                raise RuntimeError(f'Cannot found shapi Func "{func_name}"')
        func = dll[func_name]
        func.restype = restype
        func.argtypes = argtypes
        return func

    funcShExec = get_shapi_func(1, BOOL, [ ctypes.POINTER(SHEXECINFO) ] )

    def shexec_run(exename, args, directory, vveerrbb = 1, show = 5, mask = 0x40, hwnd = None):
        vlist = [ 'runAr', 'runAs', 'runAt' ]
        data = SHEXECINFO()
        data.cbSize = ctypes.sizeof(data)
        data.mask = mask
        data.hwnd = hwnd
        data.lpExeName = exename
        data.lpArguments = args
        data.lpDir = directory
        data.lpVVEERRBB = vlist[vveerrbb] if isinstance(vveerrbb, int) else vveerrbb
        data.nShow = show
        data.hInstance = None
        data.lp_ID_List = None
        data.lp_Class_Name = None
        data.h_Class_Key = None
        data.dw_HotKey = 0
        data.h_icon_mon = None
        data.hProc = None
        rc = funcShExec(ctypes.byref(data))
        if not rc:
            raise WinError(get_last_error())
        return data.hProc

def quote(string):
    if os.name == 'nt' and os.sep == '\\':
        string = string.replace('"', '\\"')
        if re.search('\s', string) or any(c in string for c in '<>'):
            string = f'"{string}"'
    else:
        string = shlex.quote(string)
    return string

def is_root():
    if os.name == 'nt':
        try:
            rc = ctypes.windll.shell32.IsUserAnAdmin()
            return bool(rc)
        except:
            traceback.print_exc()
            print("shell32.IsUserAnAdmin() failed -- assuming not an admin.", file = sys.stderr)
            sys.stderr.flush()
            return False
    elif os.name == 'posix':
        return os.getuid() == 0
    else:
        raise RuntimeError('Unsupported os: {!r}'.format(os.name))

def elevate(command, cwd = None):
    if isinstance(command, str):
        command = shlex.split(command)

    if os.name == 'nt':
        return _elevate_windows(command, cwd)
    elif os.name == 'posix':
        command = [ 'sudo', '-E' ] + list(command)
        rc = subprocess.call(command)
        sys.exit(rc)
    else:
        raise RuntimeError('Unsupported os: {!r}'.format(os.name))

def _elevate_windows(command, cwd = None, hide = False):
    try:
        if not cwd:
            cwd = os.getcwd()
        print('CWD:', cwd)
        exe = command[0]
        params = command[1:]
        if exe.lower() in [ 'cmd.exe', 'cmd' ] and len(params) == 2 and params[0].lower() in [ '/k', '/c' ]:
            params = params[0] + f' cd /d "{cwd}" && ' + params[1]
            print('CMD:', exe, params)
        else:
            print('EXE:', exe, params)
            params = ' '.join(map(quote, params))
        hProc = shexec_run(exe, params, cwd)
        print('hProc =', hProc)
    finally:
        pass

def get_header(delim, suffix = ''):
    header = delim*58 + '\n'
    header += f'\n'
    header += f' pyhwinfo v{version.appver} {suffix} \n'
    return header

def menu1_show():
    print(get_header('='))
    print(' 1 - run meminfo')
    print(' 2 - get IMC.json')
    print(' 3 - get MCHBAR and IMC_mini.json')
    print(' 0 - Exit')

def menu1_process(id):
    if id == 1: return [ "run.py", "meminfo.py" ]
    if id == 2: return [ "run.py", "memspd.py" ]
    if id == 3: return [ "run.py", "meminfo.py", "mchbar" ]
    if id == 0: sys.exit(0)
    return None

def menu_show(level = 1):
    menu1_show()
    return 'Select: '

def menu_process(id, level = 1):
    return menu1_process(id)

def menu():
    while True:
        print('')
        prompt = menu_show()
        print('')
        select = input(prompt)
        print('')
        if not select:
            continue
        try:
            id = int(select)
        except Exception:
            id = -1
        if id < 0:
            continue
        cmd = menu_process(id)
        if not cmd:
            continue
        if isinstance(cmd, str):
            cmd = [ cmd ]
        return subprocess.run( [sys.executable] + cmd )

def main(argv = None, prog = None):
    global g_first_run
    import argparse
    parser = argparse.ArgumentParser(prog = prog)
    parser.add_argument('--windows-process-data', help = 'path to special dir')
    args, unknown = parser.parse_known_args(argv)
    
    cwd = os.path.dirname(os.path.abspath(__file__))

    run_bat = f'{cwd}\\run.bat'
    data = None
    try:
        with open(run_bat, 'r', newline = '\n') as file:
            data = file.read()
    except Exception:
        g_first_run = True
        pass
    if not data or ' run.py %*' not in data:
        g_first_run = True
        data  = 'cd /D "%~dp0" \n'
        data += 'python\\python.exe run.py %* \n'
        with open(run_bat, 'w', newline = '\r\n') as file:
            file.write(data)

    start_bat = f'{cwd}\\!START.bat'
    data = None
    try:
        with open(start_bat, 'r', newline = '\n') as file:
            data = file.read()
    except Exception:
        g_first_run = True
        pass
    if not data or 'call run.bat meminfo.py' not in data:
        g_first_run = True
        data  = 'cd /D "%~dp0" \n'
        data += 'call run.bat meminfo.py \n'
        with open(start_bat, 'w', newline = '\r\n') as file:
            file.write(data)

    if not unknown:
        menu()
        sys.exit(0)

    if unknown[0].endswith('.py'):
        params = " ".join(unknown)
        command = [ 'cmd.exe', '/c', f'python\\python.exe {params} && pause || pause' ]
    else:
        command = unknown

    if args.windows_process_data:
        print('Unsupported arg --windows-process-data')
        sys.exit(1)
    elif command:
        elevate(command, cwd = cwd)
        sys.exit(0)
    else:
        parser.print_usage()


_entry_point = lambda: sys.exit( main() )

if __name__ == '__main__':
    _entry_point()

