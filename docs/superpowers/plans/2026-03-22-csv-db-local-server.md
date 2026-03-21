# CSV DB + 로컬 서버 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** CSV 파일을 단일 진실 소스로 하는 로컬 서버 기반 가계 대시보드 시스템 구축

**Architecture:** serve.py가 db/*.csv를 읽어 집계 후 JSON API로 제공. dashboard.html은 fetch()로 데이터를 받아 렌더링. 대시보드 편집 내용은 POST API를 통해 db/overrides.csv에 영구 저장.

**Tech Stack:** Python 3 (표준 라이브러리: http.server, csv, json, unittest), HTML/CSS/JS, Chart.js 4.4.1

**Spec:** `docs/superpowers/specs/2026-03-22-csv-database-architecture-design.md`

---

## 파일 맵

| 파일 | 상태 | 역할 |
|------|------|------|
| `db/transactions.csv` | 신규 | 전체 거래내역 DB |
| `db/assets.csv` | 신규 | 월별 자산 스냅샷 DB |
| `db/overrides.csv` | 신규 | 대시보드 편집 내용 |
| `serve.py` | 신규 | HTTP 서버 + API + 집계 로직 |
| `dashboard.html` | 신규 (v3 기반) | 대시보드 UI |
| `start_server.bat` | 신규 | Windows 자동 시작 배치 |
| `tests/test_serve.py` | 신규 | serve.py 유닛 테스트 |
| `archive/` | 신규 폴더 | 기존 파일 보관 |

---

## Task 1: db/ 폴더 및 빈 CSV 파일 생성

**Files:**
- Create: `db/transactions.csv`
- Create: `db/assets.csv`
- Create: `db/overrides.csv`

- [ ] **Step 1: db/ 디렉토리와 헤더만 있는 CSV 파일 생성**

```bash
mkdir db
```

`db/transactions.csv` 내용:
```
id,person,date,time,type,category,subcategory,desc,amount,currency,method,memo
```

`db/assets.csv` 내용:
```
snapshot_date,person,total_assets,total_liabilities,net_assets,credit_score,dc_pension,irp_pension,investments_json,loans_json
```

`db/overrides.csv` 내용:
```
id,cat,desc,deleted,updated_at
```

- [ ] **Step 2: .gitignore에 db/*.csv 추가 (개인 금융 데이터 보호)**

`.gitignore`에 추가:
```
db/transactions.csv
db/assets.csv
db/overrides.csv
db/serve.log
```

- [ ] **Step 3: 커밋**

```bash
git add db/.gitkeep .gitignore
git commit -m "chore: db/ 디렉토리 및 CSV 스키마 초기화"
```

---

## Task 2: serve.py — CSV 파싱 유틸리티 (TDD)

**Files:**
- Create: `serve.py`
- Create: `tests/test_serve.py`

- [ ] **Step 1: tests/ 폴더 및 테스트 파일 생성**

```bash
mkdir tests
```

`tests/test_serve.py`:
```python
import sys, os, json, csv, io
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# ── 테스트용 픽스처 ──────────────────────────────────────────
SAMPLE_TRANSACTIONS = """id,person,date,time,type,category,subcategory,desc,amount,currency,method,memo
h_0,h,2026-01-05,10:00,지출,식비,,스타벅스,-5000,KRW,카드,
h_1,h,2026-01-10,15:00,수입,급여,,메리츠화재,4500000,KRW,이체,
w_0,w,2026-01-07,09:00,지출,교통,,K패스,-1500,KRW,카드,
"""

SAMPLE_ASSETS = """snapshot_date,person,total_assets,total_liabilities,net_assets,credit_score,dc_pension,irp_pension,investments_json,loans_json
2026-01,h,300000000,200000000,100000000,974,122764978,7050000,"[{""name"":""메리츠금융지주"",""firm"":""키움"",""value"":48770000,""cost"":23940000,""rate"":103.71}]","[{""name"":""KB전세"",""balance"":216000000,""rate"":4.42}]"
2026-01,w,90000000,0,90000000,1000,0,0,"[]","[]"
"""

SAMPLE_OVERRIDES = """id,cat,desc,deleted,updated_at
h_0,금융,아이엠삼송 전세이자,false,2026-01-15T10:00:00
"""

import unittest

class TestCSVParsing(unittest.TestCase):
    def setUp(self):
        import serve
        self.serve = serve
        # 임시 CSV 파일들을 문자열로 패치
        self.tx_rows = list(csv.DictReader(io.StringIO(SAMPLE_TRANSACTIONS)))
        self.asset_rows = list(csv.DictReader(io.StringIO(SAMPLE_ASSETS)))
        self.ov_rows = list(csv.DictReader(io.StringIO(SAMPLE_OVERRIDES)))

    def test_parse_transactions_returns_list(self):
        result = self.serve.parse_transactions(self.tx_rows)
        self.assertEqual(len(result), 3)

    def test_parse_transactions_amount_is_int(self):
        result = self.serve.parse_transactions(self.tx_rows)
        self.assertIsInstance(result[0]['amount'], int)
        self.assertEqual(result[0]['amount'], -5000)

    def test_parse_assets_returns_dict_by_person(self):
        result = self.serve.parse_assets(self.asset_rows)
        self.assertIn('h', result)
        self.assertIn('w', result)

    def test_parse_assets_investments_json_decoded(self):
        result = self.serve.parse_assets(self.asset_rows)
        self.assertIsInstance(result['h']['investments'], list)
        self.assertEqual(result['h']['investments'][0]['name'], '메리츠금융지주')

    def test_parse_overrides_returns_dict_by_id(self):
        result = self.serve.parse_overrides(self.ov_rows)
        self.assertIn('h_0', result)
        self.assertEqual(result['h_0']['cat'], '금융')

    def test_parse_overrides_deleted_is_bool(self):
        result = self.serve.parse_overrides(self.ov_rows)
        self.assertFalse(result['h_0']['deleted'])

if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

```bash
python -m pytest tests/test_serve.py -v
```
Expected: `ModuleNotFoundError: No module named 'serve'` 또는 `AttributeError`

- [ ] **Step 3: serve.py 파싱 함수 구현**

`serve.py` (파싱 함수만):
```python
import csv, json, os
from datetime import datetime

DB_DIR = os.path.join(os.path.dirname(__file__), 'db')
TX_PATH    = os.path.join(DB_DIR, 'transactions.csv')
ASSETS_PATH = os.path.join(DB_DIR, 'assets.csv')
OV_PATH    = os.path.join(DB_DIR, 'overrides.csv')


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
```

- [ ] **Step 4: 테스트 실행 — 통과 확인**

```bash
python -m pytest tests/test_serve.py -v
```
Expected: 6개 PASS

- [ ] **Step 5: 커밋**

```bash
git add serve.py tests/test_serve.py
git commit -m "feat: serve.py CSV 파싱 함수 구현 (TDD)"
```

---

## Task 3: serve.py — 집계 로직 (TDD)

**Files:**
- Modify: `serve.py`
- Modify: `tests/test_serve.py`

- [ ] **Step 1: 집계 테스트 추가** (`tests/test_serve.py` 끝에 추가)

```python
class TestAggregation(unittest.TestCase):
    def setUp(self):
        import serve
        self.serve = serve
        self.transactions = serve.parse_transactions(
            list(csv.DictReader(io.StringIO(SAMPLE_TRANSACTIONS)))
        )
        self.overrides = serve.parse_overrides(
            list(csv.DictReader(io.StringIO(SAMPLE_OVERRIDES)))
        )

    def test_apply_overrides_changes_cat(self):
        result = self.serve.apply_overrides(self.transactions, self.overrides)
        # h_0의 cat이 override로 '금융'으로 바뀌어야 함
        h0 = next(t for t in result if t['id'] == 'h_0')
        self.assertEqual(h0['cat'], '금융')

    def test_apply_overrides_excludes_deleted(self):
        ovs = {'h_1': {'cat': '', 'desc': '', 'deleted': True}}
        result = self.serve.apply_overrides(self.transactions, ovs)
        ids = [t['id'] for t in result]
        self.assertNotIn('h_1', ids)

    def test_compute_monthly_groups_by_month(self):
        txs = self.serve.apply_overrides(self.transactions, {})
        monthly = self.serve.compute_monthly(txs)
        months = [m['month'] for m in monthly]
        self.assertIn('2026-01', months)

    def test_compute_monthly_income_positive(self):
        txs = self.serve.apply_overrides(self.transactions, {})
        monthly = self.serve.compute_monthly(txs)
        jan = next(m for m in monthly if m['month'] == '2026-01')
        self.assertGreater(jan['total_income'], 0)

    def test_compute_monthly_cumulative_accumulates(self):
        txs = self.serve.apply_overrides(self.transactions, {})
        monthly = self.serve.compute_monthly(txs)
        # cumulative는 직전 월의 cumulative에 이번 달 net을 더한 값
        self.assertIn('cumulative', monthly[0])

    def test_compute_cat_summary_sums_by_category(self):
        txs = self.serve.apply_overrides(self.transactions, self.overrides)
        summary = self.serve.compute_cat_summary(txs)
        # h_0이 '금융'으로 override됐으므로 금융 합계에 포함
        self.assertIn('금융', summary)
        self.assertGreater(summary['금융']['total'], 0)
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

```bash
python -m pytest tests/test_serve.py::TestAggregation -v
```
Expected: `AttributeError: module 'serve' has no attribute 'apply_overrides'`

- [ ] **Step 3: 집계 함수 구현** (`serve.py`에 추가)

```python
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
    """월별 수입/지출/누적 집계. 이체(이체 타입)는 제외."""
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
    h_inv = sum(i['value'] for i in h_assets.get('investments', []))
    w_inv = sum(i['value'] for i in w_assets.get('investments', []))
    h_cost = sum(i['cost'] for i in h_assets.get('investments', []))
    w_cost = sum(i['cost'] for i in w_assets.get('investments', []))
    return {
        'net_assets': h_assets['net_assets'] + w_assets['net_assets'],
        'total_liabilities': h_assets['total_liabilities'] + w_assets['total_liabilities'],
        'invest_total_value': h_inv + w_inv,
        'invest_total_cost': h_cost + w_cost,
    }
```

- [ ] **Step 4: 테스트 실행 — 통과 확인**

```bash
python -m pytest tests/test_serve.py -v
```
Expected: 12개 PASS

- [ ] **Step 5: 커밋**

```bash
git add serve.py tests/test_serve.py
git commit -m "feat: serve.py 집계 함수 구현 (apply_overrides, monthly, cat_summary)"
```

---

## Task 4: serve.py — HTTP 서버 + API

**Files:**
- Modify: `serve.py`

- [ ] **Step 1: /api/data 응답 빌더 구현** (`serve.py`에 추가)

```python
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
```

- [ ] **Step 2: override 저장 함수 구현** (`serve.py`에 추가)

```python
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
```

- [ ] **Step 3: HTTP 핸들러 구현** (`serve.py`에 추가)

```python
from http.server import HTTPServer, BaseHTTPRequestHandler
import logging

LOG_PATH = os.path.join(DB_DIR, 'serve.log')
logging.basicConfig(
    filename=LOG_PATH, level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s'
)

DASHBOARD_PATH = os.path.join(os.path.dirname(__file__), 'dashboard.html')
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
            with open(DASHBOARD_PATH, 'rb') as f:
                body = f.read()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', len(body))
            self.end_headers()
            self.wfile.write(body)
        else:
            self._json({'error': 'not found'}, 404)

    def do_POST(self):
        try:
            body = self._read_body()
        except Exception:
            self._json({'error': 'invalid json'}, 400)
            return

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


if __name__ == '__main__':
    try:
        server = HTTPServer(('localhost', PORT), Handler)
        logging.info('서버 시작: http://localhost:%d', PORT)
        print(f'대시보드: http://localhost:{PORT}')
        server.serve_forever()
    except OSError as e:
        logging.error('서버 시작 실패 (포트 %d 사용 중?): %s', PORT, e)
        raise
```

- [ ] **Step 4: 서버 수동 테스트**

```bash
python serve.py
```
Expected 출력: `대시보드: http://localhost:8080`

브라우저에서 `http://localhost:8080/api/data` 열어서 JSON 응답 확인.
(데이터 없으면 빈 배열/객체 반환 — 정상)

Ctrl+C로 종료.

- [ ] **Step 5: 커밋**

```bash
git add serve.py
git commit -m "feat: serve.py HTTP 서버 및 API 엔드포인트 구현"
```

---

## Task 5: dashboard.html — fetch API로 데이터 로딩 전환

**Files:**
- Create: `dashboard.html` (기존 `가계_대시보드_v3.html` 기반)

- [ ] **Step 1: 기존 v3 HTML을 dashboard.html로 복사**

```bash
cp 가계_대시보드_v3.html dashboard.html
```

- [ ] **Step 2: 내장 JSON 데이터 블록 제거 및 fetch로 교체**

기존 코드에서 찾아서 교체:
```javascript
// 기존: const RAW = { ... 거대한 JSON ... };
```

교체할 코드:
```javascript
let RAW = null;

async function loadData() {
  try {
    RAW = await fetch('/api/data').then(r => {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    });
  } catch (e) {
    document.body.innerHTML = `
      <div style="padding:40px;font-family:sans-serif;color:#C84830;">
        <h2>서버에 연결할 수 없습니다</h2>
        <p>터미널에서 <code>python serve.py</code>를 먼저 실행해주세요.</p>
        <p>오류: ${e.message}</p>
      </div>`;
    return;
  }
  initDashboard();
  initInsights();
}
```

- [ ] **Step 3: DOMContentLoaded 핸들러 변경**

```javascript
// 기존:
window.addEventListener('DOMContentLoaded', ()=>{ initDashboard(); initInsights(); });

// 교체:
window.addEventListener('DOMContentLoaded', loadData);
```

- [ ] **Step 4: serve.py 실행 후 브라우저 테스트**

```bash
python serve.py
```
`http://localhost:8080` 열어서 대시보드 3탭이 정상 렌더링되는지 확인.
(db/가 비어있으면 빈 차트 표시 — 정상)

- [ ] **Step 5: 커밋**

```bash
git add dashboard.html
git commit -m "feat: dashboard.html fetch('/api/data') 로딩 전환"
```

---

## Task 6: dashboard.html — localStorage → API 전환

**Files:**
- Modify: `dashboard.html`

- [ ] **Step 1: OVERRIDES / localStorage 로직 제거**

기존 코드 (제거):
```javascript
let OVERRIDES = {};
try { OVERRIDES = JSON.parse(localStorage.getItem('h_overrides')||'{}'); } catch(e){}
function saveOV() { localStorage.setItem('h_overrides', JSON.stringify(OVERRIDES)); }
```

교체:
```javascript
// OVERRIDES는 서버에서 RAW.overrides로 수신. 로컬 캐시로만 사용.
let OVERRIDES = {};
function getOverrides() { return RAW ? RAW.overrides : {}; }
```

- [ ] **Step 2: getTx / visibleTx 함수 — RAW.overrides 사용으로 교체**

```javascript
function getTx(t) {
  const ov = OVERRIDES[t.id];
  return ov ? {...t, cat: ov.cat||t.cat, desc: ov.desc||t.desc, _deleted: ov.deleted||false} : {...t, _deleted:false};
}
function visibleTx() { return RAW.transactions.map(getTx).filter(t => !t._deleted); }
```

`loadData()` 완료 후 `OVERRIDES = RAW.overrides || {};` 추가:
```javascript
async function loadData() {
  // ... fetch ...
  OVERRIDES = RAW.overrides || {};
  initDashboard();
  initInsights();
}
```

- [ ] **Step 3: 편집 저장 함수 교체**

기존 `saveOV()` 호출 부분을 찾아서 API 호출로 교체.

편집 저장 (기존 `applyEdit` 함수 내):
```javascript
// 기존: OVERRIDES[id] = {cat, desc}; saveOV();
// 교체:
async function saveOverrideAPI(id, cat, desc) {
  await fetch('/api/override', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({id, cat, desc})
  });
  // 로컬 캐시도 즉시 갱신 (재fetch 없이)
  OVERRIDES[id] = {cat: cat || OVERRIDES[id]?.cat, desc: desc || OVERRIDES[id]?.desc};
}

async function saveBulkOverrideAPI(ids, cat, desc) {
  await fetch('/api/bulk-override', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ids, cat, desc})
  });
  ids.forEach(id => {
    OVERRIDES[id] = {cat: cat || OVERRIDES[id]?.cat, desc: desc || OVERRIDES[id]?.desc};
  });
}
```

삭제 (기존 `deleteEntry` 함수 내):
```javascript
async function saveDeleteAPI(id) {
  await fetch('/api/delete', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({id})
  });
  OVERRIDES[id] = {deleted: true};
}
```

- [ ] **Step 4: 기존 `applyEdit`, `deleteEntry` 함수에서 API 함수 호출로 연결**

기존 함수들의 `saveOV()` 호출 → 대응하는 async API 함수로 교체.
`async` 키워드 추가 및 `await` 처리.

- [ ] **Step 5: 통합 테스트**

1. `python serve.py` 실행
2. `http://localhost:8080` 접속
3. 거래내역 클릭 → 카테고리 수정 → 저장
4. 페이지 새로고침 → 수정 내용 유지되는지 확인
5. `db/overrides.csv` 파일 열어서 내용 기록됐는지 확인

- [ ] **Step 6: 커밋**

```bash
git add dashboard.html
git commit -m "feat: dashboard.html localStorage 제거, API 저장으로 전환"
```

---

## Task 7: start_server.bat + 기존 파일 아카이브

**Files:**
- Create: `start_server.bat`
- Create: `archive/` 폴더

- [ ] **Step 1: pythonw.exe 경로 확인**

```bash
where pythonw
```
또는:
```bash
python -c "import sys, os; print(os.path.join(os.path.dirname(sys.executable), 'pythonw.exe'))"
```

- [ ] **Step 2: start_server.bat 생성**

`start_server.bat`:
```bat
@echo off
"[위에서 확인한 pythonw.exe 전체 경로]" "C:\Users\chlgn\OneDrive\Desktop\mydata\serve.py"
```

예시:
```bat
@echo off
"C:\Users\chlgn\AppData\Local\Programs\Python\Python312\pythonw.exe" "C:\Users\chlgn\OneDrive\Desktop\mydata\serve.py"
```

- [ ] **Step 3: Windows 시작 프로그램에 등록**

파일 탐색기에서 `start_server.bat` 우클릭 → 바로가기 만들기.
만들어진 바로가기를 아래 경로로 이동:
```
%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup
```

- [ ] **Step 4: 기존 파일 archive/로 이동**

```bash
mkdir archive
mv build_dashboard.py archive/
mv 가계_대시보드_v3.html archive/
```

- [ ] **Step 5: 커밋**

```bash
git add start_server.bat archive/
git commit -m "chore: start_server.bat 추가, 기존 파일 archive 이동"
```

---

## Task 8: 초기 데이터 마이그레이션

> **Note:** 이 Task는 자동화 스크립트 없이 Claude가 수행.
> `archive/가계_대시보드_v3.html`에 내장된 JSON 데이터를 파싱해서 db/ CSV에 기록.

**Files:**
- Modify: `db/transactions.csv`
- Modify: `db/assets.csv`

- [ ] **Step 1: Claude에게 마이그레이션 요청**

```
archive/가계_대시보드_v3.html의 내장 JSON(RAW 객체)에서
transactions 배열을 db/transactions.csv에 기록해줘.
h_assets, w_assets를 db/assets.csv에 기록해줘.
```

- [ ] **Step 2: 서버 재시작 후 데이터 확인**

```bash
python serve.py
```
`http://localhost:8080/api/data` 에서 transactions, h_assets 등 데이터 확인.
`http://localhost:8080` 에서 전체 대시보드 정상 표시 확인.

- [ ] **Step 3: 커밋**

```bash
git add -N db/  # DB 파일은 .gitignore에 포함이므로 커밋 안 됨 (정상)
git commit -m "feat: 초기 데이터 마이그레이션 완료"
```

---

## 완료 기준

- [ ] `python serve.py` 실행 후 `http://localhost:8080` 에서 3탭 대시보드 정상 렌더링
- [ ] 거래내역 카테고리 수정 → 새로고침 후 유지
- [ ] 거래내역 삭제 → 새로고침 후 유지
- [ ] `db/overrides.csv` 파일에 내용 기록 확인
- [ ] 모든 유닛 테스트 통과: `python -m pytest tests/ -v`
- [ ] Windows 재부팅 후 `localhost:8080` 자동 응답 확인
