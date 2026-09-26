"""检测报告业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from datetime import date
from typing import Any

from app.store import store

MODULE = "report"
REQUIRED_FIELDS = ["报告编号", "委托单位", "样品名称"]
OPTIONAL_FIELDS = ["报告类型", "编制人", "批准人", "签发日期"]
ALL_FIELDS = REQUIRED_FIELDS + OPTIONAL_FIELDS
FIELD_MAX_LENGTH = 100
MAX_ENTRIES = 500
STATUS_ORDER = ["待编制", "编制中", "待批准", "已签发", "已撤回"]
ACTION_RULES = {"编制报告": "编制中", "提交批准": "待批准", "撤回报告": "已撤回"}
NEGATIVE_ACTIONS: list[str] = []


def _safe_int(value: Any, default: int = 0) -> int:
    """异常字段（None、空串、非数字文本）一律回退默认值，不让一条脏数据拖垮整张表。"""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _clean_field(value: Any) -> str | None:
    """把登记值收敛成文本；遇到列表、字典这类无法展示的异常结构时返回 None 让上层报错。"""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float, bool)):
        return str(value)
    return None


class ReportService:
    def list_entries(
        self,
        *,
        filters: dict[str, str] | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        for field, keyword in (filters or {}).items():
            if keyword:
                rows = [row for row in rows if keyword in str(row.get(field) or "")]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def summary(self) -> list[dict[str, Any]]:
        """数量指标：空库时自然归零；签发日期缺失或格式异常的记录不计入本月签发。"""
        rows = store.rows(MODULE)
        month = date.today().strftime("%Y-%m")
        return [
            {"label": "待编制报告", "value": sum(1 for row in rows if row.get("status") in STATUS_ORDER[:2])},
            {"label": "待批准报告", "value": sum(1 for row in rows if row.get("status") == "待批准")},
            {"label": "本月签发", "value": sum(
                1 for row in rows
                if row.get("status") == "已签发" and str(row.get("签发日期") or "").startswith(month)
            )},
        ]

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        """登记一条检测报告；返回 (entry, errors)，errors 非空时说明原因且不写入任何数据。"""
        rows = store.rows(MODULE)
        if len(rows) >= MAX_ENTRIES:
            return None, [f"检测报告数量已达上限 {MAX_ENTRIES} 条，请先归档历史报告再登记"]
        cleaned: dict[str, str] = {}
        errors: list[str] = []
        for field in ALL_FIELDS:
            text = _clean_field(values.get(field))
            if text is None:
                errors.append(f"字段「{field}」格式异常，请填写文本内容")
                continue
            if len(text) > FIELD_MAX_LENGTH:
                errors.append(f"字段「{field}」超过 {FIELD_MAX_LENGTH} 字上限，请缩短后再试")
                continue
            cleaned[field] = text
        missing = [field for field in REQUIRED_FIELDS if not cleaned.get(field)]
        if missing:
            errors.append(f"缺少必填字段：{'、'.join(missing)}")
        if errors:
            return None, errors
        number = cleaned["报告编号"]
        if any(str(row.get("报告编号") or "") == number for row in rows):
            return None, [f"报告编号 {number} 已存在，不能覆盖已有检测报告"]
        entry = {"id": max((_safe_int(row.get("id")) for row in rows), default=0) + 1}
        entry.update(cleaned)
        entry["status"] = STATUS_ORDER[0]
        entry["报告状态"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"检测报告 {entry_id} 不存在或已归档"
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
