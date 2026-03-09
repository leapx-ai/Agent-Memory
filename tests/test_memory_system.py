import importlib
import json
import shutil
import sys
import tempfile
import types
import unittest
from pathlib import Path


def install_yaml_stub():
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


def load_memory_module():
    install_yaml_stub()
    sys.modules.pop("memory", None)
    return importlib.import_module("memory")


class MemorySystemTests(unittest.TestCase):
    def setUp(self):
        self.memory_module = load_memory_module()
        self.temp_dir = Path(tempfile.mkdtemp(prefix="agent-memory-core-tests-", dir="/tmp"))
        self.memory_system = self.memory_module.MemorySystem(base_path=self.temp_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_bootstrap_creates_required_storage_files(self):
        expected_paths = [
            self.temp_dir / "events",
            self.temp_dir / "strategies",
            self.temp_dir / "archive",
            self.temp_dir / "governance.yaml",
            self.temp_dir / "index.json",
            self.temp_dir / "status.json",
            self.temp_dir / "strategies" / "task-strategies.yaml",
            self.temp_dir / "strategies" / "user-preferences.yaml",
            self.temp_dir / "strategies" / "error-rules.yaml",
        ]

        for path in expected_paths:
            self.assertTrue(path.exists(), str(path))

    def test_learning_updates_strategy_index(self):
        strategy = self.memory_system.learn_immediately(
            {
                "type": "user_feedback",
                "goal": "Generate images",
                "context": {"task": "image_generation"},
                "feedback": "Don't use emoji, use text instead",
            }
        )

        self.assertIsNotNone(strategy)
        index = json.loads((self.temp_dir / "index.json").read_text(encoding="utf-8"))
        self.assertIn("generate images", index["indexes"]["by_condition"])
        self.assertIn(strategy["id"], index["indexes"]["by_condition"]["generate images"])

    def test_cleanup_prunes_old_events_and_low_weight_memory(self):
        self.memory_system.governance["events"]["retention_days"] = 1
        self.memory_system.governance["events"]["max_count"] = 10
        self.memory_system.governance["events"]["max_size_mb"] = 10
        self.memory_system.governance["strategies"]["min_weight"] = 0.5
        self.memory_system.governance["strategies"]["max_count"] = 1
        self.memory_system.governance["strategies"]["max_size_kb"] = 50

        old_event_file = self.temp_dir / "events" / "2000-01-01.jsonl"
        old_event_file.write_text(
            json.dumps(
                {
                    "timestamp": "2000-01-01T00:00:00",
                    "type": "task_complete",
                    "goal": "Old task",
                    "context": {"task": "old"},
                    "action": "Did something old",
                    "outcome": "success",
                }
            )
            + "\n",
            encoding="utf-8",
        )

        self.memory_system._save_memory_item(
            "strategy",
            {
                "id": "strategy-low",
                "condition": "Low priority task",
                "action": "Ignore me",
                "weight": 0.1,
                "source": "test",
                "created": "2026-03-09",
                "context": ["test"],
            },
        )
        self.memory_system._save_memory_item(
            "strategy",
            {
                "id": "strategy-high-a",
                "condition": "High priority task A",
                "action": "Use approach A",
                "weight": 0.9,
                "source": "test",
                "created": "2026-03-09",
                "context": ["test"],
            },
        )
        self.memory_system._save_memory_item(
            "strategy",
            {
                "id": "strategy-high-b",
                "condition": "High priority task B",
                "action": "Use approach B",
                "weight": 0.8,
                "source": "test",
                "created": "2026-03-09",
                "context": ["test"],
            },
        )

        self.memory_system._run_cleanup()

        self.assertFalse(old_event_file.exists())
        strategies = self.memory_system.get_all_strategies()
        self.assertEqual(len(strategies), 1)
        self.assertEqual(strategies[0]["id"], "strategy-high-a")


if __name__ == "__main__":
    unittest.main()
