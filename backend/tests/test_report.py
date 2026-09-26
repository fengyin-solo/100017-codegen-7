"""检测报告模块的边界与空态测试。

覆盖：空库、只有一条、分页达到上限、异常字段（坏 id/空编号/坏日期）、
输入不完整、报告编号重复不覆盖旧记录、动作执行后清单/数量指标/详情同步恢复。
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.seed import SEED_ROWS
from app.services import report as report_service
from app.services.report import MODULE, ReportService
from app.store import store


@pytest.fixture()
def client() -> TestClient:
    """每个用例独立：report 表换成内置样例的副本，避免污染共享内存库。"""
    original = [dict(row) for row in SEED_ROWS[MODULE]]
    store._tables[MODULE] = [dict(row) for row in original]
    with TestClient(app) as test_client:
        yield test_client
    store._tables[MODULE] = original


def _set_rows(rows: list[dict]) -> None:
    store._tables[MODULE] = [dict(row) for row in rows]


# ---------- 空库 ----------

def test_empty_library_returns_empty_page_not_error(client: TestClient) -> None:
    _set_rows([])
    response = client.get("/api/report")
    assert response.status_code == 200
    payload = response.json()
    assert payload["items"] == []
    assert payload["total"] == 0
    assert payload["page"] == 1


def test_empty_library_stats_are_zero(client: TestClient) -> None:
    _set_rows([])
    stats = client.get("/api/report/stats").json()
    assert stats == {"待编制报告": 0, "待批准报告": 0, "本月签发": 0}


def test_empty_library_detail_is_readable_404(client: TestClient) -> None:
    _set_rows([])
    response = client.get("/api/report/1")
    assert response.status_code == 404
    assert "不存在或已归档" in response.json()["detail"]


def test_empty_library_export_returns_empty_items(client: TestClient) -> None:
    _set_rows([])
    response = client.get("/api/report/export")
    assert response.status_code == 200
    assert response.json()["total"] == 0
    assert response.json()["items"] == []


def test_empty_library_create_then_retry_list_restores(client: TestClient) -> None:
    """空库登记一条后重新拉取，清单、数量指标、详情必须一起恢复。"""
    _set_rows([])
    created = client.post("/api/report", json={"values": {
        "报告编号": "REPO-NEW-1", "委托单位": "甲单位", "样品名称": "水样",
    }})
    assert created.status_code == 200
    assert created.json()["ok"] is True

    listing = client.get("/api/report").json()
    assert listing["total"] == 1
    assert listing["items"][0]["报告编号"] == "REPO-NEW-1"
    stats = client.get("/api/report/stats").json()
    assert stats["待编制报告"] == 1
    detail = client.get("/api/report/1").json()
    assert detail["报告编号"] == "REPO-NEW-1"
    assert detail["status"] == "待编制"
    assert detail["报告状态"] == "待编制"


# ---------- 只有一条 ----------

def test_single_record_filters_and_pagination(client: TestClient) -> None:
    _set_rows([{
        "id": 7, "status": "已签发", "pending": False, "abnormal": False,
        "报告编号": "REPO-ONLY-1", "委托单位": "乙单位", "样品名称": "土样",
        "签发日期": "2026-09-10",
    }])
    assert client.get("/api/report", params={"page": 2, "size": 20}).json()["items"] == []
    hit = client.get("/api/report", params={"keyword": "ONLY"}).json()
    assert hit["total"] == 1
    miss = client.get("/api/report", params={"keyword": "NOPE"}).json()
    assert miss["total"] == 0
    by_status = client.get("/api/report", params={"status": "已签发"}).json()
    assert by_status["total"] == 1


def test_single_record_stats_count_issued_month(client: TestClient) -> None:
    _set_rows([{
        "id": 1, "status": "已签发", "pending": False, "abnormal": False,
        "报告编号": "REPO-ONLY-1", "签发日期": "2026-09-10",
    }])
    stats = client.get("/api/report/stats").json()
    assert stats["本月签发"] == 1
    assert stats["待编制报告"] == 0


# ---------- 达到上限 / 非法分页 ----------

def test_size_at_upper_bound_accepted(client: TestClient) -> None:
    response = client.get("/api/report", params={"size": 200})
    assert response.status_code == 200
    assert response.json()["size"] == 200


def test_size_over_upper_bound_rejected_with_recoverable_message(client: TestClient) -> None:
    response = client.get("/api/report", params={"size": 201})
    assert response.status_code == 422  # 前端拿到后展示错误态与重试，不留旧内容


def test_invalid_status_rejected_with_options(client: TestClient) -> None:
    response = client.get("/api/report", params={"status": "外星状态"})
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "待编制" in detail and "已撤回" in detail


# ---------- 异常字段 ----------

def test_broken_id_does_not_break_listing_or_id_generation() -> None:
    _set_rows([
        {"id": "not-a-number", "报告编号": "REPO-BAD-ID"},
        {"id": 3, "报告编号": "REPO-0003"},
    ])
    service = ReportService()
    rows, total = service.list_entries()
    assert total == 2
    assert {row["报告编号"] for row in rows} == {"REPO-BAD-ID", "REPO-0003"}
    entry, _, conflict = service.create_entry({"报告编号": "REPO-NEW", "委托单位": "甲", "样品名称": "乙"})
    assert entry is not None and conflict == ""
    assert entry["id"] == 4  # 跳过无法解析的异常 id，不与 id=3 冲突


def test_missing_code_field_matches_keyword_as_empty(client: TestClient) -> None:
    _set_rows([{"id": 1, "status": "待编制", "委托单位": "无编号单位"}])
    rows, total = ReportService().list_entries(keyword="REPO")
    assert total == 0
    all_rows, all_total = ReportService().list_entries()
    assert all_total == 1
    assert all_rows[0].get("报告编号") is None


def test_broken_issue_date_excluded_from_month_stats() -> None:
    _set_rows([
        {"id": 1, "status": "已签发", "签发日期": "not-a-date"},
        {"id": 2, "status": "已签发", "签发日期": None},
        {"id": 3, "status": "已签发", "签发日期": "2026-09-20"},
    ])
    stats = ReportService().get_stats()
    assert stats["本月签发"] == 1


# ---------- 输入不完整 / 编号重复 ----------

def test_create_with_incomplete_input_is_rejected(client: TestClient) -> None:
    before = client.get("/api/report").json()["total"]
    result = client.post("/api/report", json={"values": {"报告编号": "  "}})
    body = result.json()
    assert body["ok"] is False
    assert "缺少必填字段" in body["message"]
    assert "报告编号" not in body["message"] or body["message"]  # 编号空白也算缺失
    assert client.get("/api/report").json()["total"] == before  # 旧记录不被覆盖


def test_duplicate_report_code_rejected_and_keeps_old_record(client: TestClient) -> None:
    existing = client.get("/api/report").json()["items"][0]
    code = existing["报告编号"]
    result = client.post("/api/report", json={"values": {
        "报告编号": code, "委托单位": "重复单位", "样品名称": "重复样品",
    }})
    body = result.json()
    assert body["ok"] is False
    assert "已存在" in body["message"]
    rows = client.get("/api/report").json()["items"]
    matched = [row for row in rows if row["报告编号"] == code]
    assert len(matched) == 1  # 旧记录原封不动
    assert matched[0]["委托单位"] != "重复单位"


def test_blank_action_rejected(client: TestClient) -> None:
    result = client.post("/api/report/1/actions", json={"values": {"action": "  "}})
    body = result.json()
    assert body["ok"] is False
    assert "未指定" in body["message"]


def test_action_on_missing_report_is_recoverable_404(client: TestClient) -> None:
    result = client.post("/api/report/999/actions", json={"values": {"action": "编制报告"}})
    body = result.json()
    assert body["ok"] is False
    assert "不存在或已归档" in body["message"]


# ---------- 动作后清单、数量指标、详情同步恢复 ----------

def test_action_flow_syncs_list_stats_and_detail(client: TestClient) -> None:
    # 初始：种子第一条为待编制
    assert client.get("/api/report/stats").json()["待编制报告"] >= 1

    action = client.post("/api/report/1/actions", json={"values": {"action": "提交批准"}})
    assert action.json()["ok"] is True

    listing = client.get("/api/report").json()["items"]
    row = next(item for item in listing if item["id"] == 1)
    assert row["status"] == "待批准"
    assert row["报告状态"] == "待批准"

    stats = client.get("/api/report/stats").json()
    assert stats["待批准报告"] >= 1

    detail = client.get("/api/report/1").json()
    assert detail["status"] == "待批准"
    assert detail["报告状态"] == "待批准"


def test_withdraw_clears_pending_flag(client: TestClient) -> None:
    client.post("/api/report/1/actions", json={"values": {"action": "撤回报告"}})
    detail = client.get("/api/report/1").json()
    assert detail["status"] == "已撤回"
    assert detail["pending"] is False


def test_illegal_action_does_not_mutate_record(client: TestClient) -> None:
    before = client.get("/api/report/1").json()
    result = client.post("/api/report/1/actions", json={"values": {"action": "删除报告"}})
    assert result.json()["ok"] is False
    after = client.get("/api/report/1").json()
    assert after["status"] == before["status"]
