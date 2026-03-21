import csv, json, os
from datetime import datetime

DB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'db')
TX_PATH     = os.path.join(DB_DIR, 'transactions.csv')
ASSETS_PATH = os.path.join(DB_DIR, 'assets.csv')
OV_PATH     = os.path.join(DB_DIR, 'overrides.csv')


def read_csv(path):
    """CSV 파일을 읽어 DictReader 행 리스트 반환. 파일 없으면 빈 리스트."""
    if not os.path.exists(path):
        return []
    with open(path, encoding='utf-8', newline='') as f:
        return list(csv.DictReader(f))


def parse_transactions(rows):
    """CSV 행 리스트 → 트랜잭션 딕셔너리 리스트."""
    result = []
    for r in rows:
        result.append({
            'id': r['id'],
            'person': r['person'],
            'date': r['date'],
            'time': r.get('time', ''),
            'type': r['type'],
            'cat': r['category'],
            'subcat': r.get('subcategory', ''),
            'desc': r['desc'],
            'amount': int(float(r['amount'])),
            'currency': r.get('currency', 'KRW'),
            'method': r.get('method', ''),
            'memo': r.get('memo', ''),
        })
    return result


def parse_assets(rows):
    """CSV 행 리스트 → {person: asset_dict} 딕셔너리."""
    result = {}
    for r in rows:
        p = r['person']
        result[p] = {
            'snapshot_date': r['snapshot_date'],
            'total_assets': int(float(r['total_assets'])),
            'total_liabilities': int(float(r['total_liabilities'])),
            'net_assets': int(float(r['net_assets'])),
            'credit_score': int(r['credit_score']) if r['credit_score'] else 0,
            'dc_pension': int(float(r.get('dc_pension', 0) or 0)),
            'irp_pension': int(float(r.get('irp_pension', 0) or 0)),
            'investments': json.loads(r['investments_json'] or '[]'),
            'loans': json.loads(r['loans_json'] or '[]'),
        }
    return result


def parse_overrides(rows):
    """CSV 행 리스트 → {tx_id: override_dict} 딕셔너리."""
    result = {}
    for r in rows:
        result[r['id']] = {
            'cat': r.get('cat', ''),
            'desc': r.get('desc', ''),
            'deleted': r.get('deleted', 'false').lower() == 'true',
        }
    return result
