#!/usr/bin/env python3
"""
Bounded run-level metrics and effectiveness reporting for Agent-Memory.
"""

import json
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Iterable, List, Optional

if TYPE_CHECKING:
    from memory import MemorySystem


DEFAULT_METRICS_STATE = {
    "active_trace_id": None,
    "updated_at": None,
}

OUTCOME_CLASS_OPEN = "open_run"
OUTCOME_CLASS_CLEAN = "clean_run"
OUTCOME_CLASS_CORRECTED = "corrected_run"
OUTCOME_CLASS_ERROR = "error_run"
OUTCOME_CLASS_CORRECTED_AND_ERROR = "corrected_and_error"

SUCCESS_OUTCOMES = {"success", "completed", "done", "ok"}
FAILURE_OUTCOMES = {"failure", "failed", "error", "partial_failure", "partial", "renderer_failed"}

PHASE2_CATEGORY_ALIASES = {
    "communication_style": "communication_style",
    "response_style": "communication_style",
    "style": "communication_style",
    "format": "output_contract",
    "output_format": "output_contract",
    "response_format": "output_contract",
    "output_contract": "output_contract",
    "workflow": "workflow.evidence_first",
    "workflow.evidence_first": "workflow.evidence_first",
    "evidence_first": "workflow.evidence_first",
}

PHASE2_CATEGORY_RULES = {
    "communication_style": {
        "concise": ["concise", "brief", "shorter", "简洁", "简短"],
        "direct": ["direct", "直接", "straight to the point"],
        "natural": ["natural", "自然", "less robotic"],
        "verbose": ["verbose", "wordy", "啰嗦", "冗长"],
        "too_long": ["too long", "long answer", "long response", "回复很长", "回答很长", "太长"],
        "mechanical": ["mechanical", "robotic", "机械", "模板化"],
    },
    "output_contract": {
        "json_output": ["json", "json格式", "valid json"],
        "markdown": ["markdown", "md格式"],
        "bullet_points": ["bullet", "bullet points", "bullets", "要点", "列表"],
        "no_table": ["no table", "don't use tables", "不要表格", "别用表格"],
        "used_table": ["table", "表格"],
        "exact_structure": ["exact structure", "fixed structure", "固定结构", "按照这个结构"],
    },
    "workflow.evidence_first": {
        "read_logs": [
            "read logs",
            "check logs",
            "check local logs",
            "look at logs",
            "read the logs",
            "local logs",
            "logs",
            "看日志",
            "检查日志",
            "查看日志",
        ],
        "read_docs": ["read docs", "check docs", "read documentation", "read the docs", "看文档", "读文档", "查看文档"],
        "verify_first": ["verify", "validate", "confirm first", "先验证", "先确认", "验证后"],
        "evidence_first": ["evidence first", "based on evidence", "先看证据", "根据证据"],
        "no_guessing": ["don't guess", "stop guessing", "guessed", "guessing", "不要猜", "别猜", "猜测", "臆测"],
        "root_cause": ["root cause", "diagnosis", "diagnose", "根因", "诊断"],
        "missing_logs": ["without checking logs", "didn't check logs", "没看日志", "未检查日志", "跳过日志"],
        "skipped_docs": ["didn't read docs", "没看文档", "未看文档", "跳过文档"],
        "no_verification": ["without verifying", "didn't verify", "未验证", "没有验证"],
    },
}

COMMUNICATION_STYLE_CONTRADICTIONS = {
    "concise": {"verbose", "too_long"},
    "direct": {"mechanical"},
    "natural": {"mechanical"},
}

OUTPUT_CONTRACT_CONTRADICTIONS = {
    "no_table": {"used_table"},
    "json_output": {"exact_structure", "json_output"},
    "markdown": {"markdown"},
    "bullet_points": {"bullet_points"},
}

WORKFLOW_CONTRADICTIONS = {
    "read_logs": {"missing_logs", "no_guessing", "read_logs"},
    "read_docs": {"skipped_docs", "read_docs"},
    "verify_first": {"no_verification", "verify_first"},
    "evidence_first": {"missing_logs", "skipped_docs", "no_guessing", "evidence_first"},
}


class MetricsLayer:
    def __init__(self, memory_system: "MemorySystem"):
        self.memory = memory_system
        self.metrics_path = self.memory.base_path / "metrics"
        self.manifests_path = self.metrics_path / "run-manifests.jsonl"
        self.outcomes_path = self.metrics_path / "run-outcomes.jsonl"
        self.assessments_path = self.metrics_path / "assessments.jsonl"
        self.state_path = self.metrics_path / "state.json"
        self.reports_path = self.metrics_path / "reports"
        self._ensure_storage()

    def start_run(
        self,
        context: Dict[str, Any],
        brief: Dict[str, Any],
        decision_brief: Optional[Dict[str, Any]] = None,
        trace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Record what was exposed for a single runtime run."""
        resolved_trace_id = trace_id or self._generate_trace_id()
        resolved_decision_brief = decision_brief or brief.get("decision_brief") or {}

        memory_count_by_type = {
            "strategy": len(brief.get("strategies", [])),
            "preference": len(brief.get("preferences", [])),
            "rule": len(brief.get("rules", [])),
        }
        exposed_memory_ids = self._collect_exposed_ids(brief)
        exposed_memory_types = [
            memory_type
            for memory_type, count in memory_count_by_type.items()
            if count > 0
        ]

        manifest = {
            "trace_id": resolved_trace_id,
            "started_at": datetime.now().isoformat(),
            "bucket": self._build_bucket(context),
            "context": deepcopy(context or {}),
            "exposed_memory_ids": exposed_memory_ids,
            "exposed_memory_types": exposed_memory_types,
            "exposed_memories": self._build_exposed_memories(brief),
            "memory_count_by_type": memory_count_by_type,
            "decision_brief_non_empty": self._decision_brief_non_empty(resolved_decision_brief),
        }
        self._append_jsonl(self.manifests_path, manifest)

        outcome = {
            "trace_id": resolved_trace_id,
            "closed_at": None,
            "outcome_class": OUTCOME_CLASS_OPEN,
            "task_outcome": None,
            "has_correction": False,
            "has_error": False,
            "task_complete_seen": False,
            "feedback_events": [],
            "error_events": [],
        }
        self._append_jsonl(self.outcomes_path, outcome)
        self._set_active_trace_id(resolved_trace_id)
        return manifest

    def record_task_complete(
        self,
        trace_id: Optional[str],
        event: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        resolved_trace_id = self.resolve_trace_id(trace_id)
        if not resolved_trace_id:
            return None

        latest = self._latest_outcome(resolved_trace_id)
        latest["trace_id"] = resolved_trace_id
        latest["task_complete_seen"] = True
        latest["closed_at"] = datetime.now().isoformat()
        latest["task_outcome"] = (event or {}).get("outcome")
        latest["outcome_class"] = self._compute_outcome_class(
            latest["has_correction"],
            latest["has_error"],
            latest["task_complete_seen"],
            latest["task_outcome"],
        )
        self._append_jsonl(self.outcomes_path, latest)
        return latest

    def record_user_feedback(
        self,
        trace_id: Optional[str],
        event: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        resolved_trace_id = self.resolve_trace_id(trace_id)
        if not resolved_trace_id:
            return None

        latest = self._latest_outcome(resolved_trace_id)
        latest["trace_id"] = resolved_trace_id
        latest["has_correction"] = True
        latest["feedback_events"] = self._append_unique(
            latest.get("feedback_events", []),
            self._event_ref(event),
        )
        latest["closed_at"] = datetime.now().isoformat()
        latest["outcome_class"] = self._compute_outcome_class(
            latest["has_correction"],
            latest["has_error"],
            latest.get("task_complete_seen", False),
            latest.get("task_outcome"),
        )
        self._append_jsonl(self.outcomes_path, latest)
        assessments = self._assess_event_against_exposed_memory(
            resolved_trace_id,
            event or {},
        )
        return {
            "outcome": latest,
            "assessments": assessments,
        }

    def record_error(
        self,
        trace_id: Optional[str],
        event: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        resolved_trace_id = self.resolve_trace_id(trace_id)
        if not resolved_trace_id:
            return None

        latest = self._latest_outcome(resolved_trace_id)
        latest["trace_id"] = resolved_trace_id
        latest["has_error"] = True
        latest["error_events"] = self._append_unique(
            latest.get("error_events", []),
            self._event_ref(event),
        )
        latest["closed_at"] = datetime.now().isoformat()
        if not latest.get("task_outcome") and event:
            latest["task_outcome"] = event.get("outcome")
        latest["outcome_class"] = self._compute_outcome_class(
            latest["has_correction"],
            latest["has_error"],
            latest.get("task_complete_seen", False),
            latest.get("task_outcome"),
        )
        self._append_jsonl(self.outcomes_path, latest)
        assessments = self._assess_event_against_exposed_memory(
            resolved_trace_id,
            event or {},
        )
        return {
            "outcome": latest,
            "assessments": assessments,
        }

    def report(
        self,
        window_days: int = 7,
        bucket: Optional[str] = None,
        top_buckets: int = 5,
    ) -> Dict[str, Any]:
        manifests = self._latest_records_by_trace(self.manifests_path)
        outcomes = self._latest_records_by_trace(self.outcomes_path)
        cutoff = datetime.now() - timedelta(days=max(1, int(window_days)))

        runs = []
        for trace_id, manifest in manifests.items():
            started_at = self._parse_timestamp(manifest.get("started_at"))
            if not started_at or started_at < cutoff:
                continue
            if bucket and manifest.get("bucket") != bucket:
                continue

            outcome = outcomes.get(trace_id)
            if not outcome or not self._is_reportable_outcome(outcome):
                continue

            runs.append((manifest, outcome))

        by_memory_type = {
            "strategy": self._empty_type_stats(),
            "preference": self._empty_type_stats(),
            "rule": self._empty_type_stats(),
            "none": self._empty_type_stats(),
        }

        for manifest, outcome in runs:
            exposed_types = list(manifest.get("exposed_memory_types", []))
            if not exposed_types:
                exposed_types = ["none"]
            for memory_type in exposed_types:
                stats = by_memory_type[memory_type]
                stats["runs"] += 1
                if not outcome.get("has_correction") and not outcome.get("has_error"):
                    stats["clean_runs"] += 1
                if outcome.get("has_correction"):
                    stats["corrected_runs"] += 1
                if outcome.get("has_error") or self._is_failure_outcome(outcome.get("task_outcome")):
                    stats["error_runs"] += 1
                if self._is_success_outcome(outcome.get("task_outcome")):
                    stats["successful_runs"] += 1

        normalized = {}
        for memory_type, stats in by_memory_type.items():
            runs_count = stats["runs"]
            if memory_type == "none":
                normalized[memory_type] = {
                    "runs": runs_count,
                    "clean_run_rate": self._rate(stats["clean_runs"], runs_count),
                    "correction_rate": self._rate(stats["corrected_runs"], runs_count),
                    "error_rate": self._rate(stats["error_runs"], runs_count),
                    "success_rate": self._rate(stats["successful_runs"], runs_count),
                }
            else:
                normalized[memory_type] = {
                    "exposed_runs": runs_count,
                    "clean_run_rate": self._rate(stats["clean_runs"], runs_count),
                    "correction_rate": self._rate(stats["corrected_runs"], runs_count),
                    "error_rate": self._rate(stats["error_runs"], runs_count),
                    "success_rate": self._rate(stats["successful_runs"], runs_count),
                }

        bucket_summary = self._aggregate_bucket_summary(runs, top_buckets=top_buckets)
        trace_ids = [manifest["trace_id"] for manifest, _ in runs]
        assessments = self._report_assessments(trace_ids, cutoff)

        report = {
            "generated_at": datetime.now().isoformat(),
            "window_days": max(1, int(window_days)),
            "bucket": bucket,
            "total_runs": len(runs),
            "by_memory_type": normalized,
            "by_bucket": bucket_summary,
            "summary": self._build_summary(normalized, bucket_summary, assessments),
        }
        self._write_report_snapshot(report)
        return report

    def render_report_text(self, report: Dict[str, Any]) -> str:
        bucket_label = report.get("bucket") or "all"
        summary = report.get("summary", {})
        bucket_rows = report.get("by_bucket", [])
        lines = [
            "# Agent-Memory Metrics Report",
            f"Window: {report.get('window_days', 0)} day(s)",
            f"Bucket: {bucket_label}",
            f"Total runs: {report.get('total_runs', 0)}",
        ]

        lines.append("")
        lines.append("## Headline")
        most_exposed = summary.get("most_exposed_type")
        healthiest = summary.get("healthiest_type")
        healthiest_bucket = summary.get("healthiest_bucket")
        contradictions = summary.get("linked_contradictions", 0)
        top_items = summary.get("top_contradicted_items", [])
        verdict = summary.get("headline_verdict")
        top_positive_signal = summary.get("top_positive_signal")
        top_watchouts = summary.get("top_watchouts", [])

        if verdict:
            lines.append(f"- Verdict: {verdict}")

        if most_exposed:
            lines.append(
                f"- Most exposed memory type: {most_exposed['type']} ({most_exposed['runs']} run(s))"
            )
        else:
            lines.append("- Most exposed memory type: not enough data")

        if healthiest:
            lines.append(
                "- Healthiest exposed type: "
                f"{healthiest['type']} "
                f"(clean {self._pct(healthiest['clean_run_rate'])}, "
                f"correction {self._pct(healthiest['correction_rate'])}, "
                f"runs {healthiest['runs']})"
            )
        else:
            lines.append("- Healthiest exposed type: not enough data")

        if healthiest_bucket:
            lines.append(
                "- Healthiest bucket: "
                f"{healthiest_bucket['bucket']} "
                f"(clean {self._pct(healthiest_bucket['clean_run_rate'])}, "
                f"correction {self._pct(healthiest_bucket['correction_rate'])}, "
                f"runs {healthiest_bucket['runs']})"
            )
        else:
            lines.append("- Healthiest bucket: not enough data")

        lines.append(f"- Linked contradictions: {contradictions}")
        if top_items:
            top_item = top_items[0]
            lines.append(
                f"- Most contradicted item: {top_item['memory_id']} "
                f"({top_item['count']} hit(s), category {top_item['signal_category']})"
            )
        else:
            lines.append("- Most contradicted item: none")

        if top_positive_signal:
            lines.append(f"- Positive signal: {top_positive_signal}")

        if top_watchouts:
            lines.append("")
            lines.append("## Top Watchouts")
            for item in top_watchouts[:2]:
                lines.append(f"- {item}")

        lines.append("")
        lines.append("## By Memory Type")
        for memory_type in ("strategy", "preference", "rule", "none"):
            stats = report.get("by_memory_type", {}).get(memory_type, {})
            runs = stats.get("exposed_runs", stats.get("runs", 0))
            lines.append(
                f"- {memory_type}: runs {runs}, "
                f"clean {self._pct(stats.get('clean_run_rate', 0.0))}, "
                f"correction {self._pct(stats.get('correction_rate', 0.0))}, "
                f"error {self._pct(stats.get('error_rate', 0.0))}, "
                f"success {self._pct(stats.get('success_rate', 0.0))}"
            )

        if bucket_rows:
            lines.append("")
            lines.append("## Bucket Comparison")
            for row in bucket_rows:
                lines.append(
                    f"- {row['bucket']}: runs {row['runs']}, "
                    f"clean {self._pct(row['clean_run_rate'])}, "
                    f"correction {self._pct(row['correction_rate'])}, "
                    f"error {self._pct(row['error_rate'])}, "
                    f"success {self._pct(row['success_rate'])}"
                )

        if top_items:
            lines.append("")
            lines.append("## Linked Contradictions")
            for item in top_items[:5]:
                lines.append(
                    f"- {item['memory_id']}: {item['count']} hit(s), "
                    f"category {item['signal_category']}, last reason {item['latest_reason']}"
                )

        return "\n".join(lines)

    def resolve_trace_id(self, trace_id: Optional[str]) -> Optional[str]:
        return trace_id or self.get_active_trace_id()

    def get_active_trace_id(self) -> Optional[str]:
        return self._read_json(self.state_path, DEFAULT_METRICS_STATE).get("active_trace_id")

    def get_assessments(self, trace_id: Optional[str] = None) -> List[Dict[str, Any]]:
        records = list(self._iter_jsonl(self.assessments_path))
        if trace_id:
            return [record for record in records if record.get("trace_id") == trace_id]
        return records

    def _ensure_storage(self):
        self.metrics_path.mkdir(parents=True, exist_ok=True)
        self.reports_path.mkdir(parents=True, exist_ok=True)
        for file_path in (self.manifests_path, self.outcomes_path, self.assessments_path):
            if not file_path.exists():
                file_path.write_text("", encoding="utf-8")
        if not self.state_path.exists():
            self._save_json(self.state_path, DEFAULT_METRICS_STATE)

    def _set_active_trace_id(self, trace_id: Optional[str]):
        state = {
            "active_trace_id": trace_id,
            "updated_at": datetime.now().isoformat(),
        }
        self._save_json(self.state_path, state)

    def _generate_trace_id(self) -> str:
        return f"run-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"

    def _collect_exposed_ids(self, brief: Dict[str, Any]) -> List[str]:
        ids = []
        for key in ("strategies", "preferences", "rules"):
            for item in brief.get(key, []):
                item_id = item.get("id")
                if item_id and item_id not in ids:
                    ids.append(item_id)
        return ids

    def _decision_brief_non_empty(self, decision_brief: Dict[str, Any]) -> bool:
        for key in (
            "priority_preferences",
            "relevant_strategies",
            "risk_alerts",
            "current_focus",
        ):
            if decision_brief.get(key):
                return True
        return False

    def _build_bucket(self, context: Dict[str, Any]) -> str:
        context = context or {}
        parts = [
            str(context.get("task") or "unknown"),
            str(context.get("workspace") or "unknown"),
            str(context.get("surface") or "unknown"),
        ]
        return "|".join(parts)

    def _build_exposed_memories(self, brief: Dict[str, Any]) -> List[Dict[str, Any]]:
        exposed = []
        store_defs = [
            ("strategy", "strategies", ("condition", "action")),
            ("preference", "preferences", ("category", "preference", "evidence")),
            ("rule", "rules", ("trigger", "prevention", "root_cause")),
        ]
        for memory_type, key, text_fields in store_defs:
            for item in brief.get(key, []):
                category = self._classify_memory_category(memory_type, item, text_fields)
                text = " ".join(
                    str(item.get(field, "")).strip()
                    for field in text_fields
                    if str(item.get(field, "")).strip()
                )
                exposed.append(
                    {
                        "id": item.get("id"),
                        "type": memory_type,
                        "category": category,
                        "facets": self._extract_facets(text, category),
                        "text": text,
                    }
                )
        return exposed

    def _latest_outcome(self, trace_id: str) -> Dict[str, Any]:
        latest = self._latest_records_by_trace(self.outcomes_path).get(trace_id)
        if latest:
            return latest
        return {
            "trace_id": trace_id,
            "closed_at": None,
            "outcome_class": OUTCOME_CLASS_OPEN,
            "task_outcome": None,
            "has_correction": False,
            "has_error": False,
            "task_complete_seen": False,
            "feedback_events": [],
            "error_events": [],
        }

    def _latest_manifest(self, trace_id: str) -> Optional[Dict[str, Any]]:
        return self._latest_records_by_trace(self.manifests_path).get(trace_id)

    def _assess_event_against_exposed_memory(
        self,
        trace_id: str,
        event: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        manifest = self._latest_manifest(trace_id)
        if not manifest:
            return []

        signal = self._extract_signal(event)
        if not manifest.get("exposed_memories"):
            return []

        assessments = []
        for memory in manifest["exposed_memories"]:
            assessment = self._build_assessment(trace_id, memory, signal, event)
            if assessment:
                assessments.append(assessment)
                self._append_jsonl(self.assessments_path, assessment)
        return assessments

    def _build_assessment(
        self,
        trace_id: str,
        memory: Dict[str, Any],
        signal: Dict[str, Any],
        event: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        category = signal.get("category", "unknown")
        signal_facets = set(signal.get("facets", []))
        memory_category = memory.get("category", "unknown")
        memory_facets = set(memory.get("facets", []))

        if category == "unknown" or not signal_facets:
            return self._assessment_record(
                trace_id=trace_id,
                memory_id=memory.get("id"),
                status="insufficient_evidence",
                reason="insufficient_signal",
                confidence=0.2,
                evidence=sorted(signal_facets),
                signal_category=category,
                source_event=event,
            )

        score = 0.0
        reasons = []
        if memory_category == category:
            score += 0.45
            reasons.append("same_category")

        overlap = sorted(memory_facets.intersection(signal_facets))
        if overlap:
            score += min(0.3, 0.15 * len(overlap))
            reasons.append("matching_facets")

        contradiction_bonus = self._contradiction_bonus(category, memory_facets, signal_facets)
        if contradiction_bonus > 0:
            score += contradiction_bonus
            reasons.append("contradiction_pattern")

        if score >= 0.75:
            reason = (
                "same_category_and_contradiction_pattern"
                if "contradiction_pattern" in reasons
                else "same_category_and_matching_facets"
            )
            return self._assessment_record(
                trace_id=trace_id,
                memory_id=memory.get("id"),
                status="likely_contradicted",
                reason=reason,
                confidence=min(0.95, round(score, 2)),
                evidence=sorted(signal_facets.union(set(overlap))),
                signal_category=category,
                source_event=event,
            )

        return self._assessment_record(
            trace_id=trace_id,
            memory_id=memory.get("id"),
            status="unresolved",
            reason="no_sufficient_link_evidence",
            confidence=max(0.25, round(score, 2)),
            evidence=sorted(signal_facets.union(set(overlap))),
            signal_category=category,
            source_event=event,
        )

    def _assessment_record(
        self,
        trace_id: str,
        memory_id: Optional[str],
        status: str,
        reason: str,
        confidence: float,
        evidence: List[str],
        signal_category: str,
        source_event: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        if not memory_id:
            return None
        return {
            "trace_id": trace_id,
            "memory_id": memory_id,
            "status": status,
            "reason": reason,
            "confidence": round(confidence, 2),
            "signal_category": signal_category,
            "evidence": evidence,
            "assessed_by": "rules_engine.v1",
            "source_event": {
                "type": source_event.get("type"),
                "timestamp": source_event.get("timestamp"),
            },
            "assessed_at": datetime.now().isoformat(),
        }

    def _extract_signal(self, event: Dict[str, Any]) -> Dict[str, Any]:
        explicit_category = self._normalize_category(event.get("category"))
        texts = [
            str(event.get("feedback", "")).strip(),
            str(event.get("action", "")).strip(),
            str(event.get("outcome", "")).strip(),
        ]
        combined = " ".join(part for part in texts if part)

        if explicit_category != "unknown":
            facets = self._extract_facets(combined, explicit_category)
            if facets:
                return {"category": explicit_category, "facets": facets}

        scores = {}
        facets_by_category = {}
        for category in PHASE2_CATEGORY_RULES:
            facets = self._extract_facets(combined, category)
            if facets:
                facets_by_category[category] = facets
                scores[category] = len(facets)

        if not scores:
            return {"category": "unknown", "facets": []}

        best_category = max(scores.items(), key=lambda item: item[1])[0]
        return {
            "category": best_category,
            "facets": facets_by_category.get(best_category, []),
        }

    def _classify_memory_category(
        self,
        memory_type: str,
        item: Dict[str, Any],
        text_fields: Iterable[str],
    ) -> str:
        explicit_category = self._normalize_category(item.get("category"))
        if explicit_category != "unknown":
            return explicit_category

        combined = " ".join(
            str(item.get(field, "")).strip()
            for field in text_fields
            if str(item.get(field, "")).strip()
        )

        if memory_type == "preference":
            if self._extract_facets(combined, "communication_style"):
                return "communication_style"
            if self._extract_facets(combined, "output_contract"):
                return "output_contract"

        if self._extract_facets(combined, "workflow.evidence_first"):
            return "workflow.evidence_first"
        if self._extract_facets(combined, "output_contract"):
            return "output_contract"
        if self._extract_facets(combined, "communication_style"):
            return "communication_style"
        return "unknown"

    def _extract_facets(self, text: str, category: str) -> List[str]:
        normalized = self._normalize_text(text)
        if not normalized or category not in PHASE2_CATEGORY_RULES:
            return []

        facets = []
        for facet, phrases in PHASE2_CATEGORY_RULES[category].items():
            if any(self._normalize_text(phrase) in normalized for phrase in phrases):
                facets.append(facet)
        return facets

    def _normalize_category(self, value: Any) -> str:
        normalized = self._normalize_text(value).replace(" ", "_")
        return PHASE2_CATEGORY_ALIASES.get(normalized, "unknown")

    def _contradiction_bonus(
        self,
        category: str,
        memory_facets: set,
        signal_facets: set,
    ) -> float:
        mapping = {
            "communication_style": COMMUNICATION_STYLE_CONTRADICTIONS,
            "output_contract": OUTPUT_CONTRACT_CONTRADICTIONS,
            "workflow.evidence_first": WORKFLOW_CONTRADICTIONS,
        }.get(category, {})

        for memory_facet in memory_facets:
            contradictory = mapping.get(memory_facet, set())
            if contradictory.intersection(signal_facets):
                return 0.35
        return 0.0

    def _latest_records_by_trace(self, file_path: Path) -> Dict[str, Dict[str, Any]]:
        records = {}
        for record in self._iter_jsonl(file_path):
            trace_id = record.get("trace_id")
            if trace_id:
                records[trace_id] = record
        return records

    def _iter_jsonl(self, file_path: Path) -> Iterable[Dict[str, Any]]:
        if not file_path.exists():
            return []

        records = []
        with open(file_path, encoding="utf-8") as file_handle:
            for line in file_handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(record, dict):
                    records.append(record)
        return records

    def _append_jsonl(self, file_path: Path, data: Dict[str, Any]):
        with open(file_path, "a", encoding="utf-8") as file_handle:
            file_handle.write(json.dumps(data, ensure_ascii=False) + "\n")

    def _append_unique(self, values: List[str], value: Optional[str]) -> List[str]:
        items = list(values or [])
        if value and value not in items:
            items.append(value)
        return items

    def _event_ref(self, event: Optional[Dict[str, Any]]) -> Optional[str]:
        if not event:
            return None
        timestamp = event.get("timestamp")
        event_type = event.get("type")
        if timestamp and event_type:
            return f"{event_type}:{timestamp}"
        return event_type or timestamp

    def _compute_outcome_class(
        self,
        has_correction: bool,
        has_error: bool,
        task_complete_seen: bool,
        task_outcome: Optional[str],
    ) -> str:
        if has_correction and has_error:
            return OUTCOME_CLASS_CORRECTED_AND_ERROR
        if has_correction:
            return OUTCOME_CLASS_CORRECTED
        if has_error or self._is_failure_outcome(task_outcome):
            return OUTCOME_CLASS_ERROR
        if task_complete_seen:
            return OUTCOME_CLASS_CLEAN
        return OUTCOME_CLASS_OPEN

    def _is_success_outcome(self, task_outcome: Optional[str]) -> bool:
        normalized = self._normalize_text(task_outcome)
        return normalized in SUCCESS_OUTCOMES

    def _is_failure_outcome(self, task_outcome: Optional[str]) -> bool:
        normalized = self._normalize_text(task_outcome)
        return normalized in FAILURE_OUTCOMES

    def _is_reportable_outcome(self, outcome: Dict[str, Any]) -> bool:
        if outcome.get("task_complete_seen"):
            return True
        return bool(outcome.get("has_correction") or outcome.get("has_error"))

    def _empty_type_stats(self) -> Dict[str, int]:
        return {
            "runs": 0,
            "clean_runs": 0,
            "corrected_runs": 0,
            "error_runs": 0,
            "successful_runs": 0,
        }

    def _report_assessments(
        self,
        trace_ids: List[str],
        cutoff: datetime,
    ) -> List[Dict[str, Any]]:
        allowed = set(trace_ids)
        assessments = []
        for record in self._iter_jsonl(self.assessments_path):
            if record.get("trace_id") not in allowed:
                continue
            assessed_at = self._parse_timestamp(record.get("assessed_at"))
            if assessed_at and assessed_at < cutoff:
                continue
            assessments.append(record)
        return assessments

    def _build_summary(
        self,
        by_memory_type: Dict[str, Dict[str, Any]],
        bucket_summary: List[Dict[str, Any]],
        assessments: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        exposed_candidates = []
        for memory_type in ("strategy", "preference", "rule"):
            stats = by_memory_type.get(memory_type, {})
            runs = int(stats.get("exposed_runs", 0) or 0)
            if runs <= 0:
                continue
            exposed_candidates.append(
                {
                    "type": memory_type,
                    "runs": runs,
                    "clean_run_rate": float(stats.get("clean_run_rate", 0.0) or 0.0),
                    "correction_rate": float(stats.get("correction_rate", 0.0) or 0.0),
                }
            )

        most_exposed = None
        healthiest = None
        if exposed_candidates:
            most_exposed = max(exposed_candidates, key=lambda item: (item["runs"], item["type"]))
            healthiest = max(
                exposed_candidates,
                key=lambda item: (
                    item["clean_run_rate"],
                    -item["correction_rate"],
                    item["runs"],
                    item["type"],
                ),
            )

        contradictions = {}
        for record in assessments:
            if record.get("status") != "likely_contradicted":
                continue
            memory_id = record.get("memory_id")
            if not memory_id:
                continue
            entry = contradictions.setdefault(
                memory_id,
                {
                    "memory_id": memory_id,
                    "count": 0,
                    "signal_category": record.get("signal_category", "unknown"),
                    "latest_reason": record.get("reason", "unknown"),
                },
            )
            entry["count"] += 1
            entry["signal_category"] = record.get("signal_category", entry["signal_category"])
            entry["latest_reason"] = record.get("reason", entry["latest_reason"])

        top_contradicted_items = sorted(
            contradictions.values(),
            key=lambda item: (-item["count"], item["memory_id"]),
        )[:5]

        healthiest_bucket = None
        if bucket_summary:
            healthiest_bucket = max(
                bucket_summary,
                key=lambda item: (
                    item["clean_run_rate"],
                    -item["correction_rate"],
                    item["runs"],
                    item["bucket"],
                ),
            )

        return {
            "runs_with_memory": sum(item["runs"] for item in exposed_candidates),
            "runs_without_memory": int(by_memory_type.get("none", {}).get("runs", 0) or 0),
            "most_exposed_type": most_exposed,
            "healthiest_type": healthiest,
            "healthiest_bucket": healthiest_bucket,
            "linked_contradictions": sum(item["count"] for item in contradictions.values()),
            "top_contradicted_items": top_contradicted_items,
            "headline_verdict": self._build_headline_verdict(
                exposed_candidates,
                healthiest_bucket,
                top_contradicted_items,
            ),
            "top_positive_signal": self._build_top_positive_signal(
                healthiest,
                healthiest_bucket,
            ),
            "top_watchouts": self._build_top_watchouts(
                exposed_candidates,
                bucket_summary,
                top_contradicted_items,
            ),
        }

    def _aggregate_bucket_summary(
        self,
        runs: List[Any],
        top_buckets: int,
    ) -> List[Dict[str, Any]]:
        stats_by_bucket: Dict[str, Dict[str, int]] = {}
        for manifest, outcome in runs:
            bucket = manifest.get("bucket") or "unknown|unknown|unknown"
            stats = stats_by_bucket.setdefault(bucket, self._empty_type_stats())
            stats["runs"] += 1
            if not outcome.get("has_correction") and not outcome.get("has_error"):
                stats["clean_runs"] += 1
            if outcome.get("has_correction"):
                stats["corrected_runs"] += 1
            if outcome.get("has_error") or self._is_failure_outcome(outcome.get("task_outcome")):
                stats["error_runs"] += 1
            if self._is_success_outcome(outcome.get("task_outcome")):
                stats["successful_runs"] += 1

        rows = []
        for bucket, stats in stats_by_bucket.items():
            runs_count = stats["runs"]
            rows.append(
                {
                    "bucket": bucket,
                    "runs": runs_count,
                    "clean_run_rate": self._rate(stats["clean_runs"], runs_count),
                    "correction_rate": self._rate(stats["corrected_runs"], runs_count),
                    "error_rate": self._rate(stats["error_runs"], runs_count),
                    "success_rate": self._rate(stats["successful_runs"], runs_count),
                }
            )

        rows.sort(
            key=lambda item: (
                -item["runs"],
                -item["clean_run_rate"],
                item["correction_rate"],
                item["bucket"],
            )
        )
        return rows[: max(1, int(top_buckets))]

    def _build_headline_verdict(
        self,
        exposed_candidates: List[Dict[str, Any]],
        healthiest_bucket: Optional[Dict[str, Any]],
        top_contradicted_items: List[Dict[str, Any]],
    ) -> str:
        if not exposed_candidates:
            return "Signal is still too weak to judge memory effectiveness."

        best_type = max(
            exposed_candidates,
            key=lambda item: (
                item["clean_run_rate"],
                -item["correction_rate"],
                item["runs"],
            ),
        )
        if best_type["clean_run_rate"] >= 0.7 and best_type["correction_rate"] <= 0.2:
            return (
                f"Memory looks helpful in this window, led by {best_type['type']} "
                f"exposure."
            )

        if healthiest_bucket and healthiest_bucket["correction_rate"] >= 0.4:
            return (
                f"Corrections remain high in {healthiest_bucket['bucket']}; "
                "memory guidance is landing unevenly."
            )

        if top_contradicted_items:
            return "Memory is producing signal, but some exposed items are being contradicted."

        return "Signal is mixed; keep collecting runs before expanding the system."

    def _build_top_positive_signal(
        self,
        healthiest_type: Optional[Dict[str, Any]],
        healthiest_bucket: Optional[Dict[str, Any]],
    ) -> Optional[str]:
        if healthiest_type and healthiest_bucket:
            return (
                f"{healthiest_type['type']} is the healthiest exposed type, and "
                f"{healthiest_bucket['bucket']} is the healthiest bucket."
            )
        if healthiest_type:
            return f"{healthiest_type['type']} is the healthiest exposed memory type."
        if healthiest_bucket:
            return f"{healthiest_bucket['bucket']} is the healthiest bucket in this window."
        return None

    def _build_top_watchouts(
        self,
        exposed_candidates: List[Dict[str, Any]],
        bucket_summary: List[Dict[str, Any]],
        top_contradicted_items: List[Dict[str, Any]],
    ) -> List[str]:
        watchouts = []

        if exposed_candidates:
            riskiest_type = max(
                exposed_candidates,
                key=lambda item: (
                    item["correction_rate"],
                    -item["clean_run_rate"],
                    item["runs"],
                ),
            )
            if riskiest_type["correction_rate"] >= 0.3:
                watchouts.append(
                    f"{riskiest_type['type']} shows elevated correction rate "
                    f"({self._pct(riskiest_type['correction_rate'])})."
                )

        if bucket_summary:
            riskiest_bucket = max(
                bucket_summary,
                key=lambda item: (
                    item["correction_rate"],
                    item["error_rate"],
                    -item["clean_run_rate"],
                    item["runs"],
                ),
            )
            if riskiest_bucket["correction_rate"] >= 0.3 or riskiest_bucket["error_rate"] >= 0.3:
                watchouts.append(
                    f"{riskiest_bucket['bucket']} needs attention "
                    f"(correction {self._pct(riskiest_bucket['correction_rate'])}, "
                    f"error {self._pct(riskiest_bucket['error_rate'])})."
                )

        if top_contradicted_items:
            top_item = top_contradicted_items[0]
            watchouts.append(
                f"{top_item['memory_id']} is the most repeatedly contradicted item."
            )

        return watchouts[:3]

    def _rate(self, numerator: int, denominator: int) -> float:
        if denominator <= 0:
            return 0.0
        return round(numerator / denominator, 4)

    def _pct(self, value: float) -> str:
        return f"{round(float(value or 0.0) * 100, 1)}%"

    def _write_report_snapshot(self, report: Dict[str, Any]):
        latest_path = self.reports_path / "latest.json"
        dated_path = self.reports_path / f"{datetime.now().strftime('%Y-%m-%d')}.json"
        self._save_json(latest_path, report)
        self._save_json(dated_path, report)

    def _read_json(self, file_path: Path, default: Any) -> Any:
        return self.memory._read_json(file_path, deepcopy(default))

    def _save_json(self, file_path: Path, data: Any):
        self.memory._save_json(file_path, data)

    def _normalize_text(self, value: Any) -> str:
        return self.memory._normalize_text(value)

    def _parse_timestamp(self, value: Any) -> Optional[datetime]:
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value))
        except ValueError:
            return None
