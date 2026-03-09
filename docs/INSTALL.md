# Installation Guide

## Prerequisites

- Python 3.8+
- PyYAML: `pip install pyyaml`

## Quick Install

```bash
# Clone the repository
git clone https://github.com/leapx-ai/Agent-Memory.git

# Install dependencies
cd Agent-Memory
pip install pyyaml

# Initialize memory system
mkdir -p ~/.openclaw/memory-system/{events,strategies}

# Copy example files (optional)
cp examples/*.yaml ~/.openclaw/memory-system/strategies/

# Copy core module
cp memory.py ~/.openclaw/memory-system/
cp governance.yaml ~/.openclaw/memory-system/
```

## Integration with OpenClaw

Add to your `AGENTS.md`:

```markdown
## Every Session

Before doing anything else:
1. Read strategies from `~/.openclaw/memory-system/strategies/`
2. Apply relevant strategies to current task
```

## Usage in Python

```python
import sys
sys.path.append('/path/to/Agent-Memory')

from memory import retrieve_strategies, log_event, learn_immediately

# Retrieve strategies before task
strategies = retrieve_strategies({"task": "your_task"})

# Log event after task
log_event(
    type="task_complete",
    goal="Your goal",
    context={"key": "value"},
    action="What you did",
    outcome="success",
    feedback="Optional user feedback"
)
```

## Directory Structure After Installation

```
~/.openclaw/memory-system/
├── events/                    # Events will be stored here
├── strategies/
│   ├── task-strategies.yaml
│   ├── user-preferences.yaml
│   └── error-rules.yaml
├── governance.yaml
├── index.json                 # Auto-generated
├── status.json                # Auto-generated
└── memory.py
```