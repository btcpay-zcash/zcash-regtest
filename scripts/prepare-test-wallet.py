#!/usr/bin/env python3
"""Generate a receiver in the cashcow wallet and export its watch-only key locally."""
import argparse
import json
import os
from pathlib import Path
import shlex
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parent.parent
URL = os.environ.get('BTCPAY_TEST_CASHCOW_GRAPHQL', 'http://127.0.0.1:18082/graphql')

def gql(query, variables=None):
    request = urllib.request.Request(URL, json.dumps({'query': query, 'variables': variables or {}}).encode(), {'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=120) as response:
        result = json.load(response)
    if result.get('errors'):
        raise RuntimeError('Wallet request failed: ' + str(result['errors']))
    return result['data']

parser = argparse.ArgumentParser()
parser.add_argument('--new', action='store_true', help='Create a fresh receiver for a new integration-test run')
args = parser.parse_args()

accounts = gql('query { accounts { id name } }')['accounts']
if not any(a['id'] == 1 and a['name'] == 'cashcow' for a in accounts):
    raise RuntimeError('Start BTCPay once to create/fund cashcow account 1 before generating the receiver')
receivers = [a for a in accounts if a['name'] == 'btcpay-test-receiver']
if receivers and not args.new:
    account = receivers[0]['id']
else:
    account = gql('mutation($a: NewAccount!) { createAccount(newAccount: $a) }', {'a': {'name': 'btcpay-test-receiver' + ('-' + uuid.uuid4().hex if args.new else ''), 'key': '', 'aindex': 0, 'birth': 1, 'useInternal': False}})['createAccount']
export = gql('query($f: AccountFilter) { accounts(accountFilter: $f) { seed ufvk } }', {'f': {'id': account}})['accounts'][0]
if not export['seed'] or not export['ufvk'].startswith('uviewregtest'):
    raise RuntimeError('Expected a generated seed and regtest UFVK')
values = {
    'BTCPAY_TEST_GRAPHQL': 'http://127.0.0.1:18081/graphql',
    'BTCPAY_TEST_CASHCOW_GRAPHQL': URL,
    'BTCPAY_TEST_ZEBRA_RPC': 'http://127.0.0.1:18232',
    'BTCPAY_TEST_VIEWING_KEY': export['ufvk'],
    'BTCPAY_TEST_RECEIVER_SEED': export['seed'],
    'BTCPAY_TEST_RECEIVER_ACCOUNT': str(account),
}
directory = ROOT / 'data/local'
directory.mkdir(parents=True, exist_ok=True)
for path in (directory / f'receiver-{account}.env', directory / 'current.env'):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, 'w') as output:
        output.write('# Local regtest fixture; generated private test keys. Do not commit.\n')
        for key, value in values.items():
            output.write(f'export {key}={shlex.quote(value)}\n')
print(f'Receiver account {account}; seed and viewing key saved in {directory / "current.env"} (mode 0600)')
