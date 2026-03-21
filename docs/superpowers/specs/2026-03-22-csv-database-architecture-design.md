# CSV 기반 로컬 데이터베이스 아키텍처 설계

**작성일**: 2026-03-22
**대상 프로젝트**: 최훈서·윤시온 가계 대시보드
**상태**: 승인됨

---

## 문제 정의

현재 구조의 세 가지 핵심 문제:

1. **xlsx는 스냅샷** — 매달 새 파일이 이전 데이터를 덮어씀
2. **localStorage는 브라우저에 갇힘** — `build_dashboard.py` 재실행 시 HTML이 바뀌면 편집 내용 증발
3. **두 데이터가 연결 안 됨** — xlsx 데이터와 localStorage 수정 내용이 별개

---

## 목표

- CSV를 단일 진실 소스(Single Source of Truth)로
- 대시보드에서 수정/삭제한 내용이 파일에 영구 저장
- 매달 새 xlsx가 와도 기존 편집 내용 유지
- 구조는 최대한 단순하게

---

## 최종 아키텍처

```
매달:  새 xlsx → Claude 분석 → db/transactions.csv, db/assets.csv 에 추가
평소:  serve.py (localhost:8080) → dashboard.html 서빙
편집:  대시보드 수정/삭제 → POST /api/override → db/overrides.csv 저장
```

---

## 파일 구조

```
C:\Users\chlgn\OneDrive\Desktop\mydata\
├── db/
│   ├── transactions.csv     ← 전체 거래내역 (단일 진실 소스)
│   ├── assets.csv           ← 월별 자산 스냅샷 (투자/대출/연금 포함)
│   └── overrides.csv        ← 대시보드 편집 내용 (localStorage 대체)
│
├── serve.py                 ← 로컬 서버 (포트 8080)
├── dashboard.html           ← 대시보드 (serve.py가 서빙)
├── classifications.csv      ← 분류 규칙 (기존 유지)
└── ANALYSIS_GUIDE.md        ← 분석 가이드 (기존 유지)

[기존 파일 처리]
archive/
├── build_dashboard.py       ← archive/로 이동 (더 이상 사용 안 함)
└── 가계_대시보드_v3.html    ← archive/로 이동 (더 이상 사용 안 함)
```

---

## CSV 스키마

### db/transactions.csv
```
id, person, date, time, type, category, subcategory, desc, amount, currency, method, memo
```
- `id`: `h_0`, `w_0` 형식 (person prefix + **전체 기간 통산 단조증가 순번**)
  - 컬럼명은 `id` (기존 대시보드 코드가 `t.id`로 참조하기 때문)
  - 새 임포트 시 기존 최대 번호 이후부터 부여. 절대 재사용 안 함
- `person`: `h` (훈서) / `w` (시온)
- `type`: `수입` / `지출` / `이체`
- `amount`: 지출 음수(-), 수입 양수(+)

**중복 방지 규칙**: 새 xlsx 임포트 시 person별로 기존 마지막 tx의 날짜를 확인하고,
그 날짜보다 **날짜(date)가 엄격히 이후인(strictly after) 거래만** 추가한다.
같은 날 마지막 거래가 있으면 해당 날 전체를 제외한다.
Claude는 임포트 전 기존 마지막 5건을 확인하고 새 xlsx의 동일 구간과 비교해 중복 없음을 검증한다.

### db/assets.csv
한 행 = 특정 월의 특정 인물 전체 자산 스냅샷. 중첩 데이터를 JSON 컬럼으로 저장한다.

```
snapshot_date, person, total_assets, total_liabilities, net_assets, credit_score,
dc_pension, irp_pension, investments_json, loans_json
```

- `snapshot_date`: `YYYY-MM` 형식. 같은 달 같은 person이면 덮어쓰기
- `dc_pension`, `irp_pension`: 훈서 퇴직연금 금액. 시온은 항상 0 (필드 생략 불가, 0으로 기록)
- `investments_json`: 투자 포트폴리오 배열 (JSON 직렬화)
  ```json
  [{"name":"메리츠금융지주","firm":"키움","value":48770000,"cost":23940000,"rate":103.71}]
  ```
- `loans_json`: 대출 현황 배열 (JSON 직렬화)
  ```json
  [{"name":"KB 주택전세자금대출","balance":216000000,"rate":4.42}]
  ```

### db/overrides.csv
```
id, cat, desc, deleted, updated_at
```
- `id`: transactions.csv의 `id`와 동일 (기존 코드 `OVERRIDES[t.id]`와 일치)
- `cat`: 변경된 카테고리 (기존 코드의 `OVERRIDES[id].cat`과 일치)
- `deleted`: `true` / `false` (문자열)
- `updated_at`: ISO 8601 (`2026-03-22T10:00:00`)
- localhost를 완전히 대체

---

## serve.py API

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/` | dashboard.html 서빙 |
| GET | `/api/data` | 아래 설명 참조 |
| POST | `/api/override` | 단건 수정 → overrides.csv |
| POST | `/api/delete` | 단건 삭제 → overrides.csv (deleted=true) |
| POST | `/api/bulk-override` | 일괄 수정 → overrides.csv |

### GET /api/data 응답 구조

serve.py가 서버 사이드에서 집계 계산을 모두 수행해서 반환한다.
**응답 키 이름은 기존 대시보드가 사용하는 `RAW.*` 구조와 동일하게 맞춘다.**
dashboard.html은 `const RAW = await fetch('/api/data').then(r=>r.json())`로 교체하면
나머지 렌더링 코드는 그대로 동작한다.

```json
{
  "transactions": [
    {
      "id": "h_965",
      "person": "h",
      "date": "2026-03-21",
      "type": "지출",
      "cat": "금융",
      "desc": "아이엠삼송 전세이자",
      "amount": -770000
    }
  ],
  "h_assets": {
    "snapshot_date": "2026-03",
    "total_assets": 306395533,
    "total_liabilities": 238466917,
    "net_assets": 67928616,
    "credit_score": 974,
    "investments": [{"name":"메리츠금융지주","firm":"키움","value":48770000,"cost":23940000,"rate":103.71}],
    "loans": [{"name":"KB 주택전세자금대출","balance":216000000,"rate":4.42}]
  },
  "w_assets": {
    "snapshot_date": "2026-03",
    "total_assets": 91997730,
    "total_liabilities": 0,
    "net_assets": 91997730,
    "credit_score": 1000,
    "investments": [...],
    "loans": []
  },
  "h_dc": 122764978,
  "h_irp": 7050000,
  "combined": {
    "net_assets": 159926346,
    "total_liabilities": 238466917,
    "invest_total_value": 215522687,
    "invest_total_cost": 214528048
  },
  "monthly": [
    {"month": "2025-03", "total_income": 3560000, "total_expense": -6160000, "cumulative": -2600000}
  ],
  "cumulative": [
    {"month": "2025-03", "cumulative": -2600000}
  ],
  "cat_summary": {
    "온라인쇼핑": {"total": 29770000, "h": 27530000, "w": 2240000}
  },
  "all_cats": ["금융", "투자", "보험", "자동차"],
  "overrides": {
    "h_965": {"cat": "금융", "desc": "아이엠삼송 전세이자"},
    "h_999": {"deleted": true}
  },
  "meta": {
    "last_updated": "2026-03-22T10:00:00",
    "tx_count": {"h": 1200, "w": 800}
  }
}
```

**집계 계산 규칙 (serve.py 내부)**:
- overrides 적용 후 transactions 기준으로 monthly/cat_summary 계산
- `deleted=true` 거래는 모든 집계에서 제외
- `monthly[].cumulative` = 해당 월까지 (total_income + total_expense) 누적합
- `cumulative` 배열은 `monthly`와 동일한 누적값을 별도 배열로 제공 (기존 코드 호환)
- transactions 배열 자체에도 override 적용 결과 반영 (cat, desc 교체)

### POST /api/override 요청 본문
```json
{ "id": "h_965", "cat": "금융", "desc": "아이엠삼송 전세이자" }
```

### POST /api/delete 요청 본문
```json
{ "id": "h_999" }
```

### POST /api/bulk-override 요청 본문
```json
{
  "ids": ["h_0", "h_1", "h_2"],
  "cat": "금융",
  "desc": "아이엠삼송 전세이자"
}
```
- `cat`과 `desc` 중 하나는 null 가능 (null이면 해당 필드 변경 없음)
- 둘 다 null이면 no-op (서버는 200 반환, CSV 변경 없음)
- 예: desc만 변경: `{"ids":[...],"cat":null,"desc":"새이름"}`

---

## dashboard.html 변경사항

기존 `가계_대시보드_v3.html` 대비 변경점:

| 항목 | 기존 | 변경 후 |
|------|------|---------|
| 데이터 로딩 | `const RAW = {...}` (내장 JSON) | `const RAW = await fetch('/api/data').then(r=>r.json())` |
| 편집 저장 | `localStorage.setItem('h_overrides', ...)` | `POST /api/override` |
| 삭제 | localStorage | `POST /api/delete` |
| 일괄 수정 | localStorage | `POST /api/bulk-override` |
| 편집 후 모달 갱신 | localStorage에서 읽기 | 로컬 in-memory `RAW` 객체 즉시 갱신 (재fetch 없음) |
| 카테고리 드롭다운 | 하드코딩 | `RAW.all_cats` 사용 |
| override 적용 | 클라이언트에서 `OVERRIDES` 객체로 계산 | 서버에서 이미 적용된 transactions 수신. `RAW.overrides`는 모달 초기값 표시에만 사용 |

`RAW.*` 키 이름은 기존과 동일하므로 나머지 차트/모달/정렬/필터 로직은 변경 없음.

---

## Windows 자동 시작 설정

`start_server.bat` 파일:

```bat
@echo off
"C:\Users\chlgn\AppData\Local\Programs\Python\Python312\pythonw.exe" "C:\Users\chlgn\OneDrive\Desktop\mydata\serve.py"
```

- `pythonw.exe` 전체 경로 사용 (PATH 의존 금지)
  - 실제 경로는 `where pythonw` 또는 `py -c "import sys; print(sys.executable)"` 로 확인
- 이 배치 파일의 바로가기를 아래 경로에 추가:
  `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup`
- 포트 8080이 이미 사용 중이면 `db/serve.log`에 에러 기록 후 종료

---

## 매달 임포트 절차

1. 뱅크샐러드에서 훈서/시온 마이데이터 xlsx 내보내기
2. Claude Code에 파일 전달: `"새 마이데이터 파일이야, DB에 추가해줘"`
3. Claude가 수행:
   - xlsx 파싱 및 `classifications.csv` 적용
   - `db/transactions.csv`에서 person별 마지막 날짜 확인
   - 해당 날짜 **엄격히 이후** 거래만 추가 (마지막 5건 중복 검증 포함)
   - `db/assets.csv`에 최신 스냅샷 추가/갱신
4. `db/overrides.csv` 편집 내용은 건드리지 않음 → 그대로 유지

> **임포트를 Claude가 담당하는 이유**: 매달 데이터 구조가 미묘하게 다를 수 있고,
> 성과급 처리 등 판단이 필요한 케이스를 그때그때 처리하기 위함.

---

## 구현 범위 (이번 작업)

- [ ] `db/` 폴더 및 초기 빈 CSV 파일 생성
- [ ] `serve.py` 구현 (Python 표준 라이브러리 또는 Flask)
- [ ] `dashboard.html` 구현 (기존 v3 기반, fetch API로 전환)
- [ ] `start_server.bat` 생성
- [ ] `archive/` 폴더에 기존 파일 이동

## 구현 제외 (나중에)

- 원격 접속 (Tailscale 등)
- 자동화된 import 스크립트
