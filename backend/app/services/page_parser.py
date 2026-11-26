"""页面解析模板领域服务：管理商品页HTML选择器与字段映射，负责把原始页面解析为结构化价格字段。

数据链路位置：解析层，消费样本库中的页面样本，按模板选择器提取价格字段，
产出的结构化数据交给规格归一器与解析审计。

复核视图（试跑对照单）：选一份页面样本与两个模板版本做同原文试解析，
两版共用对照单绑定的原文快照，逐字段保留版本标识与来源；试跑只写
parser_trial 对照数据，绝不回写样本库的线上解析状态与价格。
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from app.services.base import BaseModuleService
from app.store import store

TRIAL_TABLE = "parser_trial"

# 样本原始内容里的取值节点：<span class="price-promo">48</span> 这类片段。
_NODE_RE = re.compile(r'<([a-zA-Z][\w-]*)(?:\s+class="([^"]+)")?\s*>([^<]*)</\1>')


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def content_revision(sample: dict[str, Any]) -> int:
    """样本当前内容版本：每次采集更正 +1，对照单按版本绑定原文。"""
    return int(sample.get("内容版本", 1) or 1)


def _content_nodes(html: str) -> dict[str, str]:
    """把原始HTML摘要解析成 选择器键 -> 文本 的取值表（class 优先，标签兜底）。"""
    nodes: dict[str, str] = {}
    for tag, classes, text in _NODE_RE.findall(html or ""):
        text = text.strip()
        for token in (classes or "").split():
            nodes.setdefault(token, text)
        nodes.setdefault(tag, text)
    return nodes


def _parse_mapping(mapping: str) -> list[tuple[str, str]]:
    """字段映射格式：`原价=price-origin;促销价=price-promo`，兼容冒号与中文分号。"""
    pairs: list[tuple[str, str]] = []
    for item in re.split(r"[;；\n]", mapping or ""):
        item = item.strip()
        if not item:
            continue
        if "=" in item:
            field, selector = item.split("=", 1)
        elif ":" in item:
            field, selector = item.split(":", 1)
        else:
            continue
        selector = selector.strip()
        if "." in selector:
            selector = selector.split(".")[-1]
        selector = selector.lstrip(".#").strip()
        field = field.strip()
        if field and selector:
            pairs.append((field, selector))
    return pairs


def _extract_with_template(template: dict[str, Any], nodes: dict[str, str]) -> tuple[list[dict[str, Any]], list[str]]:
    """用单个模板版本试解析：逐字段记录取值与来源（模板标识 + 选择器），并列出缺失。"""
    label = f"{template.get('模板名称', '')}@{template.get('解析版本', '')}"
    fields: list[dict[str, Any]] = []
    missing: list[str] = []
    for field, selector in _parse_mapping(str(template.get("字段映射", ""))):
        value = nodes.get(selector)
        if value:
            fields.append({"字段": field, "值": value, "来源": f"{label} · {selector}", "选择器": selector})
        else:
            fields.append({"字段": field, "值": None, "来源": None, "选择器": selector})
            missing.append(field)
    return fields, missing


def _build_field_rows(
    template_a: dict[str, Any], template_b: dict[str, Any], nodes: dict[str, str]
) -> tuple[list[dict[str, Any]], dict[str, list[str]]]:
    """并排两版提取结果：字段并集保持 A 先 B 后的声明顺序，逐字段给对照结论。"""
    fields_a, _missed_a = _extract_with_template(template_a, nodes)
    fields_b, _missed_b = _extract_with_template(template_b, nodes)
    by_field_a = {item["字段"]: item for item in fields_a}
    by_field_b = {item["字段"]: item for item in fields_b}
    ordered: list[str] = []
    for item in [*fields_a, *fields_b]:
        if item["字段"] not in ordered:
            ordered.append(item["字段"])
    rows: list[dict[str, Any]] = []
    for field in ordered:
        left = by_field_a.get(field, {"值": None, "来源": None})
        right = by_field_b.get(field, {"值": None, "来源": None})
        if left["值"] is not None and right["值"] is not None:
            verdict = "一致" if left["值"] == right["值"] else "差异"
        elif left["值"] is None and right["值"] is None:
            verdict = "均缺失"
        elif left["值"] is None:
            verdict = "A缺失"
        else:
            verdict = "B缺失"
        rows.append({
            "字段": field,
            "A值": left["值"], "A来源": left["来源"],
            "B值": right["值"], "B来源": right["来源"],
            "结论": verdict,
        })
    # 缺失按字段并集口径汇总：任一版本没取到的字段都要列出来。
    missing_summary = {
        "版本A": [row["字段"] for row in rows if row["A值"] is None],
        "版本B": [row["字段"] for row in rows if row["B值"] is None],
    }
    return rows, missing_summary


class PageParserService(BaseModuleService):
    MODULE = "page_parser"
    ENTITY = "解析模板"
    OPERATION_TERM = "解析"
    LIST_FIELDS = ["模板名称", "适用站点", "选择器路径", "字段映射", "解析版本"]
    REQUIRED_FIELDS = ["模板名称", "适用站点", "选择器路径"]
    STATUS_ORDER = ["草稿", "已启用", "已废弃"]
    ACTION_RULES = {"启用模板": "已启用", "废弃模板": "已废弃"}
    NEGATIVE_ACTIONS = []

    # ---- 业务扩展：模板解析与字段提取 ----

    def enable_template(self, entry_id: int) -> dict[str, Any]:
        """启用解析模板，校验选择器与字段映射完整性。"""
        entry = store.find(self.MODULE, entry_id)
        if entry is None:
            return {"ok": False, "message": f"{self.ENTITY} {entry_id} 不存在"}
        selector = entry.get("选择器路径", "")
        mapping = entry.get("字段映射", "")
        if not selector or "price" not in selector:
            return {"ok": False, "message": "选择器路径缺少价格节点，不能启用"}
        if not mapping:
            return {"ok": False, "message": "字段映射为空，不能启用"}
        entry["status"] = "已启用"
        entry["pending"] = False
        return {"ok": True, "message": f"模板 {entry.get('模板名称', '')} 已启用"}

    def deprecate_template(self, entry_id: int) -> dict[str, Any]:
        """废弃模板并检查是否有站点仍依赖该模板。"""
        entry = store.find(self.MODULE, entry_id)
        if entry is None:
            return {"ok": False, "message": "模板不存在"}
        site = entry.get("适用站点", "")
        pending_samples = [
            s for s in store.rows("sample_store")
            if s.get("站点名称") == site and s.get("status") == "已保存"
        ]
        entry["status"] = "已废弃"
        entry["abnormal"] = bool(pending_samples)
        return {
            "ok": True,
            "message": "模板已废弃",
            "blocking_samples": len(pending_samples),
        }

    def parse_sample(self, entry_id: int, sample_id: int) -> dict[str, Any]:
        """用模板解析指定样本，产出结构化字段并更新样本状态。"""
        entry = store.find(self.MODULE, entry_id)
        if entry is None or entry.get("status") != "已启用":
            return {"ok": False, "message": "模板不存在或未启用"}
        sample = store.find("sample_store", sample_id)
        if sample is None:
            return {"ok": False, "message": f"样本 {sample_id} 不存在"}
        if sample.get("站点名称") != entry.get("适用站点"):
            return {"ok": False, "message": "样本站点与模板适用站点不匹配"}
        sample["status"] = "已解析"
        sample["pending"] = False
        return {
            "ok": True,
            "message": "样本解析完成",
            "fields": entry.get("字段映射", ""),
            "version": entry.get("解析版本", ""),
        }

    def report_to_audit(self, entry_id: int, hit_rate: float) -> dict[str, Any]:
        """向解析质量审计上报字段命中率。"""
        entry = store.find(self.MODULE, entry_id)
        if entry is None:
            return {"ok": False, "message": "模板不存在"}
        rows = store.rows("parse_audit")
        aid = max((int(r.get("id", 0)) for r in rows), default=0) + 1
        rate_text = f"{hit_rate:.2%}"
        status = "正常" if hit_rate >= 0.9 else "命中率下降"
        rows.append({
            "id": aid,
            "审计时间": datetime.now(timezone.utc).isoformat(),
            "解析模板": entry.get("模板名称", ""),
            "样本总数": "1",
            "字段命中率": rate_text,
            "失败原因分布": "" if hit_rate >= 0.9 else "选择器失配",
            "status": status,
            "pending": True,
            "abnormal": hit_rate < 0.9,
        })
        return {"ok": True, "message": "命中率已上报审计", "audit_id": aid, "rate": rate_text}

    def route_failures(self, entry_id: int, reason: str) -> dict[str, Any]:
        """解析失败时把样本送入失败隔离区。"""
        entry = store.find(self.MODULE, entry_id)
        if entry is None:
            return {"ok": False, "message": "模板不存在"}
        rows = store.rows("failure_quarantine")
        fid = max((int(r.get("id", 0)) for r in rows), default=0) + 1
        rows.append({
            "id": fid,
            "样本指纹": f"parse-{entry_id}-{fid}",
            "失败阶段": "解析",
            "失败原因": reason,
            "隔离时间": datetime.now(timezone.utc).isoformat(),
            "重试次数": "0",
            "status": "待处理",
            "pending": True,
            "abnormal": False,
        })
        return {"ok": True, "message": "失败样本已隔离", "quarantine_id": fid}

    def bump_version(self, entry_id: int) -> dict[str, Any]:
        """升级模板解析版本并触发基线重算。"""
        entry = store.find(self.MODULE, entry_id)
        if entry is None:
            return {"ok": False, "message": "模板不存在"}
        current = str(entry.get("解析版本", "v1"))
        entry["解析版本"] = f"v{int(current.lstrip('v') or 1) + 1}"
        for base in store.rows("price_baseline"):
            if base.get("status") == "已生效":
                base["status"] = "待重算"
                base["pending"] = True
        return {
            "ok": True,
            "message": "解析版本已升级，基线已标记重算",
            "version": entry.get("解析版本"),
        }

    # ---- 复核视图：同一份原文上的两版试跑对照 ----

    def _trial_rows(self) -> list[dict[str, Any]]:
        return store.rows(TRIAL_TABLE)

    def _version_brief(self, template: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": template.get("id"),
            "模板名称": template.get("模板名称", ""),
            "解析版本": template.get("解析版本", ""),
            "适用站点": template.get("适用站点", ""),
        }

    def _run_trial(
        self,
        sample: dict[str, Any],
        template_a: dict[str, Any],
        template_b: dict[str, Any],
    ) -> dict[str, Any]:
        """生成对照单：两版共用同一份原文快照，只写 parser_trial，不动样本库。"""
        raw = str(sample.get("原始HTML摘要", ""))
        nodes = _content_nodes(raw)
        field_rows, missing = _build_field_rows(template_a, template_b, nodes)
        rows = self._trial_rows()
        trial = {
            "id": max((int(t.get("id", 0)) for t in rows), default=0) + 1,
            "样本ID": sample.get("id"),
            "样本批次": sample.get("样本批次", ""),
            "站点名称": sample.get("站点名称", ""),
            "内容版本": content_revision(sample),
            "模板A": self._version_brief(template_a),
            "模板B": self._version_brief(template_b),
            "字段对照": field_rows,
            "缺失字段": missing,
            "样本来源": {
                "样本批次": sample.get("样本批次", ""),
                "站点名称": sample.get("站点名称", ""),
                "抓取时间": sample.get("抓取时间", ""),
                "样本指纹": sample.get("样本指纹", ""),
            },
            "绑定原文": raw,
            "审阅状态": "待审阅",
            "复测状态": "未安排",
            "复测ID": None,
            "创建时间": _utcnow(),
            "审阅时间": None,
        }
        rows.append(trial)
        return trial

    def start_trial(self, sample_id: int, template_a_id: int, template_b_id: int) -> dict[str, Any]:
        """发起试跑：校验样本与两版模板同站点，随后在同一份原文上对照解析。"""
        sample = store.find("sample_store", sample_id)
        if sample is None:
            return {"ok": False, "message": f"页面样本 {sample_id} 不存在"}
        if template_a_id == template_b_id:
            return {"ok": False, "message": "试跑需要选择两个不同的模板版本"}
        template_a = store.find(self.MODULE, template_a_id)
        template_b = store.find(self.MODULE, template_b_id)
        if template_a is None or template_b is None:
            return {"ok": False, "message": "所选模板版本不存在"}
        site = str(sample.get("站点名称", ""))
        if template_a.get("适用站点") != site or template_b.get("适用站点") != site:
            return {
                "ok": False,
                "message": "跨站点拿来的页面不能作为本站模板的试跑输入，即使两版差异相同也要拒绝",
            }
        if str(template_a.get("解析版本", "")) == str(template_b.get("解析版本", "")):
            return {"ok": False, "message": "两个试跑版本的解析版本号不能相同"}
        trial = self._run_trial(sample, template_a, template_b)
        return {"ok": True, "message": f"试跑完成，对照单 #{trial['id']} 已生成", "trial": trial}

    def list_trials(self) -> list[dict[str, Any]]:
        """对照单列表，最新在前。"""
        return sorted(self._trial_rows(), key=lambda t: int(t.get("id", 0)), reverse=True)

    def get_trial(self, trial_id: int) -> dict[str, Any] | None:
        """对照单详情：附带样本当前内容版本与线上解析记录，便于核对是否已更正。"""
        trial = next((t for t in self._trial_rows() if int(t.get("id", 0)) == trial_id), None)
        if trial is None:
            return None
        detail = dict(trial)
        sample = store.find("sample_store", int(trial.get("样本ID", 0)))
        if sample is not None:
            detail["样本当前内容版本"] = content_revision(sample)
            detail["样本当前状态"] = sample.get("status", "")
            detail["样本线上解析价格"] = sample.get("线上解析价格", "")
        return detail

    def review_trial(self, trial_id: int) -> dict[str, Any]:
        """审阅对照单：只有绑定原文仍是样本当前内容时才允许标记已审阅。"""
        trial = next((t for t in self._trial_rows() if int(t.get("id", 0)) == trial_id), None)
        if trial is None:
            return {"ok": False, "message": "对照单不存在"}
        sample = store.find("sample_store", int(trial.get("样本ID", 0)))
        if sample is not None and content_revision(sample) != int(trial.get("内容版本", 1)):
            trial["审阅状态"] = "需重新审阅"
            return {
                "ok": False,
                "message": "样本采集内容已更正，本对照单绑定的是旧原文，请重新试跑后再审阅",
                "trial": trial,
            }
        trial["审阅状态"] = "已审阅"
        trial["审阅时间"] = _utcnow()
        return {"ok": True, "message": "对照单已审阅，差异数据可供解析质量审计读取", "trial": trial}

    def rerun_trial(self, trial_id: int) -> dict[str, Any]:
        """按样本当前内容重新试跑：生成新的对照单，旧对照单保留不覆盖。"""
        trial = next((t for t in self._trial_rows() if int(t.get("id", 0)) == trial_id), None)
        if trial is None:
            return {"ok": False, "message": "对照单不存在"}
        sample = store.find("sample_store", int(trial.get("样本ID", 0)))
        if sample is None:
            return {"ok": False, "message": "关联样本不存在"}
        template_a = store.find(self.MODULE, int(trial["模板A"]["id"]))
        template_b = store.find(self.MODULE, int(trial["模板B"]["id"]))
        if template_a is None or template_b is None:
            return {"ok": False, "message": "关联模板版本不存在"}
        new_trial = self._run_trial(sample, template_a, template_b)
        return {
            "ok": True,
            "message": f"已按样本当前内容（rev{new_trial['内容版本']}）重新试跑，对照单 #{new_trial['id']} 待审阅",
            "trial": new_trial,
        }
