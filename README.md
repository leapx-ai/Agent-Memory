# Agent Memory System

A self-evolving memory system for AI agents. Enables agents to learn from experience and continuously improve their behavior strategies.

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
| **Event Logging** | Record events for learning |
| **Immediate Learning** | Generate strategies from user feedback |
| **Memory Governance** | Weight decay, cleanup, archival |
| **Hard Limits** | Prevent unbounded growth |
| **High-Value Archival** | Preserve relearning capability |

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
    action: "Used emoji",
    "outcome": "Rendering broken",
    "feedback": "Don't use emoji, use text instead"
})
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

- **Archive, not delete**: Events that generated strategies are archived
- **Relearn capability**: Can relearn from archive if strategy is wrong
- **Graceful degradation**: Agent works even if memory system fails

## Documentation

| Document | Purpose |
|----------|---------|
| [README.md](./README.md) | This file - overview |
| [ARCHITECTURE.md](./docs/ARCHITECTURE.md) | System architecture |
| [DESIGN.md](./docs/DESIGN.md) | Design principles and decisions |
| [INSTALL.md](./docs/INSTALL.md) | Installation guide |

## Current Capabilities (v1.0.0)

- [x] Strategy storage and retrieval
- [x] Event logging
- [x] Immediate learning from feedback
- [x] Memory governance config
- [x] Hard limits and safety boundaries
- [x] High-value archival design
- [x] Complete documentation

## Roadmap

### v1.1.0 - Automation
- [ ] Automatic event logging after tasks
- [ ] Automatic learning triggers
- [ ] Heartbeat-based governance (decay, cleanup)

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

**Quick integration** - Add to your `AGENTS.md`:

```markdown
## Every Session

Before doing anything else:
1. Read strategies from `~/.openclaw/memory-system/strategies/`
2. Apply relevant strategies to current task
```

## Philosophy

This project is guided by these principles:

1. **Learning > Remembering**: The goal is behavior change, not just storage
2. **Safety First**: Production systems need hard limits
3. **User Sovereignty**: Users should never lose ability to relearn
4. **Simplicity**: Start minimal, evolve based on real usage

## Contributing

Contributions welcome! Please read the design principles in [DESIGN.md](./docs/DESIGN.md) first.

## License

MIT License - See [LICENSE](./LICENSE)