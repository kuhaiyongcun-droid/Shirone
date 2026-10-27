"""Start/stop only this release's own hidden loopback preview process."""
import argparse
import ctypes
from ctypes import wintypes
import datetime
import json
import os
import re
import socket
import subprocess
import sys
import time
from pathlib import Path

RELEASE = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('mode', choices=('start', 'stop'))
parser.add_argument('dist', nargs='?')
parser.add_argument('--port', type=int, default=4177)
options = parser.parse_args()
if not 1024 <= options.port <= 65535:
    raise SystemExit('Use a loopback port between 1024 and 65535')
PORT = options.port
STATE = RELEASE / 'evidence' / ('preview-active.json' if PORT == 4177 else f'preview-active-{PORT}.json')
kernel = ctypes.WinDLL('kernel32', use_last_error=True)
kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel.OpenProcess.restype = wintypes.HANDLE
kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
kernel.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
kernel.CloseHandle.argtypes = [wintypes.HANDLE]

def identity(handle):
    times = [wintypes.FILETIME() for _ in range(4)]
    if not kernel.GetProcessTimes(handle, *(ctypes.byref(value) for value in times)):
        raise ctypes.WinError()
    length = wintypes.DWORD(32768)
    name = ctypes.create_unicode_buffer(length.value)
    if not kernel.QueryFullProcessImageNameW(handle, 0, name, ctypes.byref(length)):
        raise ctypes.WinError()
    ticks = (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime
    return ticks, name.value

def save(record):
    temporary = STATE.with_name(STATE.name + '.' + str(os.getpid()) + '.tmp')
    with temporary.open('x', encoding='utf-8') as stream:
        json.dump(record, stream, ensure_ascii=False, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, STATE)

mode = options.mode
if mode == 'start':
    name = options.dist or ''
    if not re.fullmatch(r'dist(?:-[A-Za-z0-9_-]+)?', name):
        raise SystemExit('Supply a real assembled dist name')
    if STATE.exists() and json.loads(STATE.read_text(encoding='utf-8')).get('status') == 'RUNNING':
        raise SystemExit('Recorded preview still running; stop that exact owned process first')
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', PORT))
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    log = RELEASE / 'evidence' / ('preview-' + str(PORT) + '-' + stamp + '.log')
    with log.open('xb') as output:
        process = subprocess.Popen([sys.executable, '-B', str(RELEASE / 'scripts/serve-preview.py'), name, '--port', str(PORT)],
                                   cwd=RELEASE, stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        ticks, executable = identity(int(process._handle))
        record = {'status': 'RUNNING', 'pid': process.pid, 'creation_ticks': ticks, 'executable': executable,
                  'dist': name, 'url': f'http://127.0.0.1:{PORT}/', 'log': str(log), 'started_utc': stamp,
                  'owner': 'blog-release-v1/scripts/manage-preview.py'}
        time.sleep(1)
        if process.poll() is not None:
            record['status'] = 'FAILED_START'
            record['exit_code'] = process.returncode
        save(record)
    except BaseException:
        # Popen retains the exact child handle; no PID-based fallback or unrelated process kill.
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=10)
        raise
    print(json.dumps(record))
    raise SystemExit(0 if record['status'] == 'RUNNING' else 1)
elif mode == 'stop':
    record = json.loads(STATE.read_text(encoding='utf-8'))
    if record.get('status') != 'RUNNING' or record.get('owner') != 'blog-release-v1/scripts/manage-preview.py':
        raise SystemExit('No running process owned by this launcher')
    handle = kernel.OpenProcess(0x1000 | 0x0001 | 0x00100000, False, record['pid'])
    if not handle:
        error = ctypes.get_last_error()
        if error != 87:  # ERROR_INVALID_PARAMETER: no process with this PID.
            raise SystemExit('Cannot verify owned process; state retained. Win32 error ' + str(error))
        record['status'] = 'PID_NO_LONGER_EXISTS'
    else:
        try:
            ticks, executable = identity(handle)
            if ticks != record['creation_ticks'] or executable.casefold() != record['executable'].casefold():
                raise SystemExit('Process identity changed; refusing to stop')
            if kernel.WaitForSingleObject(handle, 0) == 0:
                record['status'] = 'ALREADY_EXITED'
            else:
                if not kernel.TerminateProcess(handle, 0):
                    raise ctypes.WinError()
                if kernel.WaitForSingleObject(handle, 10000) != 0:
                    raise SystemExit('Owned preview exit not confirmed')
                record['status'] = 'STOPPED'
        finally:
            kernel.CloseHandle(handle)
    record['stopped_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    save(record)
    print(json.dumps(record))
else:
    raise SystemExit('Usage: manage-preview.py start dist-NAME | stop')
