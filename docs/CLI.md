# CLI Contract

Agent-Memory `v1.0.0` ships a standalone CLI so external runtimes can call the system without importing Python modules directly.

The CLI keeps the original OpenClaw-era command names for compatibility, but the preferred runtime-neutral entry points are now:

- `runtime-start` as the preferred alias for `session-start`
- `publish-host-memory` as the preferred alias for `publish-memory`

## Entry Point

```bash
python3 agent_memory_cli.py --help
```

Optional storage override:

```bash
python3 agent_memory_cli.py --home /tmp/agent-memory runtime-start --json '{"context":{"task":"example"}}'
```

## Commands

### `runtime-start` / `session-start`

Build a session-start or task-preflight payload.

Input:

```json
{
  "context": {
    "task": "incident_triage",
    "workspace": "support-bot",
    "surface": "chat"
  },
  "limit_per_type": 3
}
```

Example:

```bash
python3 agent_memory_cli.py runtime-start --input context.json
```

Output:

- `context`
- `brief`
- `decision_brief`
- `prompt_block`

Use `--prompt-only` if the runtime only needs the rendered Markdown block.

### `task-complete`

Record a completed task event.

Input:

```json
{
  "goal": "Publish content",
  "context": {
    "task": "incident_triage",
    "workspace": "support-bot"
  },
  "action": "Reviewed error logs and drafted next steps",
  "outcome": "success",
  "feedback": "Optional note"
}
```

Example:

```bash
python3 agent_memory_cli.py task-complete --input event.json
```

### `user-feedback`

Record direct user feedback and learn immediately.

Input:

```json
{
  "goal": "Respond to the user",
  "context": {
    "surface": "chat",
    "workspace": "support-bot"
  },
  "action": "Sent a verbose answer",
  "feedback": "Be concise",
  "memory_type": "preference",
  "category": "communication_style"
}
```

Example:

```bash
python3 agent_memory_cli.py user-feedback --input feedback.json
```

### `record-error`

Record an error and optionally turn it into an error rule.

Input:

```json
{
  "goal": "Generate image",
  "context": {
    "task": "incident_triage",
    "workspace": "support-bot"
  },
  "action": "Skipped local logs and guessed the root cause",
  "outcome": "misdiagnosis",
  "prevention": "Check local logs before proposing a root cause",
  "root_cause": "The diagnosis was made without checking the available evidence"
}
```

Example:

```bash
python3 agent_memory_cli.py record-error --input error.json
```

### `publish-host-memory` / `publish-memory`

Publish governed memory into host memory files.

Input:

```json
{
  "context": {
    "task": "incident_triage",
    "workspace": "support-bot",
    "surface": "chat"
  },
  "target_path": "/tmp/support-bot-workspace",
  "limit_per_type": 3,
  "mode": "incremental"
}
```

Example:

```bash
python3 agent_memory_cli.py publish-host-memory --input publish.json
```

Output:

- `target_root`
- `memory_file`
- `daily_file`
- `published`
- `decision_brief`

## Input Rules

- All commands accept exactly one input source:
  - `--input path/to/file.json`
  - `--json '{"...": "..."}'`
  - stdin
- Top-level input must always be a JSON object.
- Errors are returned as CLI usage failures with non-zero exit codes.

## Output Rules

- Default output is JSON to stdout.
- `runtime-start --prompt-only` and `session-start --prompt-only` output plain text Markdown.
- The CLI is designed for automation, so stdout is reserved for machine-readable results.
