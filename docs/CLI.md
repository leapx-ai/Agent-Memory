# CLI Contract

Agent-Memory `v1.0.0` ships a standalone CLI so OpenClaw can call the system without importing Python modules directly.

## Entry Point

```bash
python3 agent_memory_cli.py --help
```

Optional storage override:

```bash
python3 agent_memory_cli.py --home /tmp/agent-memory session-start --json '{"context":{"task":"example"}}'
```

## Commands

### `session-start`

Build a session-start or task-preflight payload.

Input:

```json
{
  "context": {
    "task": "image_generation",
    "workspace": "openclaw",
    "surface": "chat"
  },
  "limit_per_type": 3
}
```

Example:

```bash
python3 agent_memory_cli.py session-start --input context.json
```

Output:

- `context`
- `brief`
- `prompt_block`

Use `--prompt-only` if OpenClaw only needs the rendered Markdown block.

### `task-complete`

Record a completed task event.

Input:

```json
{
  "goal": "Publish content",
  "context": {
    "task": "content_publishing",
    "workspace": "openclaw"
  },
  "action": "Used API to publish",
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
    "workspace": "openclaw"
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
    "task": "image_generation",
    "workspace": "openclaw"
  },
  "action": "Used emoji in image label",
  "outcome": "renderer_failed",
  "prevention": "Use plain text labels instead of emoji",
  "root_cause": "Renderer fails on emoji glyphs"
}
```

Example:

```bash
python3 agent_memory_cli.py record-error --input error.json
```

## Input Rules

- All commands accept exactly one input source:
  - `--input path/to/file.json`
  - `--json '{"...": "..."}'`
  - stdin
- Top-level input must always be a JSON object.
- Errors are returned as CLI usage failures with non-zero exit codes.

## Output Rules

- Default output is JSON to stdout.
- `session-start --prompt-only` outputs plain text Markdown.
- The CLI is designed for automation, so stdout is reserved for machine-readable results.
