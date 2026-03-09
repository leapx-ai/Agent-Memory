# Installation Guide

Release status:

- Current state: `v1.0.0`
- Release meaning: standalone memory governance system callable by OpenClaw

## Prerequisites

- Python 3.8+
- PyYAML

## Quick Install

```bash
# Clone the repository
git clone https://github.com/leapx-ai/Agent-Memory.git

# Install dependencies
cd Agent-Memory
pip install -r requirements.txt

# Optional: use a temporary storage path for local development
export AGENT_MEMORY_HOME=/tmp/agent-memory

# The first run bootstraps the directory structure automatically
python3 memory.py

# Inspect the standalone CLI surface
python3 agent_memory_cli.py --help
```

The standalone CLI is part of `v1.0.0` and is the recommended portability surface when OpenClaw should call Agent-Memory as an external dependency.

## Integration with OpenClaw

Add to your `AGENTS.md`:

```markdown
## Every Session

Before doing anything else:
1. Create an `OpenClawMemoryAdapter`
2. Call `adapter.session_start({...current task context...})`
3. Apply returned strategies, user preferences, and error rules
4. After the task, call `adapter.task_complete(...)`
5. If the user gives direct corrective feedback, call `adapter.user_feedback(...)`
```

## Usage in Python

```python
import sys
sys.path.append('/path/to/Agent-Memory')

from openclaw_integration import OpenClawMemoryAdapter

adapter = OpenClawMemoryAdapter()

# Build a prompt-ready memory block before task execution
payload = adapter.session_start({
    "task": "your_task",
    "workspace": "your_workspace",
})
print(payload["prompt_block"])

# Log event after task
adapter.task_complete(
    goal="Your goal",
    context={"key": "value"},
    action="What you did",
    outcome="success",
    feedback="Optional user feedback"
)

# Turn explicit feedback into long-term memory
adapter.user_feedback(
    goal="Respond to the user",
    context={"surface": "chat"},
    action="Sent a verbose answer",
    feedback="Be concise",
    memory_type="preference",
    category="communication_style",
)
```

## Usage via CLI

```bash
python3 agent_memory_cli.py session-start --json '{
  "context": {
    "task": "your_task",
    "workspace": "your_workspace"
  }
}'
```

See [CLI.md](./CLI.md) for the full standalone contract.

If you want the default persistent location, omit `AGENT_MEMORY_HOME` and the system will use `~/.openclaw/memory-system/`.

## Testing

```bash
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

## Directory Structure After Installation

```
~/.openclaw/memory-system/
├── events/                    # Events will be stored here
├── strategies/
│   ├── task-strategies.yaml
│   ├── user-preferences.yaml
│   └── error-rules.yaml
├── governance.yaml            # Auto-generated on first run if missing
├── index.json                 # Auto-generated
├── status.json                # Auto-generated
└── memory.py                  # Your imported module
```
