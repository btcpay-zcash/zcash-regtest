#!/usr/bin/env python3
"""Fresh, disposable local chain; no Docker or Python packages required."""
import argparse
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import tempfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
os.environ['PATH'] = str(ROOT / 'tools/bin') + os.pathsep + os.environ['PATH']
RPC = 'http://127.0.0.1:18232'
GQL = 'http://127.0.0.1:18081/graphql'
CASHCOW_GQL = 'http://127.0.0.1:18082/graphql'
processes = []
logs = []


def request(url, body):
    req = urllib.request.Request(url, json.dumps(body).encode(), {'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=120) as response:
        result = json.load(response)
    if result.get('errors') or result.get('error'):
        raise RuntimeError(result)
    return result


def rpc(method, params):
    return request(RPC, {'jsonrpc': '1.0', 'id': 'regtest', 'method': method, 'params': params})['result']


def gql(query, variables=None, url=GQL):
    return request(url, {'query': query, 'variables': variables or {}})['data']


def wait_for(check, description):
    deadline = time.monotonic() + 600
    last = None
    while time.monotonic() < deadline:
        if any(p.poll() is not None for p in processes):
            raise RuntimeError('A regtest process exited; inspect logs')
        try:
            if check():
                return
        except Exception as error:
            last = error
        time.sleep(1)
    raise TimeoutError(f'{description}: {last}')


def start(name, args, state):
    log = open(state / f'{name}.log', 'a')
    logs.append(log)
    processes.append(subprocess.Popen(args, cwd=state, stdout=log, stderr=subprocess.STDOUT))


def main():
    for name in ('zebrad', 'lightwalletd', 'zkool_graphql'):
        if not shutil.which(name):
            raise RuntimeError(f'Missing {name}; run scripts/install-tools.sh first')
    # Never attach to or kill an unrelated node.
    for port in (18232, 18233, 8137, 18081, 18082):
        with socket.socket() as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            probe.bind(('127.0.0.1', port))
    parent = ROOT / 'data/local'
    parent.mkdir(parents=True, exist_ok=True)
    parser = argparse.ArgumentParser()
    parser.add_argument('--zkool-binary', type=Path, help='Wallet binary under test (defaults to installed test tools)')
    parser.add_argument('--state-dir', type=Path, help='Resume an existing local run instead of creating fresh state')
    parser.add_argument('--control-token', help=argparse.SUPPRESS)
    args = parser.parse_args()
    state = args.state_dir.resolve() if args.state_dir else Path(tempfile.mkdtemp(prefix='run-', dir=parent))
    if not state.is_dir():
        raise RuntimeError('State directory does not exist')
    print(f'Regtest state and logs: {state}', flush=True)
    (state / 'zebra.toml').write_text(f'''[network]
network = "Regtest"
listen_addr = "127.0.0.1:18233"
[state]
cache_dir = "{state / 'chain'}"
[rpc]
listen_addr = "127.0.0.1:18232"
enable_cookie_auth = false
[mining]
miner_address = "tmQ1BiNRfsvT6eMkJ5n7nMZsbz1PGwCs1Zs"
[network.testnet_parameters.activation_heights]
"NU6.2" = 1
"NU6.3" = 250
[[network.testnet_parameters.lockbox_disbursements]]
address = "t27eWDgjFYJGVXmzrXeVjnb5J3uXDM9xH9v"
amount = 0
''')
    (state / 'zebra.conf').write_text('rpcuser=user\nrpcpassword=password\nrpcport=18232\nregtest=1\n')
    start('zebra', ['zebrad', '-c', str(state / 'zebra.toml'), 'start'], state)
    wait_for(lambda: rpc('getblockchaininfo', []), 'Zebra readiness')
    height = rpc('getblockchaininfo', [])['blocks']
    if height < 300:
        rpc('generate', [300 - height])
    start('lightwalletd', ['lightwalletd', '--no-tls-very-insecure', '--data-dir=' + str(state / 'lwd'), '--grpc-bind-addr=127.0.0.1:8137', '--zcash-conf-path=' + str(state / 'zebra.conf'), '--log-file=/dev/stdout'], state)
    for name, port, url in (('main', 18081, GQL), ('cashcow', 18082, CASHCOW_GQL)):
        start(name, [str(args.zkool_binary.resolve()) if args.zkool_binary else 'zkool_graphql', '--config-path', str(state / 'zkool.toml'), '--db-path', str(state / f'{name}-regtest.db'), '--coin', '2', '--lwd-url', 'http://127.0.0.1:8137', '--port', str(port), '--bind-address', '127.0.0.1', '--allow-unauthenticated', '--allow-unencrypted-database'], state)
        wait_for(lambda: gql('query { currentHeight }', url=url)['currentHeight'] >= 300, f'{url} readiness')
    (state / 'ready.json').write_text(json.dumps({'pid': os.getpid(), 'token': args.control_token}))
    print(f'Regtest ready: main {GQL}, cashcow {CASHCOW_GQL}\nBTCPay cheatmode creates and funds its cashcow. Ctrl-C stops the stack.', flush=True)
    while True:
        if any(p.poll() is not None for p in processes):
            raise RuntimeError('Regtest process exited')
        time.sleep(1)


if __name__ == '__main__':
    def stop(*_):
        raise KeyboardInterrupt()
    signal.signal(signal.SIGTERM, stop)
    try:
        main()
    except KeyboardInterrupt:
        pass
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
        for log in logs:
            log.close()
