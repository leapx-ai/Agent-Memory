# Agent Memory System

A self-evolving memory system for AI agents. Enables agents to learn from experience and continuously improve their behavior strategies.

## Core Concept

Traditional Agent:
```
LLM → Reasoning → Output
```

Self-Evolving Agent:
```
Experience → Learning → Strategy Update
```

## Features

- **Strategy Retrieval**: Get relevant strategies before task execution
- **Event Logging**: Record events for learning
- **Immediate Learning**: Generate strategies from user feedback
- **Memory Governance**: Weight decay, cleanup, archival

## Quick Start

```python
from memory import retrieve_strategies, log_event, learn_immediately

# Before task: retrieve relevant strategies
strategies = retrieve_strategies({"task": "content_publishing"})
for s in strategies:
    print(f"[{s['weight']}] {s['condition']} → {s['action']}")

# After task: log event
log_event(
    type="task_complete",
    goal="Publish content",
    action="Used API to publish",
    outcome="success",
    feedback="Image rendering issue"
)

# When user gives feedback: learn immediately
learn_immediately({
    "type": "user_feedback",
    "goal": "Generate images",
    "action": "Used emoji",
    "outcome": "Rendering broken",
    "feedback": "Don't use emoji, use text instead"
})
```

## Directory Structure

```
~/.openclaw/memory-system/
├── events/                    # Event store (short-term)
│   └── 2026-03-09.jsonl
├── strategies/                # Strategy store (long-term)
│   ├── task-strategies.yaml
│   ├── user-preferences.yaml
│   └── error-rules.yaml
├── governance.yaml            # Governance config
├── index.json                 # Strategy index
├── status.json                # System status
└── memory.py                  # Interface layer
```

## Hard Limits

Ensure system stability:

| Component | Limit | Description |
|-----------|-------|-------------|
| events | 10MB / 1000 items | Max size/count |
| strategies | 50KB / 100 items | Max size/count |
| retention | 7 days | Event retention |

## Architecture

See [ARCHITECTURE.md](./docs/ARCHITECTURE.md) for detailed design.

## Current Capabilities (v1.0.0)

- [x] Strategy storage and retrieval
- [x] Event logging
- [x] Immediate learning from feedback
- [x] Memory governance config
- [x] Hard limits and safety boundaries
- [x] High-value archival design

## Roadmap

### v1.1.0
- [ ] Automatic weight decay
- [ ] Strategy merging and deduplication
- [ ] Event archival implementation

### v1.2.0
- [ ] Relearn from archive
- [ ] Cross-agent strategy sharing
- [ ] Web UI for management

## License

MIT License