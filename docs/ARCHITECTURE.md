# Agent Memory Architecture

## Overview

This document describes the architecture of a self-evolving memory system for AI agents, with the current implementation focused on serving OpenClaw.

Release status:

- Current state: `v1.0.0`
- Release meaning: independent memory governance system callable by OpenClaw

## Core Principle

The key insight: **Self-Evolving Agent's core is not LLM, but Experience → Strategy Learning.**

```
Traditional Agent:
  LLM → Reasoning → Output

Self-Evolving Agent:
  Experience → Learning → Strategy Update
  ↓
  Improved Behavior → New Experience
  ↓
  (loop)
```

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Agent Runtime                            │
│  (Task execution, tool calls, user interaction)            │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                   Experience Logger                         │
│  Record: interaction, tool_call, error, feedback, result   │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                     Event Store                             │
│  Raw events (short-term, with limits)                       │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                   Learning Engine                           │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐           │
│  │  Pattern    │ │  Failure    │ │  Strategy   │           │
│  │  Extraction │ │  Analysis   │ │  Builder    │           │
│  └─────────────┘ └─────────────┘ └─────────────┘           │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                   Memory Governance                         │
│  Admission │ Weight │ Merge │ Decay                         │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                   Memory Store                              │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐           │
│  │  Knowledge  │ │   Error     │ │ Procedural  │           │
│  │   Memory    │ │   Memory    │ │   Memory    │           │
│  └─────────────┘ └─────────────┘ └─────────────┘           │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                  Retrieval Engine                           │
│  Semantic similarity + Weight ranking + Context relevance  │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
                   Back to Agent Runtime
```

## Deployment Model

Agent-Memory is being positioned as an independent subsystem, not an OpenClaw-internal memory file bundle.

For `v1.0.0`, the intended layers are:

- `memory.py`: core storage, retrieval, learning, and governance logic
- `openclaw_integration.py`: OpenClaw lifecycle adapter
- CLI surface: standalone invocation boundary for non-import-based usage
- OpenClaw runtime: external caller that consumes the adapter or CLI contract

## Core Modules

### 1. Experience Logger

Records all agent behavior:

```json
{
  "timestamp": "2026-03-09T14:00:00+08:00",
  "type": "user_feedback",
  "goal": "Generate image",
  "context": {"task": "content_creation"},
  "action": "Used emoji in image",
  "outcome": "Rendering broken",
  "feedback": "Don't use emoji"
}
```

### 2. Learning Engine

Three subsystems:

- **Pattern Extraction**: Identify recurring patterns from events
- **Failure Analysis**: Analyze failures and generate error rules
- **Strategy Builder**: Convert experience into behavior strategies

### 3. Memory Governance

Controls memory quality:

- **Admission**: What enters long-term memory?
- **Weight**: How important is each strategy?
- **Decay**: Reduce weight over time
- **Merge**: Combine similar strategies

### 4. Memory Store

Three types:

- **Knowledge Memory** (Semantic): Facts and knowledge
- **Error Memory**: Mistakes to avoid
- **Procedural Memory** (Strategies): How to behave

Current OpenClaw-facing implementation stores and retrieves:

- **Task Strategies**: `condition -> action`
- **User Preferences**: communication/workflow preferences
- **Error Rules**: `trigger -> prevention`

### 5. Retrieval Engine

Find relevant strategies:

- Semantic similarity matching
- Weight-based ranking
- Context relevance scoring

Current implementation note:

- Retrieval is lightweight keyword/context scoring
- OpenClaw can consume the result through `build_openclaw_brief()` or `render_openclaw_memory()`
- The recommended runtime hook layer is `openclaw_integration.py`

## Data Structures

### Event

```json
{
  "timestamp": "ISO8601",
  "type": "user_feedback | error | task_complete | new_pattern",
  "goal": "string",
  "context": {"key": "value"},
  "action": "string",
  "outcome": "success | failure | partial",
  "feedback": "string (optional)"
}
```

### Strategy

```yaml
- id: strategy-001
  condition: "When generating images"
  action: "Don't use emoji, use text instead"
  weight: 0.95
  source: "user_feedback"
  created: "2026-03-09"
  context: ["content_creation"]
```

### User Preference

```yaml
- id: preference-001
  category: "communication_style"
  preference: "Be concise, avoid mechanical responses"
  weight: 0.9
  evidence: "User prefers direct communication"
  created: "2026-03-09"
  context: ["chat"]
```

### Error Rule

```yaml
- id: rule-001
  trigger: "Using emoji in generated images"
  root_cause: "Renderer fails on emoji glyphs"
  prevention: "Use plain text labels instead of emoji"
  weight: 0.95
  created: "2026-03-09"
  context: ["image_generation"]
```

## Hard Limits

Ensure system stability:

```yaml
events:
  max_size_mb: 10
  max_count: 1000
  retention_days: 7

strategies:
  max_count: 100
  max_size_kb: 50
```

## Governance Rules

### Admission

Only meaningful events enter the system:

```yaml
allowed_types:
  - user_feedback      # Explicit user feedback
  - error              # System errors
  - task_complete      # Completed tasks
  - new_pattern        # New pattern discovered
  - strategy_success   # Strategy validation
  - strategy_failure   # Strategy failure
```

### Weight Decay

Strategies lose weight over time if not used:

```yaml
decay:
  enabled: true
  daily_rate: 0.05  # 5% per day
  min_weight: 0.3   # Minimum threshold
```

### High-Value Archival

Design decision: **Archive events that generated strategies**

- Regular events: Delete after 7 days
- Events that generated strategies: Archive permanently
- Benefit: Can relearn from archive if strategy is wrong

## Maturity Levels

### Level 1: Memory Agent
- Store conversations in vector DB
- No learning capability

### Level 2: Pattern Agent
- Extract patterns from events
- Recognize user preferences

### Level 3: Self-Evolving Agent
- Learn strategies from experience
- Update behavior based on feedback
- Continuously improve

**Current Implementation: Level 2 → Level 3 transition**

## Integration with OpenClaw

```
OpenClaw Agent
     │
     ├─→ Session Start
     │      └─→ OpenClaw adapter or CLI
     │
     ├─→ Task Complete
     │      └─→ standalone Agent-Memory call
     │
     ├─→ User Feedback
     │      └─→ standalone Agent-Memory call
     │             ├─→ strategy
     │             ├─→ preference
     │             └─→ rule
     │
     └─→ Heartbeat (scheduled)
            └─→ Governance: decay, cleanup, archive
```

For `v1.0.0`, the preferred integration order is:

1. OpenClaw calls the Python adapter directly if both live in the same environment.
2. Otherwise, OpenClaw calls the future CLI surface with structured payloads.
3. HTTP/service deployment remains post-`v1.0.0`.

## Future Work

- Automatic pattern extraction
- Cross-agent strategy sharing
- Web UI for memory management
- LLM-powered strategy generation
