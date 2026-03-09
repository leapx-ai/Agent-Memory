# Agent Memory System

A self-evolving memory system for AI agents, currently optimized as a memory layer for OpenClaw. It enables the agent to learn from experience and continuously improve its behavior strategies, user preference handling, and error prevention.

## Why This Matters

**Traditional AI agents forget everything between sessions.**

```
Day 1: Agent solves problem X
Day 2: Agent encounters problem X again
       Agent: "Let me research this from scratch..."
       User: "We solved this yesterday!"
```

**Self-evolving agents learn and improve:**

```
Day 1: Agent solves problem X → Strategy created
Day 2: Agent encounters problem X
       Agent: "I have a strategy for this" → Apply → Succeed
       User: "Finally, it remembers!"
```

## Core Concept

```
Traditional Agent:
  LLM → Reasoning → Output

Self-Evolving Agent:
  Experience → Learning → Strategy Update → Improved Behavior
       ↑                                           ↓
       └───────────────────────────────────────────┘
                     Continuous Evolution
```

## Features

| Feature | Description |
|---------|-------------|
| **Strategy Retrieval** | Get relevant strategies before task execution |
| **OpenClaw Session Brief** | Build a ready-to-inject memory block for session start and task preflight |
| **Event Logging** | Record events for learning |
| **Immediate Learning** | Turn direct feedback into strategies, preferences, or error rules |
| **Preference Memory** | Surface user communication and workflow preferences |
| **Error Rule Memory** | Surface mistakes and preventions before repeating them |
| **Memory Governance** | Capacity tracking, cleanup trigger, safe defaults |
| **Hard Limits** | Prevent unbounded growth |
| **Bootstrap Setup** | Auto-create required directories and files on first run |

## Quick Start

```python
from openclaw_integration import (
    OpenClawMemoryAdapter,
    openclaw_record_error,
    openclaw_task_complete,
    openclaw_user_feedback,
)

adapter = OpenClawMemoryAdapter()

# Before task: build a memory brief for OpenClaw
payload = adapter.session_start({
    "task": "content_publishing",
    "workspace": "blog",
    "channel": "blog",
})
print(payload["brief"]["summary"])
print(payload["prompt_block"])

# After task: log event
openclaw_task_complete(
    goal="Publish content",
    context={"task": "content_publishing", "channel": "blog"},
    action="Used API to publish",
    outcome="success",
    feedback="Image rendering issue"
)

# When user gives feedback: learn immediately
openclaw_user_feedback(
    goal="Generate images",
    context={"task": "image_generation"},
    action="Used emoji",
    feedback="Don't use emoji, use text instead",
)

# Learn a user preference explicitly
openclaw_user_feedback(
    goal="Respond to the user",
    context={"surface": "chat"},
    action="Sent a verbose answer",
    feedback="Be concise, avoid mechanical responses",
    memory_type="preference",
    category="communication_style",
)

# Learn an error-prevention rule explicitly
openclaw_record_error(
    goal="Generate image",
    context={"task": "image_generation"},
    action="Used emoji in generated images",
    outcome="renderer_failed",
    prevention="Use plain text labels instead of emoji",
    root_cause="Renderer fails on emoji glyphs",
)
```

For local development, you can point the storage elsewhere:

```bash
export AGENT_MEMORY_HOME=/tmp/agent-memory
```

## Directory Structure

```
~/.openclaw/memory-system/
├── events/                    # Event store (short-term)
│   └── 2026-03-09.jsonl       # Daily event files
├── strategies/                # Strategy store (long-term)
│   ├── task-strategies.yaml   # How to behave
│   ├── user-preferences.yaml  # User preferences
│   └── error-rules.yaml       # Mistakes to avoid
├── governance.yaml            # Governance config
├── index.json                 # Strategy index
├── status.json                # System status
└── memory.py                  # Interface layer
```

## Safety Guarantees

### Hard Limits

Ensure system stability:

| Component | Limit | Description |
|-----------|-------|-------------|
| events | 10MB / 1000 items | Max size/count |
| strategies | 50KB / 100 items | Max size/count |
| retention | 7 days | Event retention |

### Data Sovereignty

- **Cleanup before sprawl**: Old event files are trimmed when retention or hard limits are exceeded
- **Relearn-friendly design**: Archive path and governance model are reserved for future relearning workflows
- **Graceful degradation**: Agent works even if memory system fails

## Documentation

| Document | Purpose |
|----------|---------|
| [README.md](./README.md) | This file - overview |
| [CLI.md](./docs/CLI.md) | Stable CLI contract for external callers |
| [ROADMAP.md](./docs/ROADMAP.md) | Post-1.0.0 milestone plan |
| [ARCHITECTURE.md](./docs/ARCHITECTURE.md) | System architecture |
| [DESIGN.md](./docs/DESIGN.md) | Design principles and decisions |
| [INSTALL.md](./docs/INSTALL.md) | Installation guide |

## Current Release (v1.0.0)

- [x] Strategy storage and retrieval
- [x] Preference and error-rule retrieval for OpenClaw
- [x] Event logging
- [x] Immediate learning into strategies, preferences, and rules
- [x] First-run bootstrap for storage files
- [x] Index rebuild after strategy updates
- [x] OpenClaw session brief rendering
- [x] Capacity tracking and cleanup trigger
- [x] Hard limits and safety boundaries
- [x] Complete documentation

## v1.0.0 Definition

`v1.0.0` is the release where Agent-Memory becomes a standalone memory governance system that OpenClaw can call as an external dependency, instead of being treated as an in-repo helper layer.

The `v1.0.0` release must provide:

- A stable memory engine for events, strategies, preferences, and error rules
- A stable OpenClaw adapter layer for session start, task completion, feedback, and error ingestion
- A standalone integration surface beyond raw imports, with CLI support as the default portability target
- Governance guarantees with tested bootstrap, indexing, cleanup, and bounded storage behavior
- Versioned documentation that explains how OpenClaw consumes the system without relying on internal implementation details

The `v1.0.0` release does not require:

- Automatic runtime hooks inside OpenClaw itself
- Semantic/vector retrieval
- Background decay/archive automation
- Multi-agent sync or service deployment

## Standalone CLI

`v1.0.0` ships a standalone CLI as the default portability layer:

```bash
python3 agent_memory_cli.py --help
```

Primary commands:

- `session-start`
- `task-complete`
- `user-feedback`
- `record-error`

See [CLI.md](./docs/CLI.md) for the stable input/output contract.

## Roadmap

### v1.1.0 - Automation
- [ ] Automatic event logging after tasks
- [ ] Automatic learning triggers
- [ ] Heartbeat-based governance (decay, archive)

### v1.2.0 - Intelligence
- [ ] LLM-powered strategy extraction
- [ ] Semantic strategy matching
- [ ] Pattern mining from events

### v1.3.0 - Collaboration
- [ ] Cross-agent strategy sharing
- [ ] Strategy marketplace
- [ ] Team memory systems

### v2.0.0 - Enterprise
- [ ] Web UI for memory management
- [ ] Analytics dashboard
- [ ] Role-based access control

## Integration with OpenClaw

See [DESIGN.md](./docs/DESIGN.md#integration-architecture) for detailed integration architecture.

**Quick integration** - Add to your `AGENTS.md` workflow:

```markdown
## Every Session

Before doing anything else:
1. Create an `OpenClawMemoryAdapter`
2. Call `adapter.session_start({...current task context...})`
3. Apply returned strategies, user preferences, and error rules before acting
4. After the task, call `adapter.task_complete(...)`
5. If the user gives direct corrective feedback, call `adapter.user_feedback(...)`
```

### OpenClaw Workflow

For OpenClaw, this project is now centered on one primary loop:

1. **Session start / task preflight**: call `OpenClawMemoryAdapter.session_start()`
2. **Task execution**: use the returned strategies, preferences, and error rules
3. **Task completion**: call `OpenClawMemoryAdapter.task_complete()`
4. **Direct correction**: call `OpenClawMemoryAdapter.user_feedback()` or `OpenClawMemoryAdapter.record_error()`

## Philosophy

This project is guided by these principles:

1. **Learning > Remembering**: The goal is behavior change, not just storage
2. **Safety First**: Production systems need hard limits
3. **User Sovereignty**: Users should never lose ability to relearn
4. **Simplicity**: Start minimal, evolve based on real usage

## Current Boundaries

- Retrieval is lightweight keyword/context matching, not semantic search yet.
- Cleanup is implemented for retention and hard limits; archival and decay are still roadmap items.
- The standalone contract is local-process and file-backed; HTTP/service deployment remains post-`v1.0.0`.

## Testing

```bash
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

## Contributing

Contributions welcome! Please read the design principles in [DESIGN.md](./docs/DESIGN.md) first.

## License

MIT License - See [LICENSE](./LICENSE)
