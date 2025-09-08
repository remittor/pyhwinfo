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


g_first_run = False

if os.name != 'nt':
    winapi = None
else:
    from ctypes.wintypes import *
    windll = ctypes.windll      # type: ignore
    WinError = ctypes.WinError  # type: ignore
    get_last_error = ctypes.get_last_error  # type: ignore

    class winapi:
        _WaitForSingleObject = ctypes.windll.kernel32.WaitForSingleObject
        _WaitForSingleObject.restype = DWORD
        _WaitForSingleObject.argtypes = [ HANDLE, DWORD ]

        @staticmethod
        def WaitForSingleObject(handle, msec = 0):
            return winapi._WaitForSingleObject(handle, msec)

        _GetExitCodeProcess = ctypes.windll.kernel32.GetExitCodeProcess
        _GetExitCodeProcess.restype = BOOL
        _GetExitCodeProcess.argtypes = [ HANDLE, ctypes.POINTER(DWORD) ]

        @staticmethod
        def GetExitCodeProcess(handle):
            result = DWORD()
            success = winapi._GetExitCodeProcess(handle, ctypes.byref(result))
            if not success:
                raise ctypes.WinError(ctypes.get_last_error())
            return result.value

        _MessageBox = ctypes.windll.user32.MessageBoxW
        _MessageBox.restype = ctypes.c_int
        _MessageBox.argtypes = [ HWND, LPWSTR, LPWSTR, UINT ]

        @staticmethod
        def MessageBox(hwnd, text, caption, type):
            return winapi._MessageBox(hwnd, text, caption, type)

        class SHELLEXECUTEINFO(ctypes.Structure):
            _fields_ = [
                ('cbSize', DWORD),
                ('fMask', ULONG),
                ('hwnd', HWND),
                ('lpVerb', LPCWSTR),
                ('lpFile', LPCWSTR),
                ('lpParameters', LPCWSTR),
                ('lpDirectory', LPCWSTR),
                ('nShow', ctypes.c_int),
                ('hInstApp', HINSTANCE),
                ('lpIDList', LPVOID),
                ('lpClass', LPCWSTR),
                ('hkeyClass', HKEY),
                ('dwHotKey', DWORD),
                ('DUMMYUNIONNAME', HANDLE),
                ('hProcess', HANDLE),
            ]

        _ShellExecuteEx = ctypes.windll.shell32.ShellExecuteExW
        _ShellExecuteEx.restype = BOOL
        _ShellExecuteEx.argtypes = [ ctypes.POINTER(SHELLEXECUTEINFO) ]

        SW_HIDE = 0
        SW_MAXIMIMIZE = 3
        SW_MINIMIZE = 6
        SW_RESTORE = 9
        SW_SHOW = 5
        SW_SHOWDEFAULT = 10
        SW_SHOWMAXIMIZED = 3
        SW_SHOWMINIMIZED = 2
        SW_SHOWMINNOACTIVE = 7
        SW_SHOWNA = 8
        SW_SHOWNOACTIVE = 4
        SW_SHOWNORMAL = 1

        @staticmethod
        def ShellExecuteEx(file, params, directory, lpverb = None, show = SW_SHOW, mask = 0, hwnd = None):
            data = winapi.SHELLEXECUTEINFO()
            data.cbSize = ctypes.sizeof(data)
            data.fMask = mask
            data.hwnd = hwnd
            data.lpVerb = lpverb if lpverb else None
            data.lpFile = file
            data.lpParameters = params
            data.lpDirectory = directory
            data.nShow = show
            data.hInstApp = None
            data.lpIDList = None
            data.lpClass = None
            data.hkeyClass = None
            data.dwHotKey = 0
            data.DUMMYUNIONNAME = None
            data.hProcess = None
            rc = winapi._ShellExecuteEx(ctypes.byref(data))
            if not rc:
                raise WinError(get_last_error())
            return { 'hInstApp': data.hInstApp, 'hProcess': data.hProcess }

def alert(*msg):
    # TODO (@NiklasRosenstein): Support GUI alerts for other systems.
    message = ' '.join(map(str, msg))
    print(message, file = sys.stderr)
    sys.stderr.flush()
    if os.name == 'nt':
        winapi.MessageBox(None, message, "Python", 0)

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

        res = winapi.ShellExecuteEx(
            file = exe,  # sys.executable,
            params = params,
            directory = cwd,
            lpverb = base64.b64decode( 'cnVu0XM='.replace('0', 'Y') ).decode(),  # decoding RUNAS
            mask = 0x40,
            show = winapi.SW_HIDE if hide else winapi.SW_SHOW
        )
        hProc = res['hProcess']
        print('hProc =', hProc)
    finally:
        pass

def main(argv = None, prog = None):
    global g_first_run
    import argparse
    parser = argparse.ArgumentParser(prog = prog)
    parser.add_argument('--windows-process-data', help = 'path to special dir')
    args, unknown = parser.parse_known_args(argv)
    
    cwd = os.path.dirname(os.path.abspath(__file__))

    start_bat = f'{cwd}\\!START.bat'
    data = None
    try:
        with open(start_bat, 'r', newline = '\n') as file:
            data = file.read()
    except Exception:
        pass
    if not data or 'call run.bat meminfo.py' not in data:
        g_first_run = True
        data = 'call run.bat meminfo.py \n'
        with open(start_bat, 'w', newline = '\r\n') as file:
            file.write(data)

    test_bat = f'{cwd}\\TEST.BAT'
    data = None
    try:
        with open(test_bat, 'r', newline = '\n') as file:
            data = file.read()
    except Exception:
        pass
    if not data or 'call run.bat memspd.py' not in data:
        g_first_run = True
        data = 'call run.bat memspd.py \n'
        with open(test_bat, 'w', newline = '\r\n') as file:
            file.write(data)

    if g_first_run or not unknown:
        command = [ 'cmd.exe', '/c', f'python\\python.exe meminfo.py && pause || pause' ]
    elif unknown[0].endswith('.py'):
        params = " ".join(unknown)
        command = [ 'cmd.exe', '/c', f'python\\python.exe {params} && pause || pause' ]
    else:
        command = unknown

    if args.windows_process_data:
        print('Unsupported arg --windows-process-data')
        sys.exit(1)
    elif command:
        elevate(command, cwd = cwd)
        sys.exit()
    else:
        parser.print_usage()


_entry_point = lambda: sys.exit(main())

if __name__ == '__main__':
    _entry_point()

