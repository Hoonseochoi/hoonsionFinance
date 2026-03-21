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
│   ├── assets.csv           ← 월별 자산 스냅샷
│   └── overrides.csv        ← 대시보드 편집 내용 (localStorage 대체)
│
├── serve.py                 ← 로컬 서버 (포트 8080)
├── dashboard.html           ← 대시보드 (serve.py가 서빙)
├── classifications.csv      ← 분류 규칙 (기존 유지)
└── ANALYSIS_GUIDE.md        ← 분석 가이드 (기존 유지)
```

---

## CSV 스키마

### db/transactions.csv
```
tx_id, person, date, time, type, category, subcategory, desc, amount, currency, method, memo
```
- `tx_id`: `h_0`, `w_0` 형식 (person prefix + 순번)
- `person`: `h` (훈서) / `w` (시온)
- `type`: `수입` / `지출` / `이체`
- `amount`: 지출 음수(-), 수입 양수(+)
- 새 xlsx 임포트 시 기존 마지막 날짜 이후 거래만 추가 (중복 방지)

### db/assets.csv
```
snapshot_date, person, total_assets, total_liabilities, net_assets, credit_score
```
- `snapshot_date`: `YYYY-MM` 형식
- 같은 달 같은 person이면 덮어쓰기

### db/overrides.csv
```
tx_id, category, desc, deleted, updated_at
```
- `deleted`: `true` / `false`
- `updated_at`: ISO 8601 타임스탬프
- localStorage를 완전히 대체

---

## serve.py API

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/` | dashboard.html 서빙 |
| GET | `/api/data` | transactions + assets + overrides 합쳐서 JSON 반환 |
| POST | `/api/override` | 단건 수정 저장 → overrides.csv |
| POST | `/api/delete` | 단건 삭제 → overrides.csv (deleted=true) |
| POST | `/api/bulk-override` | 일괄 수정 (같은 이름/카테고리 전체) → overrides.csv |

### /api/data 응답 구조
```json
{
  "transactions": [...],   // overrides 적용 후 (deleted 제외)
  "assets": [...],
  "meta": {
    "last_updated": "2026-03-22T10:00:00",
    "tx_count": { "h": 1200, "w": 800 }
  }
}
```

---

## dashboard.html 변경사항

기존 `가계_대시보드_v3.html` 대비 변경점:

1. **데이터 로딩**: 내장 JSON → `fetch('/api/data')` 로 교체
2. **편집 저장**: `localStorage.setItem` → `POST /api/override` 로 교체
3. **삭제**: localStorage → `POST /api/delete` 로 교체
4. **일괄 수정**: localStorage → `POST /api/bulk-override` 로 교체
5. 나머지 UI/차트/모달 로직은 그대로 유지

---

## Windows 자동 시작 설정

`serve.py`를 Windows 시작 프로그램으로 등록하는 배치 파일:

```bat
start_server.bat
```

- 시작 프로그램 폴더에 바로가기 추가
- 부팅 시 백그라운드 실행, 콘솔 창 숨김
- `localhost:8080` 상시 대기

---

## 매달 임포트 절차

1. 뱅크샐러드에서 xlsx 내보내기
2. Claude Code에 파일 전달: `"새 마이데이터 파일이야, DB에 추가해줘"`
3. Claude가 xlsx 분석 → `db/transactions.csv`, `db/assets.csv` 업데이트
4. 기존 `overrides.csv` 편집 내용은 그대로 유지됨

> **Note**: 임포트를 Claude가 담당하는 이유 — 매달 데이터 구조가 미묘하게 다를 수 있고, 성과급 처리 등 판단이 필요한 케이스를 그때그때 처리하기 위함.

---

## 구현 범위 (이번 작업)

- [ ] `db/` 폴더 생성 및 초기 CSV 파일 생성
- [ ] `serve.py` 구현 (Flask 또는 표준 라이브러리)
- [ ] `dashboard.html` 수정 (fetch API로 데이터 로딩, override API로 편집 저장)
- [ ] `start_server.bat` 생성

## 구현 제외 (나중에)

- 원격 접속 (Tailscale 등) — 나중에 필요할 때
- 자동화된 import 스크립트 — Claude가 수동으로 처리
