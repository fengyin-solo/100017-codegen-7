"""检测报告接口：维护检测报告，覆盖编制报告、提交批准、撤回报告等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.report import STATUS_ORDER, ReportService

router = APIRouter(prefix="/api/report", tags=["检测报告"])

service = ReportService()

LIST_FIELDS = ["报告编号", "委托单位", "样品名称", "报告类型", "编制人", "批准人", "签发日期", "报告状态"]
STATUSES = STATUS_ORDER


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按报告编号检索"),
    client: str | None = Query(default=None, description="按委托单位检索"),
    sample: str | None = Query(default=None, description="按样品名称检索"),
    status: str | None = Query(default=None, description="待编制、编制中、待批准、已签发、已撤回"),
    page: int = Query(default=1, ge=1, description="页码，从 1 开始"),
    size: int = Query(default=20, ge=1, le=200, description="每页条数，1-200"),
) -> PageResult[dict]:
    """按报告编号、委托单位、样品名称与状态过滤检测报告列表；没有数据时返回空页，不报错。"""
    if status and status not in STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"报告状态「{status}」不支持，可选：{'、'.join(STATUSES)}",
        )
    items, total = service.list_entries(
        keyword=keyword, client=client, sample=sample, status=status, page=page, size=size
    )
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/stats")
def get_stats() -> dict[str, int]:
    """数量指标：待编制报告、待批准报告、本月签发；始终随清单当前口径返回。"""
    return service.get_stats()


# 静态路径必须声明在 /{entry_id} 之前，否则会被当成报告 id 解析。
@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出检测报告清单：返回当前全量数据；空库时返回空清单，不报错。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "report", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条检测报告明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"检测报告 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条检测报告，缺字段或编号重复时说明原因而不是静默丢弃或覆盖旧记录。"""
    entry, missing, conflict = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    if conflict:
        return ActionResult(ok=False, message=conflict)
    return ActionResult(ok=True, message="检测报告已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条检测报告执行编制报告、提交批准、撤回报告；不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
