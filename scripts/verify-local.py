#!/usr/bin/env python3
"""Read-only checks for the running real wallet stack and notes query filter."""
import json
from pathlib import Path
import shlex
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
values = {}
for line in (ROOT / 'data/local/current.env').read_text().splitlines():
    parts = shlex.split(line, comments=True)
    if parts and parts[0] == 'export':
        key, value = parts[1].split('=', 1)
        values[key] = value

def gql(url, query, variables=None):
    req = urllib.request.Request(url, json.dumps({'query': query, 'variables': variables or {}}).encode(), {'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=120) as response:
        result = json.load(response)
    if result.get('errors'):
        raise RuntimeError(result['errors'])
    return result['data']

main = values['BTCPAY_TEST_GRAPHQL']
cashcow = values['BTCPAY_TEST_CASHCOW_GRAPHQL']
for name, url in (('main', main), ('cashcow', cashcow)):
    height = gql(url, 'query { currentHeight }')['currentHeight']
    assert height >= 300, name + ' is not ready'
    print(f'{name}: height {height}')
funding = gql(cashcow, 'query { accounts(accountFilter: {id: 1}) { balance } }')['accounts'][0]['balance']
assert float(funding) > 0, 'cashcow is not funded'
accounts = gql(main, 'query { accounts { id seed ufvk } }')['accounts']
watch_only = [a for a in accounts if a['ufvk'] == values['BTCPAY_TEST_VIEWING_KEY'] and a['seed'] is None]
assert watch_only, 'Expected an imported watch-only receiver'
account = watch_only[0]['id']
all_notes = gql(main, 'query($id: Int!) { notesByAccount(idAccount: $id) { id diversifierIndex } }', {'id': account})['notesByAccount']
assert all_notes, 'Expected at least one received/confirmed note'
query = 'query($id: Int!, $indices: [BigDecimal!]) { notesByAccount(idAccount: $id, diversifierIndices: $indices) { id diversifierIndex } }'
assert gql(main, query, {'id': account, 'indices': []})['notesByAccount'] == []
assert gql(main, query, {'id': account, 'indices': None})['notesByAccount'] == all_notes
index = next(n['diversifierIndex'] for n in all_notes if n['diversifierIndex'] is not None)
expected = [n for n in all_notes if n['diversifierIndex'] == index]
actual = gql(main, query, {'id': account, 'indices': [str(index)]})['notesByAccount']
assert actual == expected, 'Matching index filter returned incorrect notes'
missing = str(max(int(n['diversifierIndex']) for n in all_notes if n['diversifierIndex'] is not None) + 1)
assert gql(main, query, {'id': account, 'indices': [missing]})['notesByAccount'] == []
print('PASS: funded cashcow, watch-only receiver, omitted/null/empty/matching/nonmatching index filters')
