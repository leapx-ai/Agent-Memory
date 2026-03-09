#!/usr/bin/env python3
"""
Decision-layer helpers for projecting governed memory into OpenClaw-facing outputs.
"""

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from memory import MemorySystem


STORE_KEYS = {
    "strategy": "strategies",
    "preference": "preferences",
    "rule": "rules",
}


class DecisionLayer:
    def __init__(self, memory_system: "MemorySystem"):
        self.memory = memory_system

    def build_openclaw_brief(
        self,
        context: Dict[str, Any],
        limit_per_type: int = 3,
    ) -> Dict[str, Any]:
        memory_items = self._collect_memory_items(context, limit_per_type=limit_per_type)
        decision_brief = self.build_decision_brief(context, limit_per_type=limit_per_type)
        projection = self.select_projection(context, limit_per_type=limit_per_type)

        brief = dict(memory_items)
        brief["context"] = context
        brief["summary"] = decision_brief["summary"]
        brief["decision_brief"] = decision_brief
        brief["projection"] = projection
        return brief

    def build_decision_brief(
        self,
        context: Dict[str, Any],
        limit_per_type: int = 3,
    ) -> Dict[str, Any]:
        memory_items = self._collect_memory_items(context, limit_per_type=limit_per_type)

        priority_preferences = self._dedupe_lines(
            [
                self._format_preference_line(item)
                for item in memory_items["preferences"][:limit_per_type]
            ]
        )
        relevant_strategies = self._dedupe_lines(
            [
                self._format_strategy_line(item)
                for item in memory_items["strategies"][:limit_per_type]
            ]
        )
        risk_alerts = self._dedupe_lines(
            [
                self._format_rule_line(item)
                for item in memory_items["rules"][:limit_per_type]
            ]
        )
        current_focus = self._current_focus_lines(context)

        summary = []
        summary.extend(f"Preference: {line}" for line in priority_preferences)
        summary.extend(f"Strategy: {line}" for line in relevant_strategies)
        summary.extend(f"Risk: {line}" for line in risk_alerts)
        summary.extend(f"Focus: {line}" for line in current_focus)

        return {
            "context": context,
            "priority_preferences": priority_preferences,
            "relevant_strategies": relevant_strategies,
            "risk_alerts": risk_alerts,
            "current_focus": current_focus,
            "summary": summary,
            "source_items": memory_items,
        }

    def render_openclaw_memory(
        self,
        context: Dict[str, Any],
        limit_per_type: int = 3,
    ) -> str:
        brief = self.build_openclaw_brief(context, limit_per_type=limit_per_type)
        decision_brief = brief["decision_brief"]
        if not any(
            brief[key] for key in ("strategies", "preferences", "rules")
        ) and not any(
            decision_brief[key]
            for key in (
                "priority_preferences",
                "relevant_strategies",
                "risk_alerts",
                "current_focus",
            )
        ):
            return ""

        lines = ["## Decision Brief"]
        self._append_lines(
            lines,
            "### Priority Preferences",
            decision_brief["priority_preferences"],
        )
        self._append_lines(
            lines,
            "### Relevant Strategies",
            decision_brief["relevant_strategies"],
        )
        self._append_lines(lines, "### Risk Alerts", decision_brief["risk_alerts"])
        self._append_lines(lines, "### Current Focus", decision_brief["current_focus"])

        if any(brief[key] for key in ("strategies", "preferences", "rules")):
            lines.append("")
            lines.append("## Relevant Memory")
            self._append_lines(
                lines,
                "### Strategies",
                [self._format_strategy_line(item) for item in brief["strategies"]],
            )
            self._append_lines(
                lines,
                "### User Preferences",
                [self._format_preference_line(item) for item in brief["preferences"]],
            )
            self._append_lines(
                lines,
                "### Error Rules",
                [self._format_rule_line(item) for item in brief["rules"]],
            )

        return "\n".join(lines)

    def select_projection(
        self,
        context: Dict[str, Any],
        limit_per_type: int = 3,
    ) -> Dict[str, Any]:
        context = context or {}
        context_tags = set(self.memory._normalize_context_tags(context))
        projection_limit = max(
            int(limit_per_type),
            int(self._projection_config().get("max_brief_items_per_type", 3)),
        )
        memory_items = self._collect_memory_items(context, limit_per_type=projection_limit)

        targets = {
            "brief": {"strategies": [], "preferences": [], "rules": []},
            "durable": {"strategies": [], "preferences": [], "rules": []},
            "recent": {"strategies": [], "preferences": [], "rules": []},
        }
        candidates = []

        for memory_type, key in STORE_KEYS.items():
            for item in memory_items[key]:
                candidate = self._build_projection_candidate(
                    memory_type,
                    item,
                    context_tags,
                )
                candidates.append(candidate)

                if candidate["include_in_brief"]:
                    targets["brief"][key].append(dict(item))
                if candidate["target"] in ("durable", "recent"):
                    targets[candidate["target"]][key].append(dict(item))

        for bucket in targets.values():
            for key, items in bucket.items():
                items.sort(
                    key=lambda item: (
                        float(item.get("score", 0) or 0),
                        float(item.get("weight", 0) or 0),
                        item.get("created", ""),
                        item.get("id", ""),
                    ),
                    reverse=True,
                )
                del items[projection_limit:]

        candidates.sort(
            key=lambda item: (
                item["include_in_brief"],
                item["target"] == "durable",
                item["score"],
                item["weight"],
                item["created"],
            ),
            reverse=True,
        )

        return {
            "context": context,
            "candidates": candidates,
            "targets": targets,
        }

    def publish_openclaw_memory(
        self,
        target_root: Optional[Path] = None,
        context: Optional[Dict[str, Any]] = None,
        limit_per_type: int = 3,
        mode: str = "incremental",
    ) -> Dict[str, Any]:
        if mode not in {"incremental", "full"}:
            raise ValueError("publish mode must be either 'incremental' or 'full'.")

        context = context or {}
        root = self._resolve_publish_root(target_root)
        root.mkdir(parents=True, exist_ok=True)
        daily_dir = root / "memory"
        daily_dir.mkdir(parents=True, exist_ok=True)

        projection = self.select_projection(context, limit_per_type=limit_per_type)
        decision_brief = self.build_decision_brief(context, limit_per_type=limit_per_type)

        memory_file = root / "MEMORY.md"
        daily_file = daily_dir / f"{datetime.now().strftime('%Y-%m-%d')}.md"

        durable_text = self._render_host_memory_projection(
            "durable",
            projection["targets"]["durable"],
            context,
            decision_brief,
        )
        recent_text = self._render_host_memory_projection(
            "recent",
            projection["targets"]["recent"],
            context,
            decision_brief,
        )

        memory_file.write_text(durable_text, encoding="utf-8")
        daily_file.write_text(recent_text, encoding="utf-8")

        return {
            "mode": mode,
            "target_root": str(root),
            "memory_file": str(memory_file),
            "daily_file": str(daily_file),
            "published": {
                "durable_ids": self._collect_ids(projection["targets"]["durable"]),
                "recent_ids": self._collect_ids(projection["targets"]["recent"]),
            },
            "decision_brief": decision_brief,
        }

    def _collect_memory_items(
        self,
        context: Dict[str, Any],
        limit_per_type: int,
    ) -> Dict[str, List[Dict[str, Any]]]:
        context = context or {}
        context_tags = self.memory._normalize_context_tags(context)
        has_context = bool(context_tags)
        limit = max(1, int(limit_per_type))

        if has_context:
            memory_items = self.memory.retrieve_memory(context, limit_per_type=limit)
        else:
            memory_items = {
                "strategies": self.memory.get_all_strategies()[:limit],
                "preferences": self.memory.get_all_preferences()[:limit],
                "rules": self.memory.get_all_error_rules()[:limit],
            }

        if not memory_items["preferences"]:
            memory_items["preferences"] = self.memory.get_all_preferences()[: min(limit, 2)]

        return memory_items

    def _build_projection_candidate(
        self,
        memory_type: str,
        item: Dict[str, Any],
        context_tags: set,
    ) -> Dict[str, Any]:
        score = float(item.get("score", 0) or 0)
        weight = float(item.get("weight", 0) or 0)
        item_tags = set(self.memory._normalize_context_tags(item.get("context", [])))
        has_context_match = bool(item_tags.intersection(context_tags))

        if not context_tags:
            score = max(score, weight)

        target = self._determine_target(memory_type, score, weight, has_context_match)
        include_in_brief = bool(
            score > 0
            or (memory_type == "preference" and weight >= self._durable_threshold(memory_type))
        )
        reasons = self._projection_reasons(memory_type, score, weight, has_context_match, target)

        return {
            "id": item.get("id"),
            "type": memory_type,
            "score": round(score, 4),
            "weight": round(weight, 4),
            "target": target,
            "include_in_brief": include_in_brief,
            "created": item.get("created", ""),
            "reasons": reasons,
        }

    def _determine_target(
        self,
        memory_type: str,
        score: float,
        weight: float,
        has_context_match: bool,
    ) -> str:
        durable_threshold = self._durable_threshold(memory_type)
        recent_threshold = float(self._projection_config().get("recent_threshold", 0.45))

        if memory_type == "preference" and weight >= durable_threshold:
            return "durable"
        if weight >= durable_threshold and (score >= recent_threshold or not has_context_match):
            return "durable"
        if score >= recent_threshold or has_context_match:
            return "recent"
        return "skip"

    def _durable_threshold(self, memory_type: str) -> float:
        thresholds = self._projection_config().get("durable_thresholds", {})
        return float(thresholds.get(memory_type, 0.8))

    def _projection_reasons(
        self,
        memory_type: str,
        score: float,
        weight: float,
        has_context_match: bool,
        target: str,
    ) -> List[str]:
        reasons = []
        if has_context_match:
            reasons.append("context_match")
        if score >= 0.9:
            reasons.append("high_relevance")
        elif score >= 0.45:
            reasons.append("relevant")
        if weight >= self._durable_threshold(memory_type):
            reasons.append("high_weight")
        if target == "durable":
            reasons.append("durable_candidate")
        elif target == "recent":
            reasons.append("recent_candidate")
        if not reasons:
            reasons.append("low_signal")
        return reasons

    def _resolve_publish_root(self, target_root: Optional[Path]) -> Path:
        if target_root is not None:
            root = Path(target_root).expanduser()
        else:
            root = Path(self._projection_config().get("publish_root", "openclaw-memory"))
            if not root.is_absolute():
                root = self.memory.base_path / root
        return root

    def _render_host_memory_projection(
        self,
        bucket: str,
        items: Dict[str, List[Dict[str, Any]]],
        context: Dict[str, Any],
        decision_brief: Dict[str, Any],
    ) -> str:
        lines = []
        if bucket == "durable":
            lines.extend(
                [
                    "# OpenClaw Memory Projection",
                    "",
                    "Generated by Agent-Memory. This file contains stable high-value guidance.",
                    "",
                ]
            )
        else:
            lines.extend(
                [
                    f"# Daily Memory Projection - {datetime.now().strftime('%Y-%m-%d')}",
                    "",
                    "Generated by Agent-Memory. This file contains recent and stage-specific guidance.",
                    "",
                ]
            )
            self._append_lines(lines, "## Current Focus", decision_brief["current_focus"])

        self._append_lines(
            lines,
            "## User Preferences",
            [self._format_preference_line(item) for item in items["preferences"]],
        )
        self._append_lines(
            lines,
            "## Strategies",
            [self._format_strategy_line(item) for item in items["strategies"]],
        )
        self._append_lines(
            lines,
            "## Error Rules",
            [self._format_rule_line(item) for item in items["rules"]],
        )

        if bucket == "recent":
            self._append_lines(
                lines,
                "## Task Decision Brief",
                decision_brief["summary"],
            )

        if context:
            lines.append("")
            lines.append("## Context")
            for key, value in context.items():
                lines.append(f"- {key}: {value}")

        return "\n".join(self._trim_trailing_blank_lines(lines)) + "\n"

    def _append_lines(self, lines: List[str], heading: str, values: List[str]):
        values = [value for value in values if value]
        if not values:
            return
        if lines and lines[-1] != "":
            lines.append("")
        lines.append(heading)
        for value in values:
            lines.append(f"- {value}")

    def _collect_ids(self, items: Dict[str, List[Dict[str, Any]]]) -> List[str]:
        ids = []
        for key in ("strategies", "preferences", "rules"):
            ids.extend(item.get("id") for item in items[key] if item.get("id"))
        return ids

    def _current_focus_lines(self, context: Dict[str, Any]) -> List[str]:
        focus = []
        for key in ("task", "goal", "workspace", "surface", "channel"):
            value = context.get(key)
            if value:
                focus.append(f"{key}: {value}")
        if not focus and context:
            focus.append(
                "context: " + ", ".join(f"{key}={value}" for key, value in context.items())
            )
        return self._dedupe_lines(focus)

    def _format_strategy_line(self, item: Dict[str, Any]) -> str:
        return f"When {item.get('condition')}: {item.get('action')}"

    def _format_preference_line(self, item: Dict[str, Any]) -> str:
        category = item.get("category", "general")
        return f"{category}: {item.get('preference')}"

    def _format_rule_line(self, item: Dict[str, Any]) -> str:
        return f"Avoid {item.get('trigger')}; prevention: {item.get('prevention')}"

    def _dedupe_lines(self, values: List[str]) -> List[str]:
        deduped = []
        seen = set()
        for value in values:
            normalized = self.memory._normalize_text(value)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            deduped.append(value)
        return deduped

    def _trim_trailing_blank_lines(self, lines: List[str]) -> List[str]:
        trimmed = list(lines)
        while trimmed and trimmed[-1] == "":
            trimmed.pop()
        return trimmed

    def _projection_config(self) -> Dict[str, Any]:
        return self.memory.governance.get("projection", {})
