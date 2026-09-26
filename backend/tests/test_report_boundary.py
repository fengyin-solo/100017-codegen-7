"""检测报告边界与空态回归测试。

覆盖四类边界：空库、只有一条、达到上限、异常字段；
以及"失败后重试"的恢复路径：重试成功时清单、数量指标、详情必须同步恢复，
已有记录不被覆盖。
"""
from __future__ import annotations

import copy
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.store import store

client = TestClient(app)

VALID_VALUES = {"报告编号": "REPO-1001", "委托单位": "某食品厂", "样品名称": "矿泉水"}


@pytest.fixture(autouse=True)
def restore_report_rows():
    """每个用例跑完都还原 report 表，保证用例之间互不影响。"""
    original = copy.deepcopy(store.rows("report"))
    yield
    rows = store.rows("report")
    rows.clear()
    rows.extend(original)


def set_rows(rows: list[dict]) -> None:
    table = store.rows("report")
    table.clear()
    table.extend(rows)


def create(values: dict):
    return client.post("/api/report", json={"values": values})


def stat_values() -> dict[str, int]:
    payload = client.get("/api/report/stats").json()
    return {item["label"]: item["value"] for item in payload["stats"]}


# ---------- 空库 ----------

class TestEmptyStore:
    def setup_method(self):
        set_rows([])

    def test_list_returns_empty_page_not_error(self):
        resp = client.get("/api/report")
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["items"] == []
        assert payload["total"] == 0

    def test_stats_all_zero(self):
        assert stat_values() == {"待编制报告": 0, "待批准报告": 0, "本月签发": 0}

    def test_detail_404_readable(self):
        resp = client.get("/api/report/1")
        assert resp.status_code == 404
        assert "不存在" in resp.json()["detail"]

    def test_export_empty(self):
        resp = client.get("/api/report/export")
        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    def test_filter_on_empty_store(self):
        resp = client.get("/api/report", params={"报告编号": "REPO"})
        assert resp.status_code == 200
        assert resp.json()["total"] == 0


# ---------- 只有一条 ----------

class TestSingleEntry:
    def setup_method(self):
        set_rows([])

    def test_single_record_list_and_stats(self):
        assert create(VALID_VALUES).json()["ok"] is True
        payload = client.get("/api/report").json()
        assert payload["total"] == 1
        assert payload["items"][0]["报告编号"] == "REPO-1001"
        assert stat_values()["待编制报告"] == 1

    def test_second_create_appends_without_touching_first(self):
        create(VALID_VALUES)
        resp = create({"报告编号": "REPO-1002", "委托单位": "某药厂", "样品名称": "纯化水"})
        assert resp.json()["ok"] is True
        assert resp.json()["entry"]["id"] == 2
        payload = client.get("/api/report").json()
        assert payload["total"] == 2
        first = client.get("/api/report/1").json()
        assert first["报告编号"] == "REPO-1001"
        assert first["委托单位"] == "某食品厂"

    def test_filters_narrow_the_single_record(self):
        create(VALID_VALUES)
        hit = client.get("/api/report", params={"委托单位": "食品"}).json()
        miss = client.get("/api/report", params={"委托单位": "不存在"}).json()
        assert hit["total"] == 1
        assert miss["total"] == 0 and miss["items"] == []


# ---------- 达到上限 ----------

class TestLimits:
    def setup_method(self):
        set_rows([dict(VALID_VALUES, id=1, status="待编制", pending=True, abnormal=False)])

    @pytest.mark.parametrize("size", [0, -1, 201])
    def test_size_out_of_range_returns_400(self, size):
        resp = client.get("/api/report", params={"size": size})
        assert resp.status_code == 400
        assert "分页" in resp.json()["detail"]

    def test_page_must_start_from_1(self):
        resp = client.get("/api/report", params={"page": 0})
        assert resp.status_code == 400
        assert "页码" in resp.json()["detail"]

    def test_page_beyond_range_returns_empty_page(self):
        resp = client.get("/api/report", params={"page": 99, "size": 20})
        assert resp.status_code == 200
        assert resp.json()["items"] == []
        assert resp.json()["total"] == 1

    def test_size_at_upper_bound_still_works(self):
        resp = client.get("/api/report", params={"size": 200})
        assert resp.status_code == 200

    def test_create_rejected_at_capacity(self, monkeypatch):
        monkeypatch.setattr("app.services.report.MAX_ENTRIES", 1)
        resp = create({"报告编号": "REPO-1002", "委托单位": "某药厂", "样品名称": "纯化水"})
        assert resp.json()["ok"] is False
        assert "上限" in resp.json()["message"]
        assert client.get("/api/report").json()["total"] == 1


# ---------- 异常字段 ----------

class TestAbnormalFields:
    def setup_method(self):
        set_rows([])

    def test_missing_required_fields_listed(self):
        resp = create({})
        assert resp.json()["ok"] is False
        message = resp.json()["message"]
        for field in ["报告编号", "委托单位", "样品名称"]:
            assert field in message
        assert client.get("/api/report").json()["total"] == 0

    def test_blank_required_fields_treated_as_missing(self):
        resp = create({"报告编号": "   ", "委托单位": "", "样品名称": "矿泉水"})
        assert resp.json()["ok"] is False
        assert "报告编号" in resp.json()["message"]
        assert "委托单位" in resp.json()["message"]

    def test_structured_value_rejected_as_abnormal(self):
        resp = create({"报告编号": ["REPO-1001"], "委托单位": "某食品厂", "样品名称": "矿泉水"})
        assert resp.json()["ok"] is False
        assert "格式异常" in resp.json()["message"]
        assert client.get("/api/report").json()["total"] == 0

    def test_numeric_value_coerced_to_text(self):
        resp = create({"报告编号": 1001, "委托单位": "某食品厂", "样品名称": "矿泉水"})
        assert resp.json()["ok"] is True
        assert resp.json()["entry"]["报告编号"] == "1001"

    def test_overlong_field_rejected(self):
        resp = create({"报告编号": "R" * 101, "委托单位": "某食品厂", "样品名称": "矿泉水"})
        assert resp.json()["ok"] is False
        assert "上限" in resp.json()["message"]

    def test_duplicate_number_does_not_overwrite_existing(self):
        create(VALID_VALUES)
        resp = create({"报告编号": "REPO-1001", "委托单位": "另一家单位", "样品名称": "别的样品"})
        assert resp.json()["ok"] is False
        assert "已存在" in resp.json()["message"]
        assert client.get("/api/report").json()["total"] == 1
        kept = client.get("/api/report/1").json()
        assert kept["委托单位"] == "某食品厂"
        assert kept["样品名称"] == "矿泉水"

    def test_row_with_abnormal_id_does_not_crash_lookup(self):
        set_rows([{"id": "not-a-number", "报告编号": None, "status": "待编制"}])
        assert client.get("/api/report/999").status_code == 404
        resp = create(VALID_VALUES)
        assert resp.json()["ok"] is True
        assert resp.json()["entry"]["id"] == 1

    def test_action_boundaries(self):
        create(VALID_VALUES)
        unknown = client.post("/api/report/1/actions", json={"values": {"action": "删除报告"}})
        assert unknown.json()["ok"] is False
        assert "不属于" in unknown.json()["message"]
        missing = client.post("/api/report/999/actions", json={"values": {"action": "编制报告"}})
        assert missing.json()["ok"] is False
        assert "不存在" in missing.json()["message"]


# ---------- 失败后重试：清单、指标、详情同步恢复 ----------

class TestRetryRecovery:
    def setup_method(self):
        set_rows([])

    def test_failed_create_then_retry_restores_everything(self):
        failed = create({"报告编号": "REPO-1001"})
        assert failed.json()["ok"] is False
        assert client.get("/api/report").json()["total"] == 0
        assert stat_values()["待编制报告"] == 0

        retried = create(VALID_VALUES)
        assert retried.json()["ok"] is True
        entry_id = retried.json()["entry"]["id"]

        listing = client.get("/api/report").json()
        assert listing["total"] == 1
        assert listing["items"][0]["报告编号"] == "REPO-1001"
        assert stat_values() == {"待编制报告": 1, "待批准报告": 0, "本月签发": 0}
        detail = client.get(f"/api/report/{entry_id}").json()
        assert detail["委托单位"] == "某食品厂"

    def test_action_then_list_stats_detail_in_sync(self):
        entry_id = create(VALID_VALUES).json()["entry"]["id"]
        resp = client.post(f"/api/report/{entry_id}/actions", json={"values": {"action": "提交批准"}})
        assert resp.json()["ok"] is True

        listing = client.get("/api/report").json()
        assert listing["items"][0]["status"] == "待批准"
        assert listing["items"][0]["报告状态"] == "待批准"
        assert stat_values() == {"待编制报告": 0, "待批准报告": 1, "本月签发": 0}
        detail = client.get(f"/api/report/{entry_id}").json()
        assert detail["status"] == "待批准"

    def test_monthly_issued_stat_counts_only_current_month(self):
        month = date.today().strftime("%Y-%m")
        set_rows([
            {"id": 1, "报告编号": "REPO-1", "status": "已签发", "签发日期": f"{month}-01"},
            {"id": 2, "报告编号": "REPO-2", "status": "已签发", "签发日期": "2020-01-01"},
            {"id": 3, "报告编号": "REPO-3", "status": "已签发", "签发日期": None},
        ])
        assert stat_values()["本月签发"] == 1

    def test_export_returns_all_rows(self):
        create(VALID_VALUES)
        create({"报告编号": "REPO-1002", "委托单位": "某药厂", "样品名称": "纯化水"})
        payload = client.get("/api/report/export").json()
        assert payload["module"] == "report"
        assert payload["total"] == 2
        assert len(payload["items"]) == 2
