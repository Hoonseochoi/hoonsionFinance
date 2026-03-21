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


def apply_overrides(transactions, overrides):
    """override 적용 + deleted 제거 → 정제된 트랜잭션 리스트."""
    result = []
    for t in transactions:
        ov = overrides.get(t['id'])
        if ov and ov['deleted']:
            continue
        tx = dict(t)
        if ov:
            if ov['cat']:  tx['cat']  = ov['cat']
            if ov['desc']: tx['desc'] = ov['desc']
        result.append(tx)
    return result


def compute_monthly(transactions):
    """월별 수입/지출/누적 집계. 이체 타입은 제외."""
    from collections import defaultdict
    monthly = defaultdict(lambda: {'total_income': 0, 'total_expense': 0})
    for t in transactions:
        if t['type'] == '이체':
            continue
        month = t['date'][:7]  # YYYY-MM
        if t['amount'] > 0:
            monthly[month]['total_income'] += t['amount']
        else:
            monthly[month]['total_expense'] += t['amount']

    result = []
    cumulative = 0
    for month in sorted(monthly.keys()):
        d = monthly[month]
        net = d['total_income'] + d['total_expense']
        cumulative += net
        result.append({
            'month': month,
            'total_income': d['total_income'],
            'total_expense': d['total_expense'],
            'cumulative': cumulative,
        })
    return result


def compute_cat_summary(transactions):
    """카테고리별 합계 집계. 지출 타입만, 이체 제외."""
    from collections import defaultdict
    summary = defaultdict(lambda: {'total': 0, 'h': 0, 'w': 0})
    for t in transactions:
        if t['type'] != '지출':
            continue
        cat = t['cat']
        amt = abs(t['amount'])
        summary[cat]['total'] += amt
        summary[cat][t['person']] += amt
    return dict(summary)


def compute_combined(h_assets, w_assets):
    """합산 재무 통계."""
    h_inv = sum(i.get('value', 0) for i in h_assets.get('investments', []))
    w_inv = sum(i.get('value', 0) for i in w_assets.get('investments', []))
    h_cost = sum(i.get('cost', 0) for i in h_assets.get('investments', []))
    w_cost = sum(i.get('cost', 0) for i in w_assets.get('investments', []))
    return {
        'net_assets': h_assets.get('net_assets', 0) + w_assets.get('net_assets', 0),
        'total_liabilities': h_assets.get('total_liabilities', 0) + w_assets.get('total_liabilities', 0),
        'invest_total_value': h_inv + w_inv,
        'invest_total_cost': h_cost + w_cost,
    }
