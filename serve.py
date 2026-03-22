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
            'month': r['date'][:7],
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


def parse_assets_history(rows):
    """모든 스냅샷 반환 (날짜순 정렬). 자산 추이 차트용."""
    history = []
    for r in rows:
        try:
            history.append({
                'snapshot_date': r['snapshot_date'],
                'person': r['person'],
                'net_assets': int(float(r['net_assets'])),
                'total_assets': int(float(r['total_assets'])),
                'total_liabilities': int(float(r['total_liabilities'])),
            })
        except (ValueError, TypeError):
            continue
    return sorted(history, key=lambda x: x['snapshot_date'])


def parse_overrides(rows):
    """CSV 행 리스트 → {tx_id: override_dict} 딕셔너리."""
    result = {}
    for r in rows:
        result[r['id']] = {
            'cat': r.get('cat', ''),
            'desc': r.get('desc', ''),
            'amount': r.get('amount', ''),   # 신규
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
            if ov.get('amount'):
                try:
                    tx['_orig_amount'] = tx['amount']
                    tx['amount'] = int(float(ov['amount']))
                except (ValueError, TypeError):
                    pass
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


def get_ai_insights(month, spending_data, income, expense):
    """Claude API로 지출 성향 분석 인사이트 생성."""
    import urllib.request, urllib.error, re

    # API 키: 환경변수 우선, 없으면 config.json
    api_key = os.environ.get('ANTHROPIC_API_KEY', '')
    if not api_key:
        cfg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')
        if os.path.exists(cfg_path):
            try:
                with open(cfg_path, encoding='utf-8') as f:
                    cfg = json.load(f)
                api_key = cfg.get('ANTHROPIC_API_KEY', '')
            except Exception:
                pass

    if not api_key:
        return {'error': 'API_KEY_MISSING'}

    save_rate = round((income - abs(expense)) / income * 100) if income > 0 else 0
    cat_lines = '\n'.join([
        f"- {cat}: {int(v['total']):,}원 (훈서 {int(v.get('h',0)):,} / 시온 {int(v.get('w',0)):,})"
        for cat, v in sorted(spending_data.items(), key=lambda x: -x[1]['total'])
    ])

    prompt = f"""한국 맞벌이 부부(훈서, 시온)의 {month} 가계 지출 데이터입니다.

수입: {income:,}원 | 지출: {abs(expense):,}원 | 저축률: {save_rate}%

카테고리별 지출:
{cat_lines}

위 데이터를 분석해서 아래 JSON을 반드시 한국어로만 반환하세요 (코드블록 없이 순수 JSON만):
{{
  "summary": "이달 가계 한 줄 핵심 요약 (구체적 수치 포함)",
  "patterns": [
    "주목할 지출 패턴 1 (긍정적 또는 부정적, 구체적 금액 포함)",
    "주목할 지출 패턴 2",
    "주목할 지출 패턴 3"
  ],
  "tips": [
    "다음 달 절약 팁 1 (구체적)",
    "다음 달 절약 팁 2 (구체적)"
  ],
  "score": {{
    "value": 3,
    "reason": "가계 건전성 점수 (1-5) 이유"
  }},
  "alert": "특이사항 또는 주의사항 (없으면 빈 문자열)"
}}"""

    payload = json.dumps({
        'model': 'claude-3-5-haiku-20241022',
        'max_tokens': 1000,
        'messages': [{'role': 'user', 'content': prompt}]
    }).encode()

    req = urllib.request.Request(
        'https://api.anthropic.com/v1/messages',
        data=payload,
        headers={
            'x-api-key': api_key,
            'anthropic-version': '2023-06-01',
            'content-type': 'application/json',
        },
        method='POST'
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
            text = result['content'][0]['text'].strip()
            json_match = re.search(r'\{.*\}', text, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
            return {'error': 'PARSE_ERROR', 'raw': text[:200]}
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:300]
        logging.error('AI insights HTTP error: %s %s', e.code, body)
        return {'error': f'HTTP_{e.code}', 'detail': body}
    except Exception as e:
        logging.error('AI insights error: %s', e)
        return {'error': str(e)}


def build_api_data():
    """전체 /api/data JSON 페이로드 빌드."""
    tx_rows    = read_csv(TX_PATH)
    asset_rows = read_csv(ASSETS_PATH)
    ov_rows    = read_csv(OV_PATH)

    transactions = parse_transactions(tx_rows)
    assets_by_person = parse_assets(asset_rows)
    asset_history = parse_assets_history(asset_rows)
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

    from collections import defaultdict as _dd
    _by_date = _dd(dict)
    for r in asset_history:
        _by_date[r['snapshot_date']][r['person']] = r
    assets_timeline = [
        {
            'date': date,
            'h_net': _by_date[date].get('h', {}).get('net_assets', 0),
            'h_total': _by_date[date].get('h', {}).get('total_assets', 0),
            'w_net': _by_date[date].get('w', {}).get('net_assets', 0),
            'w_total': _by_date[date].get('w', {}).get('total_assets', 0),
            'combined_net': (
                _by_date[date].get('h', {}).get('net_assets', 0) +
                _by_date[date].get('w', {}).get('net_assets', 0)
            ),
        }
        for date in sorted(_by_date.keys())
    ]

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
        'assets_timeline': assets_timeline,
        'meta': {
            'last_updated': datetime.now().isoformat(timespec='seconds'),
            'tx_count': {
                'h': sum(1 for t in transactions if t['person'] == 'h'),
                'w': sum(1 for t in transactions if t['person'] == 'w'),
            }
        }
    }


def update_asset(person, asset_type, action, index, data):
    """자산 항목 업데이트. asset_type: investment|loan|pension, action: update|delete"""
    rows = read_csv(ASSETS_PATH)
    if not rows:
        return False

    # person의 최신 snapshot row 인덱스 찾기
    latest_idx = None
    latest_date = ''
    for i, r in enumerate(rows):
        if r['person'] == person and r['snapshot_date'] >= latest_date:
            latest_date = r['snapshot_date']
            latest_idx = i

    if latest_idx is None:
        return False

    fields = ['snapshot_date', 'person', 'total_assets', 'total_liabilities',
              'net_assets', 'credit_score', 'dc_pension', 'irp_pension',
              'investments_json', 'loans_json']
    row = dict(rows[latest_idx])

    if asset_type == 'investment':
        items = json.loads(row.get('investments_json') or '[]')
        if action == 'delete' and 0 <= index < len(items):
            items.pop(index)
        elif action == 'update' and 0 <= index < len(items):
            for k, v in data.items():
                if v is not None:
                    items[index][k] = v
        row['investments_json'] = json.dumps(items, ensure_ascii=False)

    elif asset_type == 'loan':
        items = json.loads(row.get('loans_json') or '[]')
        if action == 'delete' and 0 <= index < len(items):
            items.pop(index)
        elif action == 'update' and 0 <= index < len(items):
            for k, v in data.items():
                if v is not None:
                    items[index][k] = v
        row['loans_json'] = json.dumps(items, ensure_ascii=False)

    elif asset_type == 'pension':
        if data.get('dc_pension') is not None:
            row['dc_pension'] = str(int(float(data['dc_pension'])))
        if data.get('irp_pension') is not None:
            row['irp_pension'] = str(int(float(data['irp_pension'])))

    new_rows = list(rows)
    new_rows[latest_idx] = row
    with open(ASSETS_PATH, 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(new_rows)
    return True


def _write_overrides(ov_dict):
    """overrides.csv 전체 재작성."""
    with open(OV_PATH, 'w', encoding='utf-8', newline='') as f:
        w = csv.writer(f)
        w.writerow(['id', 'cat', 'desc', 'amount', 'deleted', 'updated_at'])
        for tid, ov in ov_dict.items():
            w.writerow([
                tid,
                ov.get('cat', ''),
                ov.get('desc', ''),
                ov.get('amount', ''),
                'true' if ov.get('deleted') else 'false',
                datetime.now().isoformat(timespec='seconds'),
            ])


def save_override(tx_id, cat, desc, amount=None):
    """단건 수정 저장."""
    rows = read_csv(OV_PATH)
    ov_dict = parse_overrides(rows)
    existing = ov_dict.get(tx_id, {})
    ov_dict[tx_id] = {
        'cat':  cat  if cat  is not None else existing.get('cat', ''),
        'desc': desc if desc is not None else existing.get('desc', ''),
        'amount': str(int(float(amount))) if amount is not None else existing.get('amount', ''),
        'deleted': existing.get('deleted', False),
    }
    _write_overrides(ov_dict)


def save_delete(tx_id):
    """단건 삭제 저장."""
    rows = read_csv(OV_PATH)
    ov_dict = parse_overrides(rows)
    ov_dict[tx_id] = {'cat': '', 'desc': '', 'deleted': True}
    _write_overrides(ov_dict)


def save_bulk_override(tx_ids, cat, desc, amount=None):
    """일괄 수정 저장. cat/desc/amount 중 None은 기존값 유지."""
    if cat is None and desc is None and amount is None:
        return
    rows = read_csv(OV_PATH)
    ov_dict = parse_overrides(rows)
    for tid in tx_ids:
        existing = ov_dict.get(tid, {})
        ov_dict[tid] = {
            'cat':    cat    if cat    is not None else existing.get('cat', ''),
            'desc':   desc   if desc   is not None else existing.get('desc', ''),
            'amount': str(int(float(amount))) if amount is not None else existing.get('amount', ''),
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
                save_override(body['id'], body.get('cat'), body.get('desc'), body.get('amount'))
                self._json({'ok': True})
            elif self.path == '/api/delete':
                save_delete(body['id'])
                self._json({'ok': True})
            elif self.path == '/api/bulk-override':
                save_bulk_override(body['ids'], body.get('cat'), body.get('desc'), body.get('amount'))
                self._json({'ok': True})
            elif self.path == '/api/update-asset':
                ok = update_asset(
                    body['person'], body['type'], body['action'],
                    body.get('index', -1), body.get('data', {})
                )
                self._json({'ok': ok})
            elif self.path == '/api/ai-insights':
                month = body.get('month', '')
                spending = body.get('spending', {})
                income = body.get('income', 0)
                expense = body.get('expense', 0)
                result = get_ai_insights(month, spending, income, expense)
                self._json(result)
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
