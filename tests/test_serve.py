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
        # 픽스처 문자열을 CSV 행 리스트로 파싱
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

    def test_parse_transactions_empty(self):
        result = self.serve.parse_transactions([])
        self.assertEqual(result, [])

    def test_parse_assets_empty(self):
        result = self.serve.parse_assets([])
        self.assertEqual(result, {})

    def test_parse_overrides_empty(self):
        result = self.serve.parse_overrides([])
        self.assertEqual(result, {})

    def test_parse_overrides_deleted_case_insensitive(self):
        rows = list(csv.DictReader(io.StringIO("id,cat,desc,deleted,updated_at\nh_1,금융,테스트,True,2026-01-01\n")))
        result = self.serve.parse_overrides(rows)
        self.assertTrue(result['h_1']['deleted'])

    def test_parse_assets_keeps_latest_snapshot(self):
        # Two rows for same person, different dates — should keep latest
        two_months = """snapshot_date,person,total_assets,total_liabilities,net_assets,credit_score,dc_pension,irp_pension,investments_json,loans_json
2026-01,h,100000000,0,100000000,974,0,0,"[]","[]"
2026-02,h,200000000,0,200000000,974,0,0,"[]","[]"
"""
        rows = list(csv.DictReader(io.StringIO(two_months)))
        result = self.serve.parse_assets(rows)
        self.assertEqual(result['h']['total_assets'], 200000000)
        self.assertEqual(result['h']['snapshot_date'], '2026-02')

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


if __name__ == '__main__':
    unittest.main()
