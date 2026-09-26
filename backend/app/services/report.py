"""检测报告业务规则：状态流转、字段校验、统计口径与筛选都收在这里。

所有读取方法对异常字段（缺 id、空编号、坏日期等）都做兜底，
保证单条脏数据不会让整页清单或数量指标读不出来。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.store import store

MODULE = "report"
REQUIRED_FIELDS = ["报告编号", "委托单位", "样品名称"]
OPTIONAL_FIELDS = ["报告类型", "编制人", "批准人", "签发日期"]
STATUS_ORDER = ["待编制", "编制中", "待批准", "已签发", "已撤回"]
ACTION_RULES = {"编制报告": "编制中", "提交批准": "待批准", "撤回报告": "已撤回"}
NEGATIVE_ACTIONS = []


def _text(value: Any) -> str:
    """把任意字段值安全转成可匹配的字符串：None、数字、异常类型都不抛错。"""
    if value is None:
        return ""
    return str(value).strip()


class ReportService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        client: str | None = None,
        sample: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = list(store.rows(MODULE))
        keyword = (keyword or "").strip()
        client = (client or "").strip()
        sample = (sample or "").strip()
        status = (status or "").strip()
        if keyword:
            rows = [row for row in rows if keyword in _text(row.get("报告编号"))]
        if client:
            rows = [row for row in rows if client in _text(row.get("委托单位"))]
        if sample:
            rows = [row for row in rows if sample in _text(row.get("样品名称"))]
        if status:
            rows = [row for row in rows if _text(row.get("status")) == status]
        total = len(rows)
        page = max(page, 1)
        size = max(size, 1)
        start = (page - 1) * size
        return rows[start:start + size], total

    def get_stats(self) -> dict[str, int]:
        """数量指标：待编制、待批准、本月签发。坏日期等异常字段一律不计入。"""
        today = datetime.now()
        pending_compile = 0
        pending_approve = 0
        issued_this_month = 0
        for row in store.rows(MODULE):
            if _text(row.get("status")) == "待编制":
                pending_compile += 1
            if _text(row.get("status")) == "待批准":
                pending_approve += 1
            issued_on = self._parse_date(row.get("签发日期"))
            if (
                _text(row.get("status")) == "已签发"
                and issued_on is not None
                and issued_on.year == today.year
                and issued_on.month == today.month
            ):
                issued_this_month += 1
        return {
            "待编制报告": pending_compile,
            "待批准报告": pending_approve,
            "本月签发": issued_this_month,
        }

    @staticmethod
    def _parse_date(value: Any) -> datetime | None:
        text = _text(value)
        if not text:
            return None
        try:
            return datetime.fromisoformat(text[:10])
        except ValueError:
            return None

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def find_by_code(self, code: str) -> dict[str, Any] | None:
        """按报告编号查重：编号空白或不存在时返回 None。"""
        code = (code or "").strip()
        if not code:
            return None
        for row in store.rows(MODULE):
            if _text(row.get("报告编号")) == code:
                return row
        return None

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str], str]:
        """登记检测报告。

        返回 (记录, 缺失字段, 业务错误说明)：输入不完整或编号重复时不动任何旧数据。
        """
        missing = [field for field in REQUIRED_FIELDS if not _text(values.get(field))]
        if missing:
            return None, missing, ""
        code = _text(values.get("报告编号"))
        if self.find_by_code(code) is not None:
            return None, [], f"报告编号 {code} 已存在，请更换编号后重试"
        rows = store.rows(MODULE)
        entry: dict[str, Any] = {"id": self._next_id(rows)}
        for field in REQUIRED_FIELDS + OPTIONAL_FIELDS:
            entry[field] = _text(values.get(field)) or None
        entry["status"] = STATUS_ORDER[0]
        entry["报告状态"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, [], ""

    @staticmethod
    def _next_id(rows: list[dict[str, Any]]) -> int:
        """跳过无法解析的异常 id，保证新编号始终递增且不与已有记录冲突。"""
        max_id = 0
        for row in rows:
            try:
                max_id = max(max_id, int(row.get("id", 0)))
            except (TypeError, ValueError):
                continue
        return max_id + 1

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"检测报告 {entry_id} 不存在或已归档"
        action = (action or "").strip()
        if not action:
            return None, "未指定要执行的动作，请重新选择后重试"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于检测报告可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        entry["status"] = target
        entry["报告状态"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return entry, f"检测报告已{action}"
