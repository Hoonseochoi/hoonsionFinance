import csv, json, os
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
import logging

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


def build_api_data():
    """전체 /api/data JSON 페이로드 빌드."""
    tx_rows    = read_csv(TX_PATH)
    asset_rows = read_csv(ASSETS_PATH)
    ov_rows    = read_csv(OV_PATH)

    transactions = parse_transactions(tx_rows)
    assets_by_person = parse_assets(asset_rows)
    overrides = parse_overrides(ov_rows)

    h_assets = assets_by_person.get('h', {
        'snapshot_date': '', 'total_assets': 0, 'total_liabilities': 0,
        'net_assets': 0, 'credit_score': 0, 'dc_pension': 0, 'irp_pension': 0,
        'investments': [], 'loans': []
    })
    w_assets = assets_by_person.get('w', {
        'snapshot_date': '', 'total_assets': 0, 'total_liabilities': 0,
        'net_assets': 0, 'credit_score': 0, 'dc_pension': 0, 'irp_pension': 0,
        'investments': [], 'loans': []
    })

    clean_txs = apply_overrides(transactions, overrides)
    monthly   = compute_monthly(clean_txs)
    combined  = compute_combined(h_assets, w_assets)
    cat_summary = compute_cat_summary(clean_txs)
    all_cats  = sorted({t['cat'] for t in clean_txs if t['cat']})

    # overrides를 기존 코드 호환 포맷으로 변환
    ov_dict = {}
    for tid, ov in overrides.items():
        if ov['deleted']:
            ov_dict[tid] = {'deleted': True}
        else:
            ov_dict[tid] = {'cat': ov['cat'], 'desc': ov['desc']}

    return {
        'transactions': clean_txs,
        'h_assets': h_assets,
        'w_assets': w_assets,
        'h_dc':  h_assets['dc_pension'],
        'h_irp': h_assets['irp_pension'],
        'combined': combined,
        'monthly': monthly,
        'cumulative': [{'month': m['month'], 'cumulative': m['cumulative']} for m in monthly],
        'cat_summary': cat_summary,
        'all_cats': all_cats,
        'overrides': ov_dict,
        'meta': {
            'last_updated': datetime.now().isoformat(timespec='seconds'),
            'tx_count': {
                'h': sum(1 for t in transactions if t['person'] == 'h'),
                'w': sum(1 for t in transactions if t['person'] == 'w'),
            }
        }
    }


def _write_overrides(ov_dict):
    """overrides.csv 전체 재작성."""
    with open(OV_PATH, 'w', encoding='utf-8', newline='') as f:
        w = csv.writer(f)
        w.writerow(['id', 'cat', 'desc', 'deleted', 'updated_at'])
        for tid, ov in ov_dict.items():
            w.writerow([
                tid,
                ov.get('cat', ''),
                ov.get('desc', ''),
                'true' if ov.get('deleted') else 'false',
                datetime.now().isoformat(timespec='seconds'),
            ])


def save_override(tx_id, cat, desc):
    """단건 수정 저장."""
    rows = read_csv(OV_PATH)
    ov_dict = parse_overrides(rows)
    existing = ov_dict.get(tx_id, {})
    ov_dict[tx_id] = {
        'cat':  cat  if cat  is not None else existing.get('cat', ''),
        'desc': desc if desc is not None else existing.get('desc', ''),
        'deleted': existing.get('deleted', False),
    }
    _write_overrides(ov_dict)


def save_delete(tx_id):
    """단건 삭제 저장."""
    rows = read_csv(OV_PATH)
    ov_dict = parse_overrides(rows)
    ov_dict[tx_id] = {'cat': '', 'desc': '', 'deleted': True}
    _write_overrides(ov_dict)


def save_bulk_override(tx_ids, cat, desc):
    """일괄 수정 저장. cat/desc 중 None은 기존값 유지."""
    if cat is None and desc is None:
        return  # no-op
    rows = read_csv(OV_PATH)
    ov_dict = parse_overrides(rows)
    for tid in tx_ids:
        existing = ov_dict.get(tid, {})
        ov_dict[tid] = {
            'cat':  cat  if cat  is not None else existing.get('cat', ''),
            'desc': desc if desc is not None else existing.get('desc', ''),
            'deleted': existing.get('deleted', False),
        }
    _write_overrides(ov_dict)


LOG_PATH = os.path.join(DB_DIR, 'serve.log')
logging.basicConfig(
    filename=LOG_PATH, level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s'
)

DASHBOARD_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'dashboard.html')
PORT = 8080


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        logging.info(fmt % args)

    def _json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', len(body))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self):
        length = int(self.headers.get('Content-Length', 0))
        return json.loads(self.rfile.read(length))

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_GET(self):
        if self.path == '/api/data':
            try:
                self._json(build_api_data())
            except Exception as e:
                logging.error('api/data error: %s', e, exc_info=True)
                self._json({'error': str(e)}, 500)
        elif self.path in ('/', '/dashboard.html'):
            try:
                with open(DASHBOARD_PATH, 'rb') as f:
                    body = f.read()
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', len(body))
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(body)
            except FileNotFoundError:
                self._json({'error': 'dashboard.html not found'}, 404)
        else:
            self._json({'error': 'not found'}, 404)

    def do_POST(self):
        try:
            body = self._read_body()
        except Exception:
            self._json({'error': 'invalid json'}, 400)
            return

        try:
            if self.path == '/api/override':
                save_override(body['id'], body.get('cat'), body.get('desc'))
                self._json({'ok': True})
            elif self.path == '/api/delete':
                save_delete(body['id'])
                self._json({'ok': True})
            elif self.path == '/api/bulk-override':
                save_bulk_override(body['ids'], body.get('cat'), body.get('desc'))
                self._json({'ok': True})
            else:
                self._json({'error': 'not found'}, 404)
        except KeyError as e:
            self._json({'error': f'missing field: {e}'}, 400)
        except Exception as e:
            logging.error('POST %s error: %s', self.path, e, exc_info=True)
            self._json({'error': str(e)}, 500)


if __name__ == '__main__':
    try:
        server = HTTPServer(('localhost', PORT), Handler)
        logging.info('서버 시작: http://localhost:%d', PORT)
        print(f'대시보드: http://localhost:{PORT}')
        server.serve_forever()
    except OSError as e:
        logging.error('서버 시작 실패 (포트 %d 사용 중?): %s', PORT, e)
        raise
