import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import List, Optional


REPO_ROOT = Path(__file__).resolve().parents[1]


class AgentMemoryCliTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="agent-memory-cli-tests-", dir="/tmp"))
        self.memory_home = self.temp_dir / "memory-home"
        self.stub_dir = self.temp_dir / "stubs"
        self.stub_dir.mkdir(parents=True, exist_ok=True)
        (self.stub_dir / "yaml.py").write_text(
            (
                "import json\n"
                "class YAMLError(Exception):\n"
                "    pass\n"
                "def safe_load(stream):\n"
                "    text = stream.read()\n"
                "    if not text.strip():\n"
                "        return None\n"
                "    return json.loads(text)\n"
                "def safe_dump(data, stream, allow_unicode=True, sort_keys=False):\n"
                "    json.dump(data, stream, ensure_ascii=not allow_unicode, indent=2, sort_keys=sort_keys)\n"
            ),
            encoding="utf-8",
        )

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_cli_task_complete_and_session_start(self):
        feedback_payload = {
            "goal": "Generate images",
            "context": {"task": "image_generation", "workspace": "openclaw"},
            "action": "Used emoji",
            "feedback": "Don't use emoji, use text instead",
        }
        preference_payload = {
            "goal": "Respond to the user",
            "context": {"surface": "chat", "workspace": "openclaw"},
            "action": "Sent a verbose answer",
            "feedback": "Be concise",
            "memory_type": "preference",
            "category": "communication_style",
        }
        error_payload = {
            "goal": "Generate image",
            "context": {"task": "image_generation", "workspace": "openclaw"},
            "action": "Used emoji in image label",
            "outcome": "renderer_failed",
            "prevention": "Use plain text labels instead of emoji",
            "root_cause": "Renderer fails on emoji glyphs",
        }
        task_payload = {
            "goal": "Publish content",
            "context": {"task": "content_publishing", "workspace": "openclaw"},
            "action": "Used API to publish",
            "outcome": "success",
        }
        session_payload = {
            "context": {"task": "image_generation", "workspace": "openclaw", "surface": "chat"},
            "limit_per_type": 3,
        }

        self.run_cli("user-feedback", feedback_payload)
        self.run_cli("user-feedback", preference_payload)
        self.run_cli("record-error", error_payload)
        task_output = self.run_cli("task-complete", task_payload)
        session_output = self.run_cli("session-start", session_payload)
        prompt_only = self.run_cli(
            "session-start",
            session_payload,
            extra_args=["--prompt-only"],
            parse_json=False,
        )

        self.assertEqual(task_output["event"]["type"], "task_complete")
        self.assertIn("brief", session_output)
        self.assertIn("decision_brief", session_output)
        self.assertIn("prompt_block", session_output)
        self.assertIn("### Priority Preferences", session_output["prompt_block"])
        self.assertIn("### Relevant Strategies", session_output["prompt_block"])
        self.assertIn("### Risk Alerts", session_output["prompt_block"])
        self.assertIn("### Strategies", session_output["prompt_block"])
        self.assertIn("### User Preferences", session_output["prompt_block"])
        self.assertIn("### Error Rules", session_output["prompt_block"])
        self.assertIn("## Decision Brief", prompt_only)
        self.assertIn("## Relevant Memory", prompt_only)

        event_files = list((self.memory_home / "events").glob("*.jsonl"))
        self.assertEqual(len(event_files), 1)

    def test_cli_reads_stdin_and_returns_preference_memory_type(self):
        payload = {
            "goal": "Respond to the user",
            "context": {"surface": "chat", "workspace": "openclaw"},
            "action": "Sent a verbose answer",
            "feedback": "Be concise",
            "memory_type": "preference",
            "category": "communication_style",
        }
        output = self.run_cli("user-feedback", payload, use_stdin=True)
        self.assertEqual(output["memory_type"], "preference")
        self.assertEqual(output["memory_item"]["category"], "communication_style")

    def test_cli_requires_valid_payload(self):
        result = subprocess.run(
            self.base_command(["task-complete"]),
            input='{"goal":"Only goal"}',
            text=True,
            capture_output=True,
            env=self.cli_env(),
            cwd=REPO_ROOT,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Field 'context' is required", result.stderr)

    def test_cli_publish_memory_creates_host_files(self):
        feedback_payload = {
            "goal": "Generate images",
            "context": {"task": "image_generation", "workspace": "openclaw"},
            "action": "Used emoji",
            "feedback": "Don't use emoji, use text instead",
        }
        preference_payload = {
            "goal": "Respond to the user",
            "context": {"surface": "chat", "workspace": "openclaw"},
            "action": "Sent a verbose answer",
            "feedback": "Be concise",
            "memory_type": "preference",
            "category": "communication_style",
        }
        target_root = self.temp_dir / "workspace"
        publish_payload = {
            "context": {"task": "image_generation", "workspace": "openclaw", "surface": "chat"},
            "target_path": str(target_root),
        }

        self.run_cli("user-feedback", feedback_payload)
        self.run_cli("user-feedback", preference_payload)
        publish_output = self.run_cli("publish-memory", publish_payload)

        self.assertTrue(Path(publish_output["memory_file"]).exists())
        self.assertTrue(Path(publish_output["daily_file"]).exists())
        self.assertIn("decision_brief", publish_output)

    def run_cli(
        self,
        command: str,
        payload: dict,
        extra_args: Optional[List[str]] = None,
        use_stdin: bool = False,
        parse_json: bool = True,
    ):
        args = [command]
        if extra_args:
            args.extend(extra_args)

        input_path = self.temp_dir / f"{command}.json"
        input_path.write_text(json.dumps(payload), encoding="utf-8")

        if use_stdin:
            result = subprocess.run(
                self.base_command(args),
                input=json.dumps(payload),
                text=True,
                capture_output=True,
                env=self.cli_env(),
                cwd=REPO_ROOT,
                check=True,
            )
        else:
            result = subprocess.run(
                self.base_command(args + ["--input", str(input_path)]),
                text=True,
                capture_output=True,
                env=self.cli_env(),
                cwd=REPO_ROOT,
                check=True,
            )

        if parse_json:
            return json.loads(result.stdout)
        return result.stdout

    def base_command(self, args):
        return [
            "python3",
            str(REPO_ROOT / "agent_memory_cli.py"),
            "--home",
            str(self.memory_home),
            *args,
        ]

    def cli_env(self):
        env = os.environ.copy()
        repo_pythonpath = str(REPO_ROOT)
        existing = env.get("PYTHONPATH")
        paths = [str(self.stub_dir), repo_pythonpath]
        if existing:
            paths.append(existing)
        env["PYTHONPATH"] = os.pathsep.join(paths)
        return env


if __name__ == "__main__":
    unittest.main()
