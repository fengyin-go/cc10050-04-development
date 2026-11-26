"""解析质量审计领域服务：审计解析模板的字段命中率与失败分布，负责命中率劣化告警与沉淀。

数据链路位置：质量审计层，消费页面解析模板上报的命中数据与失败隔离区的
失败原因分布，产出的审计结论供模板版本升级决策。

复测安排：读取已审阅的试跑对照单（提取差异数据），按对照单里的关联样本与
两版标识校验资格——跨站点页面一律拒绝、样本内容已更正则要求重新审阅；
受理后把复测结果写回本模块，作为模板升级判定的依据。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from app.services.base import BaseModuleService
from app.services.page_parser import TRIAL_TABLE, content_revision
from app.store import store


class ParseAuditService(BaseModuleService):
    MODULE = "parse_audit"
    ENTITY = "审计明细"
    OPERATION_TERM = "解析"
    LIST_FIELDS = ["审计时间", "解析模板", "样本总数", "字段命中率", "失败原因分布"]
    REQUIRED_FIELDS = ["审计时间", "解析模板", "样本总数"]
    STATUS_ORDER = ["正常", "命中率下降", "解析异常"]
    ACTION_RULES = {"查看详情": "命中率下降", "忽略告警": "解析异常"}
    NEGATIVE_ACTIONS = ["忽略告警"]

    # ---- 业务扩展：命中率审计与劣化告警 ----

    def record_hit_rate(self, template: str, total: int, hit: int) -> dict[str, Any]:
        """记录一次模板命中率审计明细。"""
        if total <= 0:
            return {"ok": False, "message": "样本总数必须为正数"}
        rate = hit / total
        rows = store.rows(self.MODULE)
        aid = max((int(r.get("id", 0)) for r in rows), default=0) + 1
        status = "正常" if rate >= 0.9 else ("命中率下降" if rate >= 0.6 else "解析异常")
        rows.append({
            "id": aid,
            "审计时间": datetime.now(timezone.utc).isoformat(),
            "解析模板": template,
            "样本总数": str(total),
            "字段命中率": f"{rate:.2%}",
            "失败原因分布": "" if rate >= 0.9 else "选择器失配/字段缺失",
            "status": status,
            "pending": status != "正常",
            "abnormal": status == "解析异常",
        })
        return {"ok": True, "message": "审计明细已记录", "audit_id": aid, "rate": f"{rate:.2%}"}

    def detect_degradation(self, entry_id: int) -> dict[str, Any]:
        """对比历史审计检测模板命中率劣化趋势。"""
        entry = store.find(self.MODULE, entry_id)
        if entry is None:
            return {"ok": False, "message": "审计明细不存在"}
        template = entry.get("解析模板", "")
        history = [
            r for r in store.rows(self.MODULE)
            if r.get("解析模板") == template and r.get("id") != entry.get("id")
        ]
        current = float(str(entry.get("字段命中率", "0%")).rstrip("%") or 0)
        worst = max(
            (float(str(r.get("字段命中率", "0%")).rstrip("%") or 0) for r in history),
            default=current,
        )
        degraded = worst - current >= 0.15
        if degraded:
            entry["status"] = "命中率下降"
            entry["pending"] = True
        return {
            "ok": True,
            "message": "劣化检测完成",
            "degraded": degraded,
            "current": f"{current:.2%}",
            "best_before": f"{worst:.2%}",
        }

    def summarize_failures(self, entry_id: int) -> dict[str, Any]:
        """汇总失败隔离区中该模板的失败原因分布。"""
        entry = store.find(self.MODULE, entry_id)
        if entry is None:
            return {"ok": False, "message": "审计明细不存在"}
        reasons: dict[str, int] = {}
        for q in store.rows("failure_quarantine"):
            if q.get("失败阶段") == "解析":
                reason = str(q.get("失败原因", "") or "未知")
                reasons[reason] = reasons.get(reason, 0) + 1
        top = sorted(reasons.items(), key=lambda kv: kv[1], reverse=True)[:3]
        entry["失败原因分布"] = ";".join(f"{k}:{v}" for k, v in top)
        return {"ok": True, "message": "失败分布已汇总", "distribution": top}

    def recommend_template_upgrade(self, entry_id: int) -> dict[str, Any]:
        """命中率持续下降时建议模板升级版本。"""
        entry = store.find(self.MODULE, entry_id)
        if entry is None:
            return {"ok": False, "message": "审计明细不存在"}
        if entry.get("status") == "正常":
            return {"ok": True, "message": "模板健康，无需升级", "upgrade": False}
        template = next(
            (t for t in store.rows("page_parser")
             if t.get("模板名称") == entry.get("解析模板", "")), None
        )
        if template is None:
            return {"ok": False, "message": "关联模板不存在"}
        return {
            "ok": True,
            "message": "建议升级模板解析版本",
            "upgrade": True,
            "template": template.get("模板名称", ""),
            "current_version": template.get("解析版本", ""),
        }

    def publish_metrics(self, entry_id: int) -> dict[str, Any]:
        """把审计结论发布到采集量指标作为解析量口径。"""
        entry = store.find(self.MODULE, entry_id)
        if entry is None:
            return {"ok": False, "message": "审计明细不存在"}
        metrics = store.rows("collect_metrics")
        row = next((m for m in metrics if m.get("站点名称") == entry.get("解析模板", "")), None)
        if row is None:
            mid = max((int(m.get("id", 0)) for m in metrics), default=0) + 1
            metrics.append({
                "id": mid,
                "统计时间": datetime.now(timezone.utc).isoformat(),
                "站点名称": entry.get("解析模板", ""),
                "抓取量": entry.get("样本总数", "0"),
                "解析量": entry.get("样本总数", "0"),
                "产出量": "0",
                "status": entry.get("status", "正常"),
                "pending": True,
                "abnormal": entry.get("status") == "解析异常",
            })
        else:
            row["解析量"] = entry.get("样本总数", "0")
            row["统计时间"] = datetime.now(timezone.utc).isoformat()
        return {"ok": True, "message": "审计结论已发布指标"}

    def audit_health(self, days: int = 1) -> dict[str, Any]:
        """输出审计批次健康度统计。"""
        rows = store.rows(self.MODULE)
        abnormal = sum(1 for r in rows if r.get("status") == "解析异常")
        degraded = sum(1 for r in rows if r.get("status") == "命中率下降")
        return {
            "ok": True,
            "message": "审计健康度统计完成",
            "total": len(rows),
            "abnormal": abnormal,
            "degraded": degraded,
        }

    # ---- 复测安排：读取已审阅的提取差异，校验资格后写回复测结果 ----

    def _find_trial(self, trial_id: int) -> dict[str, Any] | None:
        return next(
            (t for t in store.rows(TRIAL_TABLE) if int(t.get("id", 0)) == trial_id),
            None,
        )

    @staticmethod
    def _version_rank(version: str) -> int:
        digits = "".join(ch for ch in str(version) if ch.isdigit())
        return int(digits) if digits else 0

    def _check_retest_eligibility(
        self, trial: dict[str, Any], sample: dict[str, Any] | None
    ) -> tuple[list[str], dict[str, Any] | None, dict[str, Any] | None]:
        """按已审阅对照单里的关联样本与两版标识校验复测资格，返回拒绝原因列表。"""
        reasons: list[str] = []
        template_a = template_b = None
        if trial.get("审阅状态") != "已审阅":
            reasons.append("对照单未处于已审阅状态，审计只能读取已审阅的提取差异数据")
        if sample is None:
            reasons.append("对照单关联的页面样本不存在")
            return reasons, None, None
        template_a = store.find("page_parser", int(trial["模板A"]["id"]))
        template_b = store.find("page_parser", int(trial["模板B"]["id"]))
        if template_a is None or template_b is None:
            reasons.append("对照单关联的模板版本不存在")
            return reasons, template_a, template_b
        site = str(sample.get("站点名称", ""))
        if (
            template_a.get("适用站点") != site
            or template_b.get("适用站点") != site
            or trial.get("站点名称") != site
        ):
            reasons.append("跨站点拿来的页面不能作为本站模板的复测输入，即使两版差异相同也要拒绝")
        if str(template_a.get("解析版本", "")) != str(trial["模板A"].get("解析版本", "")) or str(
            template_b.get("解析版本", "")
        ) != str(trial["模板B"].get("解析版本", "")):
            reasons.append("模板解析版本已变更，对照单不再代表当前两版，需重新试跑")
        current = content_revision(sample)
        bound = int(trial.get("内容版本", 1))
        if current != bound:
            reasons.append(
                f"样本采集内容已更正（对照单绑定 rev{bound}，当前 rev{current}）"
            )
        return reasons, template_a, template_b

    def schedule_retest(self, trial_id: int) -> dict[str, Any]:
        """安排复测：校验资格，受理或拒绝都写审计数据；只写对照与审计，不动线上样本。"""
        trial = self._find_trial(trial_id)
        if trial is None:
            return {"ok": False, "scheduled": False, "message": f"对照单 {trial_id} 不存在"}
        sample = store.find("sample_store", int(trial.get("样本ID", 0)))
        reasons, template_a, template_b = self._check_retest_eligibility(trial, sample)
        accepted = not reasons
        field_rows = trial.get("字段对照", [])
        candidate_label = ""
        conclusion = ""
        hit_rate_text = "0.00%"
        if accepted:
            rank_a = self._version_rank(trial["模板A"].get("解析版本", ""))
            rank_b = self._version_rank(trial["模板B"].get("解析版本", ""))
            candidate_key = "B" if rank_b >= rank_a else "A"
            candidate = trial[f"模板{candidate_key}"]
            candidate_label = f"{candidate['模板名称']}@{candidate['解析版本']}"
            total = len(field_rows) or 1
            hits = sum(1 for row in field_rows if row.get(f"{candidate_key}值") is not None)
            hit_rate = hits / total
            hit_rate_text = f"{hit_rate:.2%}"
            missing = trial.get("缺失字段", {}).get(f"版本{candidate_key}", [])
            if missing:
                conclusion = f"可用于升级判定：{candidate_label} 仍缺字段 {','.join(missing)}，暂缓升级"
            elif any(row.get("结论") in ("A缺失", "B缺失", "差异") for row in field_rows):
                conclusion = f"可用于升级判定：{candidate_label} 字段更全，建议升级到该版本"
            else:
                conclusion = f"可用于升级判定：两版提取一致，{candidate_label} 可平滑升级"
        else:
            conclusion = "需重新审阅：" + "；".join(reasons)
        rows = store.rows(self.MODULE)
        aid = max((int(r.get("id", 0)) for r in rows), default=0) + 1
        record = {
            "id": aid,
            "审计时间": datetime.now(timezone.utc).isoformat(),
            "解析模板": f"{trial['模板A']['模板名称']}（{trial['模板A']['解析版本']} vs {trial['模板B']['解析版本']}）",
            "样本总数": "1",
            "字段命中率": hit_rate_text,
            "失败原因分布": "" if accepted else "；".join(reasons),
            "status": "正常" if accepted else "解析异常",
            "pending": not accepted,
            "abnormal": not accepted,
            "记录类型": "复测",
            "对照单ID": trial.get("id"),
            "样本ID": trial.get("样本ID"),
            "样本批次": trial.get("样本批次", ""),
            "站点名称": trial.get("站点名称", ""),
            "内容版本": trial.get("内容版本"),
            "版本A": f"{trial['模板A']['模板名称']}@{trial['模板A']['解析版本']}",
            "版本B": f"{trial['模板B']['模板名称']}@{trial['模板B']['解析版本']}",
            "价格字段差异": json.dumps(field_rows, ensure_ascii=False),
            "绑定原文": trial.get("绑定原文", ""),
            "受理状态": "已受理" if accepted else "已拒绝",
            "资格说明": "资格校验通过：已审阅、同站点、原文未更正" if accepted else "；".join(reasons),
            "复测结论": conclusion,
            "可用于升级": accepted,
        }
        rows.append(record)
        if accepted:
            trial["复测状态"] = "已安排"
            trial["复测ID"] = aid
            message = f"复测已安排，记录 #{aid} 已写入解析质量审计，可用于升级判定"
        else:
            trial["复测状态"] = "要求复查"
            trial["复测ID"] = aid
            if any("更正" in reason for reason in reasons):
                trial["审阅状态"] = "需重新审阅"
            message = f"复测未受理，要求复查：{'；'.join(reasons)}"
        return {
            "ok": True,
            "scheduled": accepted,
            "message": message,
            "trial": trial,
            "retest": record,
        }

    def list_retests(self) -> list[dict[str, Any]]:
        """复测记录列表（含已受理与已拒绝），最新在前。"""
        rows = [r for r in store.rows(self.MODULE) if r.get("记录类型") == "复测"]
        return sorted(rows, key=lambda r: int(r.get("id", 0)), reverse=True)

    def get_retest(self, retest_id: int) -> dict[str, Any] | None:
        """单条复测记录：差异视图的数据源。"""
        record = store.find(self.MODULE, retest_id)
        if record is None or record.get("记录类型") != "复测":
            return None
        return record
