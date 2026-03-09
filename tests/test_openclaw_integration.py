import importlib
import json
import shutil
import sys
import tempfile
import types
import unittest
from pathlib import Path


def install_yaml_stub():
    """Install a minimal yaml stub so tests do not depend on external packages."""
    yaml = types.ModuleType("yaml")

    class YAMLError(Exception):
        pass

    def safe_load(stream):
        text = stream.read()
        if not text.strip():
            return None
        return json.loads(text)

    def safe_dump(data, stream, allow_unicode=True, sort_keys=False):
        json.dump(data, stream, ensure_ascii=not allow_unicode, indent=2, sort_keys=sort_keys)

    yaml.safe_load = safe_load
    yaml.safe_dump = safe_dump
    yaml.YAMLError = YAMLError
    sys.modules["yaml"] = yaml


def load_modules():
    """Reload local modules against the yaml stub."""
    install_yaml_stub()
    for module_name in ("memory", "openclaw_integration"):
        sys.modules.pop(module_name, None)

    memory = importlib.import_module("memory")
    integration = importlib.import_module("openclaw_integration")
    return memory, integration


class OpenClawIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.memory_module, self.integration_module = load_modules()
        self.temp_dir = Path(tempfile.mkdtemp(prefix="agent-memory-tests-", dir="/tmp"))
        self.memory_system = self.memory_module.MemorySystem(base_path=self.temp_dir)
        self.adapter = self.integration_module.OpenClawMemoryAdapter(
            memory_system=self.memory_system,
            limit_per_type=3,
        )

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_task_complete_logs_event(self):
        event = self.adapter.task_complete(
            goal="Publish content",
            context={"task": "content_publishing", "workspace": "openclaw"},
            action="Used API to publish",
            outcome="success",
        )

        self.assertIsNotNone(event)
        event_files = list((self.temp_dir / "events").glob("*.jsonl"))
        self.assertEqual(len(event_files), 1)
        lines = event_files[0].read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 1)
        self.assertEqual(json.loads(lines[0])["type"], "task_complete")

    def test_user_feedback_can_create_preference_memory(self):
        result = self.adapter.user_feedback(
            goal="Respond to the user",
            context={"surface": "chat", "workspace": "openclaw"},
            action="Sent a verbose answer",
            feedback="Be concise, avoid mechanical responses",
            memory_type="preference",
            category="communication_style",
            evidence="User asked for concise replies",
        )

        self.assertIsNotNone(result["event"])
        self.assertEqual(result["memory_type"], "preference")

        preferences = self.memory_system.retrieve_preferences(
            {"surface": "chat", "workspace": "openclaw"}
        )
        self.assertEqual(len(preferences), 1)
        self.assertEqual(preferences[0]["category"], "communication_style")
        self.assertIn("concise", preferences[0]["preference"].lower())

    def test_record_error_can_create_rule_memory(self):
        result = self.adapter.record_error(
            goal="Generate image",
            context={"task": "image_generation", "workspace": "openclaw"},
            action="Used emoji in image label",
            outcome="renderer_failed",
            feedback="Emoji caused rendering failure",
            prevention="Use plain text labels instead of emoji",
            root_cause="Renderer fails on emoji glyphs",
        )

        self.assertIsNotNone(result["event"])
        self.assertIsNotNone(result["memory_item"])

        rules = self.memory_system.retrieve_error_rules(
            {"task": "image_generation", "workspace": "openclaw"}
        )
        self.assertEqual(len(rules), 1)
        self.assertIn("emoji", rules[0]["trigger"].lower())
        self.assertIn("plain text", rules[0]["prevention"].lower())

    def test_session_start_renders_all_memory_types(self):
        self.adapter.user_feedback(
            goal="Generate images",
            context={"task": "image_generation", "workspace": "openclaw"},
            action="Used emoji in image label",
            feedback="Don't use emoji, use text instead",
        )
        self.adapter.user_feedback(
            goal="Respond to the user",
            context={"surface": "chat", "workspace": "openclaw"},
            action="Sent a verbose answer",
            feedback="Be concise",
            memory_type="preference",
            category="communication_style",
        )
        self.adapter.record_error(
            goal="Generate image",
            context={"task": "image_generation", "workspace": "openclaw"},
            action="Used emoji in image label",
            outcome="renderer_failed",
            prevention="Use plain text labels instead of emoji",
            root_cause="Renderer fails on emoji glyphs",
        )

        payload = self.adapter.session_start(
            {"task": "image_generation", "workspace": "openclaw", "surface": "chat"}
        )

        self.assertIn("brief", payload)
        self.assertIn("prompt_block", payload)
        self.assertIn("## Relevant Memory", payload["prompt_block"])
        self.assertIn("### Strategies", payload["prompt_block"])
        self.assertIn("### User Preferences", payload["prompt_block"])
        self.assertIn("### Error Rules", payload["prompt_block"])
        self.assertGreaterEqual(len(payload["brief"]["summary"]), 3)


if __name__ == "__main__":
    unittest.main()
