# Roadmap

This document defines the release target for Agent-Memory as an independent memory governance system that OpenClaw can consume.

## Release Positioning

Current state: `v1.0.0`

Interpretation:

- The core memory loop works locally
- The OpenClaw adapter exists
- A standalone CLI contract exists
- Tests cover the standalone contract and governance basics

## v1.0.0 Goal

`v1.0.0` means Agent-Memory is usable as a standalone system for OpenClaw, not just as a collection of helper modules.

At `v1.0.0`, OpenClaw should be able to treat Agent-Memory as an external dependency with a stable call contract.

## v1.0.0 Scope

Required:

- Stable storage and retrieval for events, strategies, user preferences, and error rules
- Stable governance behavior for bootstrap, indexing, cleanup triggers, and hard limits
- Stable OpenClaw lifecycle contract:
  - session start / task preflight
  - task complete
  - user feedback
  - error recording
- Standalone invocation surface:
  - Python SDK
  - CLI
- Installation and usage documentation for independent consumption
- Automated tests for core standalone behavior

Out of scope:

- Automatic wiring inside the OpenClaw runtime
- HTTP service deployment
- Multi-agent synchronization
- Semantic search / vector retrieval
- Background decay and archive workers

## v1.0.0 Completion

Completed in `v1.0.0`:

- Stable storage and retrieval for strategies, preferences, and error rules
- Stable OpenClaw adapter surface in `openclaw_integration.py`
- Standalone CLI in `agent_memory_cli.py`
- Automated tests for adapter, CLI, bootstrap, indexing, and cleanup behavior
- Versioned documentation for independent OpenClaw consumption

## Post-1.0.0 Milestones

### M1: Stable Core

- Keep `memory.py` as the governance and retrieval core
- Keep file-backed persistence and bounded local storage
- Preserve test coverage for retrieval and learning

### M2: Stable OpenClaw Contract

- Keep `openclaw_integration.py` as the OpenClaw-oriented adapter surface
- Freeze request/response shapes for session start, task completion, user feedback, and error recording
- Ensure the adapter does not expose storage internals

### M3: Standalone Invocation

- Keep the CLI commands stable:
  - `session-start`
  - `task-complete`
  - `user-feedback`
  - `record-error`
- Preserve JSON file and stdin input compatibility so OpenClaw is not forced to import Python modules directly

### M4: Release Hardening

- Expand tests to cover CLI behavior
- Add release-oriented installation steps
- Document version boundary: what `v1.0.0` guarantees and what it does not

## Post-1.0.0

### v1.1.0 - Automation

- Automatic event logging after tasks
- Automatic learning triggers
- Heartbeat-based governance jobs

### v1.2.0 - Intelligence

- LLM-powered strategy extraction
- Semantic retrieval
- Pattern mining from events

### v1.3.0 - Collaboration

- Cross-agent sharing
- Team memory systems
- Strategy distribution workflows
