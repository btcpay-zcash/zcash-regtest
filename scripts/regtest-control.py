#!/usr/bin/env python3
"""Start/stop the native stack, preserving its chain and wallet databases."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / 'data/local'
CONTROL = DATA / 'control.json'
RUNNER = ROOT / 'scripts/run-local.py'


def read_control():
    return json.loads(CONTROL.read_text()) if CONTROL.exists() else {}


def owned_process(control):
    pid = control.get('pid')
    token = control.get('token')
    if not pid or not token:
        return False
    result = subprocess.run(['ps', '-p', str(pid), '-o', 'command='], capture_output=True, text=True)
    return result.returncode == 0 and str(RUNNER) in result.stdout and f'--control-token {token}' in result.stdout


def ready(control):
    marker = Path(control['state']) / 'ready.json'
    if not marker.exists():
        return False
    try:
        return json.loads(marker.read_text()).get('token') == control['token']
    except (ValueError, OSError):
        return False


def save_control(control):
    path = CONTROL.with_suffix('.tmp')
    with open(path, 'w') as output:
        json.dump(control, output)
    path.replace(CONTROL)


def show(control):
    running = owned_process(control)
    phase = ('running' if ready(control) else 'starting') if running else 'stopped'
    print(f'Regtest: {phase}', flush=True)
    if control.get('state'):
        print(f'State: {control["state"]}', flush=True)
        print(f'Logs: {control["state"]}/launcher.log and component *.log', flush=True)
    if running:
        print(f'PID: {control["pid"]}\nZebra RPC: http://127.0.0.1:18232\nlightwalletd: http://127.0.0.1:8137\nMain GraphQL: http://127.0.0.1:18081/graphql\nCashcow GraphQL: http://127.0.0.1:18082/graphql', flush=True)
    return running


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['start', 'stop', 'status'])
    parser.add_argument('--state-dir', type=Path, help='Resume this existing run (start only)')
    parser.add_argument('--fresh', action='store_true', help='Create a new run instead of resuming (start only)')
    args = parser.parse_args()
    if (args.state_dir or args.fresh) and args.command != 'start':
        parser.error('--state-dir and --fresh are start options')
    if args.state_dir and args.fresh:
        parser.error('Use either --state-dir or --fresh')
    DATA.mkdir(parents=True, exist_ok=True)
    # Serialize ownership changes; release the lock before waiting for readiness.
    with open(DATA / 'control.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        control = read_control()
        if args.command == 'status':
            show(control)
            return
        if args.command == 'stop':
            if not owned_process(control):
                print('Regtest is already stopped (no owned launcher running).')
                return
            os.kill(control['pid'], signal.SIGTERM)
            deadline = time.monotonic() + 60
            while owned_process(control) and time.monotonic() < deadline:
                time.sleep(0.2)
            if owned_process(control):
                raise RuntimeError('Shutdown timed out; inspect component logs. No unrelated processes were signalled.')
            print('Regtest stopped. Chain, wallets, keys and logs are preserved.')
            return
        if owned_process(control):
            print('Regtest is already started.')
            show(control)
            return
        if args.state_dir:
            state = args.state_dir.resolve()
            if not state.is_dir():
                raise RuntimeError(f'State directory does not exist: {state}')
        elif not args.fresh and control.get('state'):
            state = Path(control['state'])
            if not state.is_dir():
                raise RuntimeError(f'Saved state is missing: {state}. Use --fresh to create a new chain.')
        else:
            state = Path(tempfile.mkdtemp(prefix='run-', dir=DATA))
        token = uuid.uuid4().hex
        with open(state / 'launcher.log', 'a') as log:
            process = subprocess.Popen([sys.executable, str(RUNNER), '--state-dir', str(state), '--control-token', token], stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        control = {'pid': process.pid, 'token': token, 'state': str(state)}
        save_control(control)
    print(f'Starting regtest; logs: {state}/launcher.log', flush=True)
    deadline = time.monotonic() + 660
    try:
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError(f'Regtest exited with code {process.returncode}; inspect {state}/launcher.log')
            if ready(control):
                show(control)
                return
            time.sleep(0.5)
        raise TimeoutError(f'Startup timed out; inspect {state}/launcher.log')
    except BaseException:
        # Also clean up a interrupted startup; established stacks remain detached.
        if owned_process(control):
            process.terminate()
            process.wait(timeout=60)
        raise


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, TimeoutError, OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
