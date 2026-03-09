# Architecture Design Principles

This document outlines the core design principles and decisions for the Agent Memory System, with an emphasis on OpenClaw integration.

Release intent:

- Current state: `v1.0.0`
- `v1.0.0`: standalone memory governance system callable by OpenClaw

## Core Design Philosophy

### 1. Learning, Not Just Remembering

The key insight: **Self-Evolving Agent's core is not "having memory", but "changing behavior through experience".**

```
Traditional Memory: Store → Retrieve
Self-Evolving: Experience → Learn → Strategy → Behavior Change
```

### 2. High Compression, Low Storage

Events are raw data, strategies are compressed knowledge.

```
100 events → 1 strategy (100:1 compression ratio)
```

Memory system should maintain small size while preserving learning capability.

### 3. Safety First

Production systems must have hard limits. No single component should be able to grow unbounded.

```yaml
Hard Limits:
  events: 10MB / 1000 items / 7 days
  strategies: 50KB / 100 items
```

### 4. Data Sovereignty

Users should never lose the ability to relearn. Even if our learning algorithm has bugs.

- Never delete raw data that generated strategies
- Archive, don't delete
- Support relearning from archive

---

## Key Design Decisions

### Decision 1: High-Value Archival

**Problem**: If we delete events after learning, and the learned strategy is wrong, we cannot relearn.

**Decision**: Archive events that generated strategies.

```
Regular events:
  Retain 7 days → Delete

High-value events (generated strategies):
  Retain 7 days → Archive permanently
```

**Benefit**: Archive size ≈ strategies × event size, which is bounded.

### Decision 2: Strategy Lifecycle

**Problem**: When should strategies be created, updated, or removed?

**Decision**: Multiple trigger points:

| Trigger | Action | Implementation |
|---------|--------|----------------|
| User explicit feedback | Immediate learning | `learn_immediately()` |
| Task completion | Log event | `log_event()` |
| Pattern detected (3+ similar events) | Extract pattern | Async learning |
| Strategy succeeds | Boost weight | `update_weight(+0.1)` |
| Strategy fails | Penalize weight | `update_weight(-0.2)` |
| Weight below threshold | Remove strategy | Governance |

### Decision 3: Async Learning Architecture

**Problem**: Learning during task execution adds latency.

**Decision**: Learning runs asynchronously.

```
Real-time Agent:
  Execute task → Log event → Return result

Offline Learning (background):
  Read events → Extract patterns → Update strategies
```

This decouples execution from learning.

### Decision 4: Weight-Based Retrieval

**Problem**: With many strategies, how to find relevant ones?

**Decision**: Multi-factor retrieval scoring:

```
score = semantic_similarity × weight × context_relevance

Where:
  - semantic_similarity: How well condition matches
  - weight: How reliable this strategy has been
  - context_relevance: Current context match
```

### Decision 5: Graceful Degradation

**Problem**: What if memory system fails?

**Decision**: Agent should work without memory system.

```
Memory System:
  Available → Use strategies
  Unavailable → Continue without strategies (fallback)
  Error → Log and continue (no crash)
```

### Decision 6: Projection Layer Over Direct Dumping

**Problem**: Raw retrieval results are not the same thing as decision-ready guidance.

If Agent-Memory sends too much internal memory directly to OpenClaw, quality drops:

- host memory becomes noisy
- task-start context becomes bloated
- OpenClaw has to do too much second-order reasoning

**Decision**: Add a dedicated projection / decision layer between the core engine and OpenClaw-facing outputs.

This layer is responsible for:

- selecting which memory items deserve host visibility
- publishing stable items into OpenClaw host memory
- producing a compact Decision Brief for task start
- keeping publication and task-time packaging separate from source storage

Recommended internal components:

- selector / ranker
- publisher
- Decision Brief builder
- sync policy

This preserves the intended layering:

- core engine = learning and governance
- projection layer = packaging and delivery
- OpenClaw = runtime execution

See [DECISION_LAYER.md](./DECISION_LAYER.md) for the concrete design.

---

## Integration Architecture

### OpenClaw Integration

Recommended implementation surface: use `openclaw_integration.py` as the lifecycle adapter instead of calling low-level memory primitives directly from the runtime.

```
┌─────────────────────────────────────────────────────────┐
│                    OpenClaw Agent                        │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  Session Start (AGENTS.md)                              │
│       ↓                                                  │
│  Python adapter or standalone CLI                       │
│       ↓                                                  │
│  Decision Brief + host memory projection                │
│       ↓                                                  │
│  Apply strategies + preferences + error rules           │
│                                                          │
│  Task Complete                                          │
│       ↓                                                  │
│  standalone Agent-Memory call                           │
│                                                          │
│  User Feedback                                          │
│       ↓                                                  │
│  standalone Agent-Memory call                           │
│                                                          │
│  Heartbeat (scheduled)                                  │
│       ↓                                                  │
│  Governance: decay, cleanup, archive ← TODO v1.1.0     │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

### Release Progression

| Feature | v1.0.0 | v1.1.0 (Planned) |
|---------|--------|------------------|
| Python memory engine | ✅ Stable contract | ✅ |
| OpenClaw adapter | ✅ Stable contract | ✅ |
| Standalone CLI | ✅ | ✅ |
| Structured Decision Brief | ⚠️ Initial post-`v1.0.0` implementation | ✅ Hardened |
| Host memory publisher | ⚠️ Initial post-`v1.0.0` implementation | ✅ Hardened |
| Log events | ✅ Manual call | ✅ Auto after tasks |
| Learn strategies/preferences/rules from feedback | ✅ Manual call | ✅ Auto trigger |
| Weight decay | ❌ | ✅ Heartbeat job |
| Cleanup | ✅ Triggered during writes | ✅ Heartbeat job |
| Archive | ❌ | ✅ Heartbeat job |

---

## Extensibility Points

### 1. Learning Algorithms

Current: Simple rule-based learning

Future:
- LLM-powered strategy extraction
- Pattern mining algorithms
- Anomaly detection for failure analysis

### 2. Storage Backends

Current: File-based (YAML, JSONL)

Future:
- SQLite for better querying
- Vector DB for semantic search
- Cloud sync for cross-device

### 3. Strategy Formats

Current: YAML with fixed schema

Future:
- Versioned strategies
- Strategy templates
- Cross-agent strategy sharing

### 4. Governance Policies

Current: Fixed rules in governance.yaml

Future:
- Configurable policies
- A/B testing for strategies
- User-controlled retention

---

## Risks and Mitigations

### Risk 1: Wrong Strategy Learned

**Mitigation**: 
- Archive source events
- Weight-based confidence
- Support relearning from archive

### Risk 2: Storage Explosion

**Mitigation**:
- Hard limits enforced
- High-value archival (bounded growth)
- Automatic cleanup

### Risk 3: Performance Impact

**Mitigation**:
- Async learning
- Lazy loading strategies
- Indexed retrieval

### Risk 4: Memory Loss on System Failure

**Mitigation**:
- File-based persistence
- Git backup option
- Export/import functionality (planned)

---

## Future Roadmap

### v1.1.0 - Automation
- Automatic event logging after tasks
- Automatic learning triggers
- Heartbeat-based governance

### v1.2.0 - Intelligence
- LLM-powered strategy extraction
- Semantic strategy matching
- Pattern mining

### v1.3.0 - Collaboration
- Cross-agent strategy sharing
- Strategy marketplace
- Team memory systems

### v2.0.0 - Enterprise
- Web UI management
- Role-based access control
- Analytics dashboard
