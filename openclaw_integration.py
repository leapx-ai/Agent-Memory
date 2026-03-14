#!/usr/bin/env python3
"""
OpenClaw memory integration helpers.

This module keeps the OpenClaw-facing compatibility surface stable while
building on top of the generic runtime adapter.
"""

from pathlib import Path
from typing import Any, Dict, Optional

from memory import MemorySystem
from runtime_integration import AgentMemoryAdapter


class OpenClawMemoryAdapter(AgentMemoryAdapter):
    """Reference adapter that keeps OpenClaw-specific defaults and naming."""

    feedback_source = "openclaw_feedback"
    error_source = "openclaw_error"


def get_openclaw_adapter(
    memory_system: Optional[MemorySystem] = None,
    limit_per_type: int = 3,
) -> OpenClawMemoryAdapter:
    """Create an OpenClaw adapter with shared memory by default."""
    return OpenClawMemoryAdapter(memory_system=memory_system, limit_per_type=limit_per_type)


def openclaw_session_start(
    context: Dict[str, Any],
    memory_system: Optional[MemorySystem] = None,
    limit_per_type: int = 3,
) -> Dict[str, Any]:
    """Build the OpenClaw session-start memory payload."""
    return get_openclaw_adapter(memory_system, limit_per_type).session_start(context)


def openclaw_before_task(
    context: Dict[str, Any],
    memory_system: Optional[MemorySystem] = None,
    limit_per_type: int = 3,
) -> Dict[str, Any]:
    """Build the OpenClaw task-preflight memory payload."""
    return get_openclaw_adapter(memory_system, limit_per_type).before_task(context)


def openclaw_task_complete(
    goal: str,
    context: Dict[str, Any],
    action: str,
    outcome: str,
    feedback: Optional[str] = None,
    memory_system: Optional[MemorySystem] = None,
) -> Optional[Dict[str, Any]]:
    """Record a completed task through the OpenClaw adapter."""
    return get_openclaw_adapter(memory_system).task_complete(
        goal=goal,
        context=context,
        action=action,
        outcome=outcome,
        feedback=feedback,
    )


def openclaw_user_feedback(
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
    return get_openclaw_adapter(memory_system).user_feedback(
        goal=goal,
        context=context,
        action=action,
        feedback=feedback,
        outcome=outcome,
        memory_type=memory_type,
        category=category,
        evidence=evidence,
    )


def openclaw_record_error(
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
    return get_openclaw_adapter(memory_system).record_error(
        goal=goal,
        context=context,
        action=action,
        outcome=outcome,
        trigger=trigger,
        feedback=feedback,
        prevention=prevention,
        root_cause=root_cause,
    )


def openclaw_publish_memory(
    target_root: Optional[Path] = None,
    context: Optional[Dict[str, Any]] = None,
    mode: str = "incremental",
    memory_system: Optional[MemorySystem] = None,
    limit_per_type: int = 3,
) -> Dict[str, Any]:
    """Publish governed memory into OpenClaw host-memory files."""
    return get_openclaw_adapter(memory_system, limit_per_type).publish_memory(
        target_root=target_root,
        context=context or {},
        mode=mode,
    )
