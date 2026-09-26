"""检测报告接口：维护检测报告，覆盖编制报告、提交批准、撤回报告等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.report import ReportService

router = APIRouter(prefix="/api/report", tags=["检测报告"])

service = ReportService()

FILTER_FIELDS = ["报告编号", "委托单位", "样品名称"]
STATUSES = ["待编制", "编制中", "待批准", "已签发", "已撤回"]
PAGE_SIZE_MAX = 200


@router.get("", response_model=PageResult[dict])
def list_entries(
    报告编号: str | None = Query(default=None, description="按报告编号模糊检索"),
    委托单位: str | None = Query(default=None, description="按委托单位模糊检索"),
    样品名称: str | None = Query(default=None, description="按样品名称模糊检索"),
    status: str | None = Query(default=None, description="待编制、编制中、待批准、已签发、已撤回"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按报告编号、委托单位、样品名称过滤检测报告列表；没有数据时返回空页，不报错。"""
    if page < 1:
        raise HTTPException(status_code=400, detail="页码从 1 开始，请调整分页参数")
    if size < 1 or size > PAGE_SIZE_MAX:
        raise HTTPException(status_code=400, detail=f"每页 1 到 {PAGE_SIZE_MAX} 条，请调整分页范围")
    raw = {"报告编号": 报告编号, "委托单位": 委托单位, "样品名称": 样品名称}
    filters = {field: (value or "").strip() for field, value in raw.items()}
    items, total = service.list_entries(filters=filters, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/stats")
def stats() -> dict[str, Any]:
    """数量指标：待编制、待批准与本月签发；空库时全部归零，不报错。"""
    return {"stats": service.summary()}


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出检测报告清单：返回当前全量数据。"""
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
    """登记一条检测报告，缺字段、字段异常或编号重复时说明原因而不是静默丢弃。"""
    entry, errors = service.create_entry(payload.values)
    if errors:
        return ActionResult(ok=False, message="；".join(errors))
    return ActionResult(ok=True, message="检测报告已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条检测报告执行编制报告、提交批准、撤回报告；不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
