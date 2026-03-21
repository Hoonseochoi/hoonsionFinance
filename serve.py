import csv, json, os

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
        try:
            amount = int(float(r['amount']))
        except (ValueError, TypeError):
            print(f"WARNING: parse_transactions — amount 변환 실패, 행 건너뜀: {r.get('id', '?')}")
            continue
        result.append({
            'id': r['id'],
            'person': r['person'],
            'date': r['date'],
            'time': r.get('time', ''),
            'type': r['type'],
            'cat': r['category'],
            'subcat': r.get('subcategory', ''),
            'desc': r['desc'],
            'amount': amount,
            'currency': r.get('currency', 'KRW'),
            'method': r.get('method', ''),
            'memo': r.get('memo', ''),
        })
    return result


def parse_assets(rows):
    """CSV 행 리스트 → {person: asset_dict} 딕셔너리. 동일 person은 최신 snapshot_date만 유지."""
    result = {}
    latest_dates = {}
    for r in rows:
        p = r['person']
        snapshot_date = r['snapshot_date']
        # 이미 더 최신 스냅샷이 있으면 건너뜀
        if p in latest_dates and snapshot_date < latest_dates[p]:
            continue
        try:
            entry = {
                'snapshot_date': snapshot_date,
                'total_assets': int(float(r['total_assets'])),
                'total_liabilities': int(float(r['total_liabilities'])),
                'net_assets': int(float(r['net_assets'])),
                'credit_score': int(r['credit_score']) if r['credit_score'] else 0,
                'dc_pension': int(float(r.get('dc_pension', 0) or 0)),
                'irp_pension': int(float(r.get('irp_pension', 0) or 0)),
                'investments': json.loads(r['investments_json'] or '[]'),
                'loans': json.loads(r['loans_json'] or '[]'),
            }
        except (ValueError, TypeError, json.JSONDecodeError):
            print(f"WARNING: parse_assets — 변환 실패, 행 건너뜀: person={p}, snapshot_date={snapshot_date}")
            continue
        result[p] = entry
        latest_dates[p] = snapshot_date
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
