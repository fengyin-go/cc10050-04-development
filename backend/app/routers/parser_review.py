"""模板试跑对照接口：试跑对照单、审阅、复测安排与样本采集更正。

这些端点只写对照（parser_trial）与审计（parse_audit）数据；
样本库的生产解析状态与价格由 sample_store 的正式流程维护，试跑不回写。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services import service_for
from app.services.page_parser import PageParserService
from app.services.parse_audit import ParseAuditService
from app.services.sample_store import SampleStoreService

router = APIRouter(prefix="/api/parser-review", tags=["模板试跑对照"])


class TrialPayload(BaseModel):
    sample_id: int
    template_a_id: int
    template_b_id: int


class CorrectPayload(BaseModel):
    content: str = Field(min_length=1)
    reason: str | None = None


def _parser_service() -> PageParserService:
    service = service_for("page_parser")
    assert isinstance(service, PageParserService)
    return service


def _audit_service() -> ParseAuditService:
    service = service_for("parse_audit")
    assert isinstance(service, ParseAuditService)
    return service


def _sample_service() -> SampleStoreService:
    service = service_for("sample_store")
    assert isinstance(service, SampleStoreService)
    return service


@router.get("/trials")
def list_trials() -> dict[str, Any]:
    """对照单列表：复核视图的入口数据。"""
    items = _parser_service().list_trials()
    return {"items": items, "total": len(items)}


@router.post("/trials")
def start_trial(payload: TrialPayload) -> dict[str, Any]:
    """发起试跑：指定页面样本 + 两个模板版本，同一份原文上对照解析。"""
    return _parser_service().start_trial(
        payload.sample_id, payload.template_a_id, payload.template_b_id
    )


@router.get("/trials/{trial_id}")
def get_trial(trial_id: int) -> dict[str, Any]:
    """对照单详情：含样本当前内容版本，便于发现打开期间发生的采集更正。"""
    trial = _parser_service().get_trial(trial_id)
    if trial is None:
        raise HTTPException(status_code=404, detail=f"对照单 {trial_id} 不存在")
    return trial


@router.post("/trials/{trial_id}/review")
def review_trial(trial_id: int) -> dict[str, Any]:
    """审阅对照单：通过后才允许安排复测。"""
    return _parser_service().review_trial(trial_id)


@router.post("/trials/{trial_id}/rerun")
def rerun_trial(trial_id: int) -> dict[str, Any]:
    """按样本当前内容重新试跑，生成新的对照单。"""
    return _parser_service().rerun_trial(trial_id)


@router.post("/trials/{trial_id}/schedule")
def schedule_retest(trial_id: int) -> dict[str, Any]:
    """安排复测：审计服务校验资格，受理或要求复查都写回复测结果。"""
    return _audit_service().schedule_retest(trial_id)


@router.get("/retests")
def list_retests() -> dict[str, Any]:
    """复测记录列表：解析质量审计页的复测区。"""
    items = _audit_service().list_retests()
    return {"items": items, "total": len(items)}


@router.get("/retests/{retest_id}")
def get_retest(retest_id: int) -> dict[str, Any]:
    """单条复测记录：差异视图展示价格字段、绑定原文与资格说明。"""
    record = _audit_service().get_retest(retest_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"复测记录 {retest_id} 不存在")
    return record


@router.post("/samples/{sample_id}/correct")
def correct_sample(sample_id: int, payload: CorrectPayload) -> dict[str, Any]:
    """采集层更正样本原文：内容版本 +1，线上解析状态与价格不变。"""
    return _sample_service().correct_content(
        sample_id, payload.content, payload.reason or ""
    )
