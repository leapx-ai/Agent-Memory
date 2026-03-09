#!/usr/bin/env python3
"""
Self-Evolving Memory System - 接口层
提供策略检索、事件记录、学习等功能
"""

import json
import os
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import yaml

BASE_PATH = Path.home() / ".openclaw" / "memory-system"

DEFAULT_GOVERNANCE = {
    "events": {
        "max_size_mb": 10,
        "max_count": 1000,
        "cleanup_trigger": 0.8,
        "retention_days": 7,
        "meaningful_only": True,
        "allowed_types": [
            "user_feedback",
            "error",
            "new_pattern",
            "task_complete",
            "strategy_success",
            "strategy_failure",
        ],
    },
    "strategies": {
        "max_count": 100,
        "max_size_kb": 50,
        "min_weight": 0.3,
        "merge_threshold": 0.8,
        "decay": {
            "enabled": True,
            "daily_rate": 0.05,
        },
        "update": {
            "success_boost": 0.1,
            "failure_penalty": 0.2,
        },
    },
    "cleanup": {
        "schedule": "daily",
        "archive_path": "archive/",
    },
}

DEFAULT_INDEX = {
    "indexes": {
        "by_condition": {},
        "by_context": {},
    }
}

DEFAULT_STATUS = {
    "usage": {
        "events": {
            "count": 0,
            "size_kb": 0,
            "usage_percent": 0.0,
        },
        "strategies": {
            "count": 0,
            "size_kb": 0,
            "usage_percent": 0.0,
        },
    },
    "last_check": None,
}

DEFAULT_MEMORY_FILES = {
    "task-strategies.yaml": {"strategies": []},
    "user-preferences.yaml": {"preferences": []},
    "error-rules.yaml": {"rules": []},
}

MEMORY_STORE_DEFS = {
    "strategy": {
        "file": "task-strategies.yaml",
        "key": "strategies",
        "label": "strategies",
        "text_fields": ("condition", "action"),
    },
    "preference": {
        "file": "user-preferences.yaml",
        "key": "preferences",
        "label": "preferences",
        "text_fields": ("category", "preference", "evidence"),
    },
    "rule": {
        "file": "error-rules.yaml",
        "key": "rules",
        "label": "rules",
        "text_fields": ("trigger", "prevention", "root_cause"),
    },
}


class MemorySystem:
    """记忆管理系统"""

    def __init__(self, base_path: Optional[Path] = None):
        env_base = os.getenv("AGENT_MEMORY_HOME")
        self.base_path = Path(base_path or env_base or BASE_PATH).expanduser()
        self.strategies_path = self.base_path / "strategies"
        self.events_path = self.base_path / "events"
        self.index_path = self.base_path / "index.json"
        self.status_path = self.base_path / "status.json"
        self.governance_path = self.base_path / "governance.yaml"
        self.archive_path = self.base_path / "archive"

        self._ensure_storage()
        self._load_governance()
        self._load_index()
        self._rebuild_index()
        self._update_status()

    def _ensure_storage(self):
        """确保目录与基础文件存在。"""
        self.base_path.mkdir(parents=True, exist_ok=True)
        self.strategies_path.mkdir(parents=True, exist_ok=True)
        self.events_path.mkdir(parents=True, exist_ok=True)
        self.archive_path.mkdir(parents=True, exist_ok=True)

        if not self.governance_path.exists():
            self._write_yaml(self.governance_path, DEFAULT_GOVERNANCE)

        if not self.index_path.exists():
            self._save_json(self.index_path, DEFAULT_INDEX)

        if not self.status_path.exists():
            self._save_json(self.status_path, DEFAULT_STATUS)

        for name, default_data in DEFAULT_MEMORY_FILES.items():
            file_path = self.strategies_path / name
            if not file_path.exists():
                self._write_yaml(file_path, default_data)

    def _load_governance(self):
        """加载治理配置并补齐默认值。"""
        governance = self._read_yaml(self.governance_path, deepcopy(DEFAULT_GOVERNANCE))
        if not isinstance(governance, dict):
            governance = deepcopy(DEFAULT_GOVERNANCE)
        self.governance = self._merge_dicts(deepcopy(DEFAULT_GOVERNANCE), governance)
        self._write_yaml(self.governance_path, self.governance)

        archive_path = self.governance.get("cleanup", {}).get("archive_path")
        if archive_path:
            resolved_archive = Path(archive_path).expanduser()
            if not resolved_archive.is_absolute():
                resolved_archive = self.base_path / resolved_archive
            self.archive_path = resolved_archive
            self.archive_path.mkdir(parents=True, exist_ok=True)

    def _load_index(self):
        """加载索引并规范化结构。"""
        raw_index = self._read_json(self.index_path, deepcopy(DEFAULT_INDEX))
        indexes = raw_index.get("indexes", {})

        by_condition = {}
        for condition, strategy_ids in indexes.get("by_condition", {}).items():
            normalized = self._normalize_index_ids(strategy_ids)
            if normalized:
                by_condition[condition] = normalized

        by_context = {}
        for tag, strategy_ids in indexes.get("by_context", {}).items():
            normalized = self._normalize_index_ids(strategy_ids)
            if normalized:
                by_context[tag] = normalized

        self.index = {"indexes": {"by_condition": by_condition, "by_context": by_context}}
        self._save_json(self.index_path, self.index)

    # ============================================
    # 核心接口
    # ============================================

    def retrieve_strategies(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        检索相关策略

        Args:
            context: {"task": "...", "context": "...", ...}

        Returns:
            相关策略列表，按匹配分数和权重排序
        """
        normalized_context = self._normalize_context_tags(context)
        context_text = self._context_text(context)
        matches = []

        for strategy in self.get_all_strategies():
            score = self._score_strategy(strategy, context_text, normalized_context)
            if score <= 0:
                continue

            matched = dict(strategy)
            matched["score"] = round(score, 4)
            matches.append(matched)

        matches.sort(
            key=lambda item: (
                item.get("score", 0),
                item.get("weight", 0),
                item.get("created", ""),
            ),
            reverse=True,
        )
        return matches

    def retrieve_preferences(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """检索相关用户偏好。"""
        return self._retrieve_store_items("preference", context)

    def retrieve_error_rules(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """检索相关错误规则。"""
        return self._retrieve_store_items("rule", context)

    def retrieve_memory(
        self,
        context: Dict[str, Any],
        limit_per_type: Optional[int] = None,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """统一检索 OpenClaw 可用的三类记忆。"""
        memory = {
            "strategies": self.retrieve_strategies(context),
            "preferences": self.retrieve_preferences(context),
            "rules": self.retrieve_error_rules(context),
        }
        if limit_per_type is None:
            return memory

        return {
            key: values[:limit_per_type]
            for key, values in memory.items()
        }

    def log_event(
        self,
        type: str,
        goal: str,
        context: Optional[Dict[str, Any]],
        action: str,
        outcome: str,
        feedback: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        记录事件

        Args:
            type: 事件类型
            goal: 任务目标
            context: 上下文
            action: 执行的动作
            outcome: 结果
            feedback: 用户反馈（可选）
        """
        allowed = self.governance.get("events", {}).get("allowed_types", [])
        if allowed and type not in allowed:
            return None

        if not self._check_capacity():
            self._run_cleanup()

        event = {
            "timestamp": datetime.now().isoformat(),
            "type": type,
            "goal": goal,
            "context": context or {},
            "action": action,
            "outcome": outcome,
        }
        if feedback:
            event["feedback"] = feedback

        today = datetime.now().strftime("%Y-%m-%d")
        event_file = self.events_path / f"{today}.jsonl"
        with open(event_file, "a", encoding="utf-8") as file_handle:
            file_handle.write(json.dumps(event, ensure_ascii=False) + "\n")

        self._update_status()
        return event

    def learn_immediately(self, event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        从事件中立即学习（生成策略）

        用于用户给出明确反馈时，立即生成策略。
        """
        event_type = event.get("type")
        if event_type not in {"user_feedback", "error", "strategy_failure"}:
            return None

        memory_type = self._resolve_memory_type(event)
        builder = {
            "strategy": self._build_strategy_from_event,
            "preference": self._build_preference_from_event,
            "rule": self._build_rule_from_event,
        }[memory_type]

        item = builder(event)
        if not item:
            return None

        self._save_memory_item(memory_type, item)
        return item

    def build_openclaw_brief(
        self,
        context: Dict[str, Any],
        limit_per_type: int = 3,
    ) -> Dict[str, Any]:
        """构建供 OpenClaw 在会话开始或任务前读取的记忆摘要。"""
        brief = self.retrieve_memory(context, limit_per_type=limit_per_type)

        if not brief["preferences"]:
            brief["preferences"] = self.get_all_preferences()[: min(limit_per_type, 2)]

        summary = []
        for strategy in brief["strategies"]:
            summary.append(f"Strategy: {strategy.get('condition')} -> {strategy.get('action')}")
        for preference in brief["preferences"]:
            category = preference.get("category", "general")
            summary.append(f"Preference ({category}): {preference.get('preference')}")
        for rule in brief["rules"]:
            summary.append(f"Avoid: {rule.get('trigger')} | Prevention: {rule.get('prevention')}")

        brief["summary"] = summary
        brief["context"] = context
        return brief

    def render_openclaw_memory(
        self,
        context: Dict[str, Any],
        limit_per_type: int = 3,
    ) -> str:
        """将记忆摘要渲染为适合 OpenClaw 提示词注入的 Markdown。"""
        brief = self.build_openclaw_brief(context, limit_per_type=limit_per_type)
        if not any(brief[key] for key in ("strategies", "preferences", "rules")):
            return ""

        lines = ["## Relevant Memory"]

        if brief["strategies"]:
            lines.append("### Strategies")
            for strategy in brief["strategies"]:
                lines.append(f"- When {strategy.get('condition')}: {strategy.get('action')}")

        if brief["preferences"]:
            lines.append("### User Preferences")
            for preference in brief["preferences"]:
                category = preference.get("category", "general")
                lines.append(f"- {category}: {preference.get('preference')}")

        if brief["rules"]:
            lines.append("### Error Rules")
            for rule in brief["rules"]:
                lines.append(
                    f"- Avoid {rule.get('trigger')}; prevention: {rule.get('prevention')}"
                )

        return "\n".join(lines)

    def get_all_strategies(self) -> List[Dict[str, Any]]:
        """获取所有 task strategies。"""
        return self._get_all_store_items("strategy")

    def get_all_preferences(self) -> List[Dict[str, Any]]:
        """获取所有用户偏好。"""
        return self._get_all_store_items("preference")

    def get_all_error_rules(self) -> List[Dict[str, Any]]:
        """获取所有错误规则。"""
        return self._get_all_store_items("rule")

    # ============================================
    # 内部方法
    # ============================================

    def _get_all_store_items(self, store_type: str) -> List[Dict[str, Any]]:
        """读取某一类长期记忆条目。"""
        store = MEMORY_STORE_DEFS[store_type]
        file_path = self.strategies_path / store["file"]
        data = self._read_yaml(file_path, {store["key"]: []})
        items = data.get(store["key"], [])
        if not isinstance(items, list):
            return []
        return sorted(items, key=lambda item: item.get("weight", 0), reverse=True)

    def _retrieve_store_items(
        self,
        store_type: str,
        context: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """按上下文检索某一类长期记忆。"""
        normalized_context = self._normalize_context_tags(context)
        context_text = self._context_text(context)
        store = MEMORY_STORE_DEFS[store_type]
        matches = []

        for item in self._get_all_store_items(store_type):
            score = self._score_memory_item(
                item,
                context_text,
                normalized_context,
                store["text_fields"],
            )
            if score <= 0:
                continue

            matched = dict(item)
            matched["score"] = round(score, 4)
            matches.append(matched)

        matches.sort(
            key=lambda item: (
                item.get("score", 0),
                item.get("weight", 0),
                item.get("created", ""),
            ),
            reverse=True,
        )
        return matches

    def _save_memory_item(self, store_type: str, item: Dict[str, Any]):
        """保存某一类长期记忆条目。"""
        store = MEMORY_STORE_DEFS[store_type]
        file_path = self.strategies_path / store["file"]
        data = self._read_yaml(file_path, {store["key"]: []})
        items = data.setdefault(store["key"], [])

        existing_index = next(
            (index for index, existing in enumerate(items) if existing.get("id") == item["id"]),
            None,
        )
        if existing_index is None:
            items.append(item)
        else:
            items[existing_index] = item

        self._write_yaml(file_path, data)
        self._rebuild_index()
        if not self._check_capacity():
            self._run_cleanup()
        else:
            self._update_status()

    def _resolve_memory_type(self, event: Dict[str, Any]) -> str:
        """确定立即学习写入哪一类记忆。"""
        explicit = self._normalize_text(event.get("memory_type", ""))
        alias_map = {
            "strategy": "strategy",
            "procedural": "strategy",
            "task_strategy": "strategy",
            "task-strategy": "strategy",
            "preference": "preference",
            "user_preference": "preference",
            "user-preference": "preference",
            "rule": "rule",
            "error_rule": "rule",
            "error-rule": "rule",
        }
        if explicit in alias_map:
            return alias_map[explicit]

        if event.get("category") or event.get("preference"):
            return "preference"
        if event.get("trigger") or event.get("prevention") or event.get("root_cause"):
            return "rule"
        if event.get("type") == "error":
            return "rule"
        return "strategy"

    def _build_strategy_from_event(self, event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """从反馈事件构建任务策略。"""
        feedback = str(event.get("feedback", "")).strip()
        if not feedback:
            return None

        context = event.get("context", {})
        goal = str(event.get("goal", "")).strip()
        return {
            "id": self._generate_id("strategy"),
            "condition": goal or self._context_text(context),
            "action": feedback,
            "weight": float(event.get("weight", 0.8)),
            "source": event.get("source") or event.get("type", "user_feedback"),
            "created": datetime.now().strftime("%Y-%m-%d"),
            "context": self._normalize_context_tags(context),
        }

    def _build_preference_from_event(self, event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """从反馈事件构建用户偏好。"""
        preference = str(event.get("preference") or event.get("feedback", "")).strip()
        if not preference:
            return None

        context = event.get("context", {})
        raw_category = event.get("category") or context.get("category") or "general"
        return {
            "id": self._generate_id("preference"),
            "category": self._slugify(raw_category),
            "preference": preference,
            "weight": float(event.get("weight", 0.85)),
            "evidence": str(
                event.get("evidence")
                or event.get("action")
                or event.get("goal")
                or event.get("feedback", "")
            ).strip(),
            "source": event.get("source") or event.get("type", "user_feedback"),
            "created": datetime.now().strftime("%Y-%m-%d"),
            "context": self._normalize_context_tags(context),
        }

    def _build_rule_from_event(self, event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """从失败或反馈事件构建错误规则。"""
        prevention = str(event.get("prevention") or event.get("feedback", "")).strip()
        trigger = str(event.get("trigger") or event.get("goal") or event.get("action", "")).strip()
        if not trigger or not prevention:
            return None

        context = event.get("context", {})
        return {
            "id": self._generate_id("rule"),
            "trigger": trigger,
            "root_cause": str(
                event.get("root_cause")
                or event.get("outcome")
                or event.get("feedback", "")
            ).strip(),
            "prevention": prevention,
            "weight": float(event.get("weight", 0.85)),
            "source": event.get("source") or event.get("type", "user_feedback"),
            "created": datetime.now().strftime("%Y-%m-%d"),
            "context": self._normalize_context_tags(context),
        }

    def _rebuild_index(self):
        """根据当前策略文件重建索引。"""
        by_condition = {}
        by_context = {}

        for strategy in self.get_all_strategies():
            strategy_id = strategy.get("id")
            if not strategy_id:
                continue

            condition = self._normalize_text(strategy.get("condition", ""))
            if condition:
                by_condition.setdefault(condition, []).append(strategy_id)

            for tag in self._normalize_context_tags(strategy.get("context", [])):
                by_context.setdefault(tag, []).append(strategy_id)

        self.index = {"indexes": {"by_condition": by_condition, "by_context": by_context}}
        self._save_json(self.index_path, self.index)

    def _score_memory_item(
        self,
        item: Dict[str, Any],
        context_text: str,
        context_tags: List[str],
        text_fields: Iterable[str],
    ) -> float:
        """对任意长期记忆条目做统一打分。"""
        score = 0.0
        for field in text_fields:
            score = max(score, self._match_text_score(item.get(field, ""), context_text, context_tags))

        item_tags = set(self._normalize_context_tags(item.get("context", [])))
        if item_tags:
            shared_tags = item_tags.intersection(context_tags)
            if shared_tags:
                score += 0.3 * (len(shared_tags) / len(item_tags))

        weight = float(item.get("weight", 0) or 0)
        return score * (0.5 + max(0.0, weight))

    def _score_strategy(
        self,
        strategy: Dict[str, Any],
        context_text: str,
        context_tags: List[str],
    ) -> float:
        """基于条件、上下文和权重做轻量打分。"""
        return self._score_memory_item(
            strategy,
            context_text,
            context_tags,
            MEMORY_STORE_DEFS["strategy"]["text_fields"],
        )

    def _match_text_score(self, value: Any, context_text: str, context_tags: List[str]) -> float:
        """计算单个文本字段与当前上下文的匹配度。"""
        normalized = self._normalize_text(value)
        if not normalized:
            return 0.0
        if normalized in context_text:
            return 1.0

        terms = set(normalized.split())
        overlap = terms.intersection(context_tags)
        if overlap:
            return 0.4 + min(0.4, 0.1 * len(overlap))
        return 0.0

    def _normalize_context_tags(self, context: Any) -> List[str]:
        """将上下文统一转换为可匹配的标签列表。"""
        tags = []
        seen = set()

        for value in self._flatten_context_values(context):
            normalized = self._normalize_text(value)
            if not normalized:
                continue

            for candidate in [normalized, *normalized.split()]:
                if candidate and candidate not in seen:
                    seen.add(candidate)
                    tags.append(candidate)

        return tags

    def _flatten_context_values(self, value: Any) -> Iterable[str]:
        """将任意上下文结构展开为字符串序列。"""
        if value is None:
            return []

        if isinstance(value, dict):
            flattened = []
            for key, nested_value in value.items():
                flattened.extend(self._flatten_context_values(key))
                flattened.extend(self._flatten_context_values(nested_value))
            return flattened

        if isinstance(value, (list, tuple, set)):
            flattened = []
            for item in value:
                flattened.extend(self._flatten_context_values(item))
            return flattened

        return [str(value)]

    def _context_text(self, context: Any) -> str:
        """将上下文压平成用于模糊匹配的文本。"""
        return " ".join(self._normalize_context_tags(context))

    def _normalize_text(self, value: Any) -> str:
        """统一文本格式，避免大小写和多空格导致的误匹配。"""
        return " ".join(str(value).strip().lower().split())

    def _slugify(self, value: Any) -> str:
        """将分类字段压缩为稳定的 ASCII 风格标签。"""
        normalized = self._normalize_text(value)
        return normalized.replace(" ", "_") or "general"

    def _generate_id(self, prefix: str) -> str:
        """生成带类型前缀的唯一 ID。"""
        return f"{prefix}-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"

    def _normalize_index_ids(self, strategy_ids: Any) -> List[str]:
        """兼容旧索引中的单值结构。"""
        if isinstance(strategy_ids, list):
            return [str(item) for item in strategy_ids if item]
        if strategy_ids:
            return [str(strategy_ids)]
        return []

    def _check_capacity(self) -> bool:
        """检查容量是否低于触发阈值。"""
        status = self._collect_status()
        trigger = float(self.governance.get("events", {}).get("cleanup_trigger", 0.8)) * 100

        return (
            status["usage"]["events"]["usage_percent"] < trigger
            and status["usage"]["strategies"]["usage_percent"] < trigger
        )

    def _collect_status(self) -> Dict[str, Any]:
        """收集当前事件和策略占用情况。"""
        events_size = 0
        events_count = 0
        for event_file in self.events_path.glob("*.jsonl"):
            events_size += event_file.stat().st_size
            with open(event_file, encoding="utf-8") as file_handle:
                events_count += sum(1 for _ in file_handle)

        strategies_size = 0
        strategies_count = 0
        for yaml_file in self.strategies_path.glob("*.yaml"):
            strategies_size += yaml_file.stat().st_size
            data = self._read_yaml(yaml_file, {})
            for store in MEMORY_STORE_DEFS.values():
                strategies_count += len(data.get(store["key"], []))

        max_event_count = max(1, int(self.governance["events"]["max_count"]))
        max_event_size_kb = max(1, int(self.governance["events"]["max_size_mb"]) * 1024)
        max_strategy_count = max(1, int(self.governance["strategies"]["max_count"]))
        max_strategy_size_kb = max(1, int(self.governance["strategies"]["max_size_kb"]))

        event_size_kb = events_size / 1024
        strategy_size_kb = strategies_size / 1024
        event_usage = max(events_count / max_event_count, event_size_kb / max_event_size_kb) * 100
        strategy_usage = max(
            strategies_count / max_strategy_count,
            strategy_size_kb / max_strategy_size_kb,
        ) * 100

        return {
            "usage": {
                "events": {
                    "count": events_count,
                    "size_kb": round(event_size_kb, 2),
                    "usage_percent": round(event_usage, 2),
                },
                "strategies": {
                    "count": strategies_count,
                    "size_kb": round(strategy_size_kb, 2),
                    "usage_percent": round(strategy_usage, 2),
                },
            },
            "last_check": datetime.now().isoformat(),
        }

    def _get_status(self) -> Dict[str, Any]:
        """获取当前状态。"""
        return self._read_json(self.status_path, deepcopy(DEFAULT_STATUS))

    def _update_status(self):
        """刷新状态文件。"""
        self._save_json(self.status_path, self._collect_status())

    def _run_cleanup(self):
        """按保留期和硬限制清理事件文件。"""
        retention_days = int(self.governance.get("events", {}).get("retention_days", 7))
        cutoff = datetime.now().date() - timedelta(days=retention_days)

        for event_file in sorted(self.events_path.glob("*.jsonl")):
            try:
                event_date = datetime.strptime(event_file.stem, "%Y-%m-%d").date()
            except ValueError:
                continue

            if event_date < cutoff:
                event_file.unlink(missing_ok=True)

        max_count = int(self.governance["events"]["max_count"])
        max_size_bytes = int(self.governance["events"]["max_size_mb"]) * 1024 * 1024

        while True:
            status = self._collect_status()
            if (
                status["usage"]["events"]["count"] <= max_count
                and status["usage"]["events"]["size_kb"] * 1024 <= max_size_bytes
            ):
                break

            event_files = sorted(self.events_path.glob("*.jsonl"))
            if not event_files:
                break
            event_files[0].unlink(missing_ok=True)

        self._prune_memory_stores()
        self._rebuild_index()
        self._update_status()

    def _prune_memory_stores(self):
        """按权重、数量和文件大小裁剪长期记忆。"""
        for store_type, store in MEMORY_STORE_DEFS.items():
            file_path = self.strategies_path / store["file"]
            data = self._read_yaml(file_path, {store["key"]: []})
            items = data.get(store["key"], [])
            if not isinstance(items, list):
                items = []

            min_weight = float(self.governance["strategies"].get("min_weight", 0))
            items = [
                item
                for item in items
                if float(item.get("weight", 0) or 0) >= min_weight
            ]

            items.sort(
                key=lambda item: (
                    float(item.get("weight", 0) or 0),
                    item.get("created", ""),
                    item.get("id", ""),
                ),
                reverse=True,
            )

            max_count = int(self.governance["strategies"]["max_count"])
            max_size_bytes = int(self.governance["strategies"]["max_size_kb"]) * 1024
            items = items[:max_count]
            data[store["key"]] = items
            self._write_yaml(file_path, data)

            while file_path.stat().st_size > max_size_bytes and len(items) > 1:
                items.pop()
                data[store["key"]] = items
                self._write_yaml(file_path, data)

    def _read_yaml(self, file_path: Path, default: Any) -> Any:
        """读取 YAML 文件，失败时返回默认值。"""
        try:
            with open(file_path, encoding="utf-8") as file_handle:
                data = yaml.safe_load(file_handle)
                return data if data is not None else deepcopy(default)
        except (FileNotFoundError, yaml.YAMLError):
            return deepcopy(default)

    def _write_yaml(self, file_path: Path, data: Any):
        """写入 YAML 文件。"""
        with open(file_path, "w", encoding="utf-8") as file_handle:
            yaml.safe_dump(data, file_handle, allow_unicode=True, sort_keys=False)

    def _read_json(self, file_path: Path, default: Any) -> Any:
        """读取 JSON 文件，失败时返回默认值。"""
        try:
            with open(file_path, encoding="utf-8") as file_handle:
                return json.load(file_handle)
        except (FileNotFoundError, json.JSONDecodeError):
            return deepcopy(default)

    def _save_json(self, file_path: Path, data: Any):
        """写入 JSON 文件。"""
        with open(file_path, "w", encoding="utf-8") as file_handle:
            json.dump(data, file_handle, indent=2, ensure_ascii=False)

    def _merge_dicts(self, base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        """递归合并配置字典。"""
        for key, value in override.items():
            if isinstance(value, dict) and isinstance(base.get(key), dict):
                base[key] = self._merge_dicts(base[key], value)
            else:
                base[key] = value
        return base


# ============================================
# 便捷函数
# ============================================

_memory = None


def get_memory() -> MemorySystem:
    """获取单例实例。"""
    global _memory
    if _memory is None:
        _memory = MemorySystem()
    return _memory


def retrieve_strategies(context: Dict[str, Any]) -> List[Dict[str, Any]]:
    """检索相关策略。"""
    return get_memory().retrieve_strategies(context)


def retrieve_preferences(context: Dict[str, Any]) -> List[Dict[str, Any]]:
    """检索相关用户偏好。"""
    return get_memory().retrieve_preferences(context)


def retrieve_error_rules(context: Dict[str, Any]) -> List[Dict[str, Any]]:
    """检索相关错误规则。"""
    return get_memory().retrieve_error_rules(context)


def retrieve_memory(
    context: Dict[str, Any],
    limit_per_type: Optional[int] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """统一检索三类长期记忆。"""
    return get_memory().retrieve_memory(context, limit_per_type=limit_per_type)


def log_event(
    type: str,
    goal: str,
    context: Optional[Dict[str, Any]],
    action: str,
    outcome: str,
    feedback: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """记录事件。"""
    return get_memory().log_event(type, goal, context, action, outcome, feedback)


def learn_immediately(event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """立即学习。"""
    return get_memory().learn_immediately(event)


def build_openclaw_brief(
    context: Dict[str, Any],
    limit_per_type: int = 3,
) -> Dict[str, Any]:
    """构建适合 OpenClaw 使用的记忆摘要。"""
    return get_memory().build_openclaw_brief(context, limit_per_type=limit_per_type)


def render_openclaw_memory(
    context: Dict[str, Any],
    limit_per_type: int = 3,
) -> str:
    """渲染适合注入 OpenClaw 提示词的 Markdown 记忆块。"""
    return get_memory().render_openclaw_memory(context, limit_per_type=limit_per_type)


if __name__ == "__main__":
    memory_system = get_memory()

    print("=== 所有策略 ===")
    for strategy in memory_system.get_all_strategies():
        print(
            f"  [{strategy.get('weight', 0):.2f}] "
            f"{strategy.get('condition', '')} -> {strategy.get('action', '')[:30]}..."
        )

    print("\n=== 检索测试 ===")
    query_context = {"task": "小红书发布", "context": "小红书发布"}
    results = memory_system.retrieve_strategies(query_context)
    print(f"匹配到 {len(results)} 条策略")
    for item in results:
        print(f"  - {item.get('condition')} (score={item.get('score', 0):.2f})")

    print("\n=== OpenClaw Memory ===")
    print(memory_system.render_openclaw_memory(query_context) or "(no relevant memory)")
