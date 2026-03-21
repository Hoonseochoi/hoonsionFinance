#!/usr/bin/env python3
"""
One-time migration: extract JSON from archive/가계_대시보드_v3.html
and write to db/transactions.csv and db/assets.csv
"""
import re, json, csv, os

WORKTREE = os.path.dirname(os.path.abspath(__file__))
HTML_PATH = os.path.join(WORKTREE, 'archive', '가계_대시보드_v3.html')
TX_PATH   = os.path.join(WORKTREE, 'db', 'transactions.csv')
ASSETS_PATH = os.path.join(WORKTREE, 'db', 'assets.csv')

# --- Extract RAW JSON from HTML ---
with open(HTML_PATH, encoding='utf-8') as f:
    html = f.read()

# Find: const RAW = {...};
match = re.search(r'const RAW\s*=\s*(\{.*?\});', html, re.DOTALL)
if not match:
    raise ValueError("Could not find 'const RAW = ...' in HTML")
RAW = json.loads(match.group(1))

# --- Write transactions.csv ---
TX_FIELDS = ['id','person','date','time','type','category','subcategory','desc','amount','currency','method','memo']

with open(TX_PATH, 'w', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, fieldnames=TX_FIELDS)
    w.writeheader()
    for tx in RAW['transactions']:
        w.writerow({
            'id':          tx['id'],
            'person':      tx['person'],
            'date':        tx['date'],
            'time':        tx.get('time', ''),
            'type':        tx['type'],
            'category':    tx.get('cat', tx.get('category', '')),
            'subcategory': tx.get('subcategory', ''),
            'desc':        tx.get('desc', ''),
            'amount':      tx['amount'],
            'currency':    tx.get('currency', 'KRW'),
            'method':      tx.get('method', ''),
            'memo':        tx.get('memo', ''),
        })

print(f"Written {len(RAW['transactions'])} transactions to {TX_PATH}")

# --- Write assets.csv ---
ASSETS_FIELDS = ['snapshot_date','person','total_assets','total_liabilities','net_assets','credit_score','dc_pension','irp_pension','investments_json','loans_json']

def assets_row(person_key, person):
    a = RAW.get(person_key, {})
    investments = a.get('investments', [])
    loans = a.get('loans', [])
    # snapshot_date may not exist in this version; default to 2026-03
    snapshot_date = a.get('snapshot_date', '2026-03')
    # dc/irp pension: check within the person's asset dict first, then top-level RAW
    if person == 'h':
        dc_pension  = a.get('h_dc',  RAW.get('h_dc',  0))
        irp_pension = a.get('h_irp', RAW.get('h_irp', 0))
    else:
        dc_pension  = 0
        irp_pension = 0
    return {
        'snapshot_date':    a.get('snapshot_date', '2026-03'),
        'person':           person,
        'total_assets':     a.get('total_assets', 0),
        'total_liabilities': a.get('total_liabilities', 0),
        'net_assets':       a.get('net_assets', 0),
        'credit_score':     a.get('credit_score', 0),
        'dc_pension':       dc_pension,
        'irp_pension':      irp_pension,
        'investments_json': json.dumps(investments, ensure_ascii=False),
        'loans_json':       json.dumps(loans, ensure_ascii=False),
    }

rows = []
if 'h_assets' in RAW:
    rows.append(assets_row('h_assets', 'h'))
if 'w_assets' in RAW:
    rows.append(assets_row('w_assets', 'w'))

with open(ASSETS_PATH, 'w', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, fieldnames=ASSETS_FIELDS)
    w.writeheader()
    w.writerows(rows)

print(f"Written {len(rows)} asset rows to {ASSETS_PATH}")
print("Migration complete.")
