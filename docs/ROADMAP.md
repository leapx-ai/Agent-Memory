# Roadmap

This document defines the release target for Agent-Memory as an independent memory governance system for agent runtimes, with OpenClaw as the current reference integration.

## Release Positioning

Current state: `v1.0.0`

Interpretation:

- The core memory loop works locally
- The OpenClaw adapter exists
- A standalone CLI contract exists
- Tests cover the standalone contract and governance basics
- The first decision-enhancement slice now exists on top of the stable `v1.0.0` base

## v1.0.0 Goal

`v1.0.0` means Agent-Memory is usable as a standalone system for a real agent runtime, not just as a collection of helper modules.

At `v1.0.0`, at least one real runtime should be able to treat Agent-Memory as an external dependency with a stable call contract. OpenClaw is that reference runtime today.

## v1.0.0 Scope

Required:

- Stable storage and retrieval for events, strategies, user preferences, and error rules
- Stable governance behavior for bootstrap, indexing, cleanup triggers, and hard limits
- Stable lifecycle contract for the reference runtime:
  - session start / task preflight
  - task complete
  - user feedback
  - error recording
- Standalone invocation surface:
  - Python SDK
  - CLI
- Installation and usage documentation for independent core usage and adapter-based consumption
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
- Stable reference adapter surface in `openclaw_integration.py`
- Standalone CLI in `agent_memory_cli.py`
- Automated tests for adapter, CLI, bootstrap, indexing, and cleanup behavior
- Versioned documentation for independent and adapter-based consumption

## Post-1.0.0 Milestones

### M1: Stable Core

- Keep `memory.py` as the governance and retrieval core
- Keep file-backed persistence and bounded local storage
- Preserve test coverage for retrieval and learning

### M2: Stable OpenClaw Contract

- Keep `openclaw_integration.py` as the reference-runtime adapter surface
- Freeze request/response shapes for session start, task completion, user feedback, and error recording
- Ensure the adapter does not expose storage internals

### M3: Standalone Invocation

- Keep the CLI commands stable:
  - `session-start`
  - `task-complete`
  - `user-feedback`
  - `record-error`
- Preserve JSON file and stdin input compatibility so runtimes are not forced to import Python modules directly

### M4: Release Hardening

- Expand tests to cover CLI behavior
- Add release-oriented installation steps
- Document version boundary: what `v1.0.0` guarantees and what it does not

### M5: Decision Enhancement Layer

Initial slice completed:

- first structured Decision Brief
- first host-memory publisher
- first selector / ranker on top of raw retrieval
- adapter and CLI exposure for the new layer

Remaining hardening:

- harden the selector / ranker that sits on top of raw retrieval
- harden the publisher for durable and recent host-memory projection, with OpenClaw as the first target
- refine the structured Decision Brief beyond the initial implementation
- keep projection outputs separate from source-of-truth storage and governance

### M6: Metrics And Effectiveness Layer

Initial bounded slice completed:

- bounded run-level observability rather than full runtime replay
- type-level correction, error, success, and clean-run reporting
- record `RunManifest` on session start
- record `RunOutcome` from task completion, user feedback, and error events
- ship a local report surface for recent windows such as 7 days

Remaining hardening:

- add limited item-level assessment only where link evidence is strong enough
- expand from the current high-leverage categories without falling back to low-value demo rules
- keep item-level status `unresolved` unless a bounded linker can justify a stronger judgment
- improve reporting for bucket comparisons and recent snapshots

## Post-1.0.0

### v1.1.0 - Automation

- Automatic event logging after tasks
- Automatic learning triggers
- Heartbeat-based governance jobs
- Decision Brief hardening and ranking improvements
- Host memory publishing hardening for runtime-facing projection
- Better sync policy for durable vs daily host memory
- Metrics hardening with richer reports and narrow item-level linking

### v1.2.0 - Intelligence

- LLM-powered strategy extraction
- Semantic retrieval
- Pattern mining from events

### v1.3.0 - Collaboration

- Cross-agent sharing
- Team memory systems
- Strategy distribution workflows
