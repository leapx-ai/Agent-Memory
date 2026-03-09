#!/usr/bin/env python3
"""
Standalone CLI for Agent-Memory.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from openclaw_integration import OpenClawMemoryAdapter

VERSION = "1.0.0"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Standalone CLI for the Agent-Memory governance system."
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"agent-memory {VERSION}",
    )
    parser.add_argument(
        "--home",
        help="Override the memory storage root. Defaults to AGENT_MEMORY_HOME or ~/.openclaw/memory-system.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    session_start = subparsers.add_parser(
        "session-start",
        help="Build a memory payload for session start or task preflight.",
    )
    _add_json_input_options(session_start)
    session_start.add_argument(
        "--limit-per-type",
        type=int,
        default=None,
        help="Maximum number of strategies/preferences/rules to return per category.",
    )
    session_start.add_argument(
        "--prompt-only",
        action="store_true",
        help="Print only the prompt_block string instead of the full JSON payload.",
    )

    task_complete = subparsers.add_parser(
        "task-complete",
        help="Record a completed task.",
    )
    _add_json_input_options(task_complete)

    user_feedback = subparsers.add_parser(
        "user-feedback",
        help="Record direct user feedback and learn from it immediately.",
    )
    _add_json_input_options(user_feedback)

    record_error = subparsers.add_parser(
        "record-error",
        help="Record an error and optionally learn an error rule.",
    )
    _add_json_input_options(record_error)

    return parser


def _add_json_input_options(parser: argparse.ArgumentParser):
    parser.add_argument(
        "--input",
        help="Path to a JSON file. If omitted, stdin is used when available.",
    )
    parser.add_argument(
        "--json",
        help="Inline JSON payload.",
    )


def load_payload(args: argparse.Namespace) -> Dict[str, Any]:
    sources = [bool(getattr(args, "input", None)), bool(getattr(args, "json", None))]
    if sum(sources) > 1:
        raise ValueError("Use only one of --input or --json.")

    if getattr(args, "input", None):
        raw = Path(args.input).read_text(encoding="utf-8")
    elif getattr(args, "json", None):
        raw = args.json
    else:
        if sys.stdin.isatty():
            raise ValueError("Expected JSON input from --input, --json, or stdin.")
        raw = sys.stdin.read()

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON payload: {exc}") from exc

    if not isinstance(payload, dict):
        raise ValueError("Top-level payload must be a JSON object.")

    return payload


def build_adapter(home: Optional[str]) -> "OpenClawMemoryAdapter":
    from memory import MemorySystem
    from openclaw_integration import OpenClawMemoryAdapter

    base_path = Path(home).expanduser() if home else None
    memory_system = MemorySystem(base_path=base_path)
    return OpenClawMemoryAdapter(memory_system=memory_system)


def handle_session_start(adapter: "OpenClawMemoryAdapter", args: argparse.Namespace) -> Any:
    payload = load_payload(args)
    context = payload.get("context", payload)
    if not isinstance(context, dict):
        raise ValueError("session-start requires a JSON object context.")

    limit_per_type = (
        args.limit_per_type
        if args.limit_per_type is not None
        else payload.get("limit_per_type", adapter.limit_per_type)
    )
    result = adapter.session_start(context, limit_per_type=limit_per_type)
    if args.prompt_only:
        return result["prompt_block"]
    return result


def handle_task_complete(
    adapter: "OpenClawMemoryAdapter",
    args: argparse.Namespace,
) -> Dict[str, Any]:
    payload = load_payload(args)
    result = adapter.task_complete(
        goal=_required_str(payload, "goal"),
        context=_required_dict(payload, "context"),
        action=_required_str(payload, "action"),
        outcome=_required_str(payload, "outcome"),
        feedback=payload.get("feedback"),
    )
    return {"event": result}


def handle_user_feedback(
    adapter: "OpenClawMemoryAdapter",
    args: argparse.Namespace,
) -> Dict[str, Any]:
    payload = load_payload(args)
    return adapter.user_feedback(
        goal=_required_str(payload, "goal"),
        context=_required_dict(payload, "context"),
        action=_required_str(payload, "action"),
        feedback=_required_str(payload, "feedback"),
        outcome=str(payload.get("outcome", "feedback_received")),
        memory_type=payload.get("memory_type"),
        category=payload.get("category"),
        evidence=payload.get("evidence"),
        source=str(payload.get("source", "openclaw_feedback")),
    )


def handle_record_error(
    adapter: "OpenClawMemoryAdapter",
    args: argparse.Namespace,
) -> Dict[str, Any]:
    payload = load_payload(args)
    return adapter.record_error(
        goal=_required_str(payload, "goal"),
        context=_required_dict(payload, "context"),
        action=_required_str(payload, "action"),
        outcome=_required_str(payload, "outcome"),
        trigger=payload.get("trigger"),
        feedback=payload.get("feedback"),
        prevention=payload.get("prevention"),
        root_cause=payload.get("root_cause"),
        source=str(payload.get("source", "openclaw_error")),
    )


def _required_str(payload: Dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Field '{key}' is required and must be a non-empty string.")
    return value


def _required_dict(payload: Dict[str, Any], key: str) -> Dict[str, Any]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"Field '{key}' is required and must be a JSON object.")
    return value


def emit_output(output: Any):
    if isinstance(output, str):
        print(output)
        return

    json.dump(output, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    adapter = build_adapter(args.home)

    handlers = {
        "session-start": handle_session_start,
        "task-complete": handle_task_complete,
        "user-feedback": handle_user_feedback,
        "record-error": handle_record_error,
    }

    try:
        result = handlers[args.command](adapter, args)
    except ValueError as exc:
        parser.error(str(exc))
        return 2

    emit_output(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
