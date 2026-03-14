#!/usr/bin/env python3
"""
Generic runtime integration helpers for Agent-Memory.
"""

from pathlib import Path
from typing import Any, Dict, Optional

from memory import MemorySystem, get_memory


class AgentMemoryAdapter:
    """Thin adapter that maps generic runtime lifecycle events onto the memory system."""

    feedback_source = "agent_feedback"
    error_source = "agent_error"

    def __init__(
        self,
        memory_system: Optional[MemorySystem] = None,
        limit_per_type: int = 3,
    ):
        self.memory = memory_system or get_memory()
        self.limit_per_type = limit_per_type

    def session_start(
        self,
        context: Dict[str, Any],
        limit_per_type: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Build a memory payload for session start or task preflight."""
        limit = limit_per_type or self.limit_per_type
        brief = self.memory.build_runtime_brief(context, limit_per_type=limit)
        return {
            "context": context,
            "brief": brief,
            "decision_brief": brief.get("decision_brief"),
            "prompt_block": self.memory.render_runtime_memory(
                context,
                limit_per_type=limit,
            ),
        }

    def before_task(
        self,
        context: Dict[str, Any],
        limit_per_type: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Alias for task preflight usage."""
        return self.session_start(context, limit_per_type=limit_per_type)

    def task_complete(
        self,
        goal: str,
        context: Dict[str, Any],
        action: str,
        outcome: str,
        feedback: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Record a completed task."""
        return self.memory.log_event(
            type="task_complete",
            goal=goal,
            context=context,
            action=action,
            outcome=outcome,
            feedback=feedback,
        )

    def user_feedback(
        self,
        goal: str,
        context: Dict[str, Any],
        action: str,
        feedback: str,
        outcome: str = "feedback_received",
        memory_type: Optional[str] = None,
        category: Optional[str] = None,
        evidence: Optional[str] = None,
        source: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Record direct user feedback and learn from it immediately."""
        event = {
            "type": "user_feedback",
            "goal": goal,
            "context": context,
            "action": action,
            "outcome": outcome,
            "feedback": feedback,
            "source": source or self.feedback_source,
        }
        if memory_type:
            event["memory_type"] = memory_type
        if category:
            event["category"] = category
        if evidence:
            event["evidence"] = evidence

        logged = self.memory.log_event(
            type="user_feedback",
            goal=goal,
            context=context,
            action=action,
            outcome=outcome,
            feedback=feedback,
        )
        learned = self.memory.learn_immediately(event)
        return {
            "event": logged,
            "memory_item": learned,
            "memory_type": self._infer_memory_type(event) if learned else None,
        }

    def record_error(
        self,
        goal: str,
        context: Dict[str, Any],
        action: str,
        outcome: str,
        trigger: Optional[str] = None,
        feedback: Optional[str] = None,
        prevention: Optional[str] = None,
        root_cause: Optional[str] = None,
        source: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Record an error and optionally turn it into an error rule."""
        event = {
            "type": "error",
            "goal": goal,
            "context": context,
            "action": action,
            "trigger": trigger or action or goal,
            "outcome": outcome,
            "feedback": feedback,
            "prevention": prevention,
            "root_cause": root_cause,
            "source": source or self.error_source,
            "memory_type": "rule",
        }
        logged = self.memory.log_event(
            type="error",
            goal=goal,
            context=context,
            action=action,
            outcome=outcome,
            feedback=feedback,
        )

        learned = None
        if prevention or feedback:
            learned = self.memory.learn_immediately(event)

        return {
            "event": logged,
            "memory_item": learned,
        }

    def publish_memory(
        self,
        target_root: Optional[Path] = None,
        context: Optional[Dict[str, Any]] = None,
        limit_per_type: Optional[int] = None,
        mode: str = "incremental",
    ) -> Dict[str, Any]:
        """Publish governed memory into host-memory files."""
        limit = limit_per_type or self.limit_per_type
        return self.memory.publish_host_memory(
            target_root=target_root,
            context=context or {},
            limit_per_type=limit,
            mode=mode,
        )

    def _infer_memory_type(self, event: Dict[str, Any]) -> str:
        """Keep adapter output stable without exposing memory internals."""
        explicit = str(event.get("memory_type", "")).strip().lower()
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


def get_adapter(
    memory_system: Optional[MemorySystem] = None,
    limit_per_type: int = 3,
) -> AgentMemoryAdapter:
    """Create a generic runtime adapter with shared memory by default."""
    return AgentMemoryAdapter(memory_system=memory_system, limit_per_type=limit_per_type)


def session_start(
    context: Dict[str, Any],
    memory_system: Optional[MemorySystem] = None,
    limit_per_type: int = 3,
) -> Dict[str, Any]:
    """Build the session-start memory payload."""
    return get_adapter(memory_system, limit_per_type).session_start(context)


def before_task(
    context: Dict[str, Any],
    memory_system: Optional[MemorySystem] = None,
    limit_per_type: int = 3,
) -> Dict[str, Any]:
    """Build the task-preflight memory payload."""
    return get_adapter(memory_system, limit_per_type).before_task(context)


def task_complete(
    goal: str,
    context: Dict[str, Any],
    action: str,
    outcome: str,
    feedback: Optional[str] = None,
    memory_system: Optional[MemorySystem] = None,
) -> Optional[Dict[str, Any]]:
    """Record a completed task through the generic runtime adapter."""
    return get_adapter(memory_system).task_complete(
        goal=goal,
        context=context,
        action=action,
        outcome=outcome,
        feedback=feedback,
    )


def user_feedback(
    goal: str,
    context: Dict[str, Any],
    action: str,
    feedback: str,
    outcome: str = "feedback_received",
    memory_type: Optional[str] = None,
    category: Optional[str] = None,
    evidence: Optional[str] = None,
    memory_system: Optional[MemorySystem] = None,
) -> Dict[str, Any]:
    """Record direct feedback and learn immediately."""
    return get_adapter(memory_system).user_feedback(
        goal=goal,
        context=context,
        action=action,
        feedback=feedback,
        outcome=outcome,
        memory_type=memory_type,
        category=category,
        evidence=evidence,
    )


def record_error(
    goal: str,
    context: Dict[str, Any],
    action: str,
    outcome: str,
    trigger: Optional[str] = None,
    feedback: Optional[str] = None,
    prevention: Optional[str] = None,
    root_cause: Optional[str] = None,
    memory_system: Optional[MemorySystem] = None,
) -> Dict[str, Any]:
    """Record an error and optionally create an error rule."""
    return get_adapter(memory_system).record_error(
        goal=goal,
        context=context,
        action=action,
        outcome=outcome,
        trigger=trigger,
        feedback=feedback,
        prevention=prevention,
        root_cause=root_cause,
    )


def publish_memory(
    target_root: Optional[Path] = None,
    context: Optional[Dict[str, Any]] = None,
    mode: str = "incremental",
    memory_system: Optional[MemorySystem] = None,
    limit_per_type: int = 3,
) -> Dict[str, Any]:
    """Publish governed memory into host-memory files."""
    return get_adapter(memory_system, limit_per_type).publish_memory(
        target_root=target_root,
        context=context or {},
        mode=mode,
    )
