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
    for module_name in ("memory", "decision_layer", "metrics_layer"):
        sys.modules.pop(module_name, None)
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

    def test_builds_structured_decision_brief(self):
        self.memory_system.learn_immediately(
            {
                "type": "user_feedback",
                "goal": "Generate images",
                "context": {"task": "image_generation", "workspace": "openclaw"},
                "feedback": "Don't use emoji, use text instead",
            }
        )
        self.memory_system.learn_immediately(
            {
                "type": "user_feedback",
                "goal": "Respond to the user",
                "context": {"surface": "chat", "workspace": "openclaw"},
                "feedback": "Be concise",
                "memory_type": "preference",
                "category": "communication_style",
            }
        )
        self.memory_system.learn_immediately(
            {
                "type": "error",
                "goal": "Generate image",
                "context": {"task": "image_generation", "workspace": "openclaw"},
                "action": "Used emoji in image label",
                "feedback": "Use plain text labels instead of emoji",
                "prevention": "Use plain text labels instead of emoji",
                "root_cause": "Renderer fails on emoji glyphs",
                "memory_type": "rule",
            }
        )

        brief = self.memory_system.build_decision_brief(
            {"task": "image_generation", "workspace": "openclaw", "surface": "chat"}
        )

        self.assertIn("priority_preferences", brief)
        self.assertIn("relevant_strategies", brief)
        self.assertIn("risk_alerts", brief)
        self.assertIn("current_focus", brief)
        self.assertTrue(any("concise" in line.lower() for line in brief["priority_preferences"]))
        self.assertTrue(any("emoji" in line.lower() for line in brief["relevant_strategies"]))
        self.assertTrue(any("avoid" in line.lower() for line in brief["risk_alerts"]))
        self.assertTrue(any("image_generation" in line for line in brief["current_focus"]))

    def test_publish_openclaw_memory_writes_memory_files(self):
        self.memory_system.learn_immediately(
            {
                "type": "user_feedback",
                "goal": "Generate images",
                "context": {"task": "image_generation", "workspace": "openclaw"},
                "feedback": "Don't use emoji, use text instead",
            }
        )
        self.memory_system.learn_immediately(
            {
                "type": "user_feedback",
                "goal": "Respond to the user",
                "context": {"surface": "chat", "workspace": "openclaw"},
                "feedback": "Be concise",
                "memory_type": "preference",
                "category": "communication_style",
            }
        )
        self.memory_system.learn_immediately(
            {
                "type": "error",
                "goal": "Generate image",
                "context": {"task": "image_generation", "workspace": "openclaw"},
                "action": "Used emoji in image label",
                "feedback": "Use plain text labels instead of emoji",
                "prevention": "Use plain text labels instead of emoji",
                "root_cause": "Renderer fails on emoji glyphs",
                "memory_type": "rule",
            }
        )

        target_root = self.temp_dir / "workspace-memory"
        result = self.memory_system.publish_openclaw_memory(
            target_root=target_root,
            context={"task": "image_generation", "workspace": "openclaw", "surface": "chat"},
        )

        memory_file = Path(result["memory_file"])
        daily_file = Path(result["daily_file"])
        self.assertTrue(memory_file.exists())
        self.assertTrue(daily_file.exists())
        self.assertIn("OpenClaw Memory Projection", memory_file.read_text(encoding="utf-8"))
        self.assertIn("User Preferences", memory_file.read_text(encoding="utf-8"))
        self.assertIn("Daily Memory Projection", daily_file.read_text(encoding="utf-8"))
        self.assertIn("Task Decision Brief", daily_file.read_text(encoding="utf-8"))

    def test_generic_runtime_aliases_match_openclaw_aliases(self):
        self.memory_system.learn_immediately(
            {
                "type": "user_feedback",
                "goal": "Generate images",
                "context": {"task": "image_generation", "workspace": "openclaw"},
                "feedback": "Don't use emoji, use text instead",
            }
        )
        context = {"task": "image_generation", "workspace": "openclaw"}

        openclaw_brief = self.memory_system.build_openclaw_brief(context)
        runtime_brief = self.memory_system.build_runtime_brief(context)
        self.assertEqual(runtime_brief["summary"], openclaw_brief["summary"])
        self.assertEqual(runtime_brief["decision_brief"], openclaw_brief["decision_brief"])

        self.assertEqual(
            self.memory_system.render_runtime_memory(context),
            self.memory_system.render_openclaw_memory(context),
        )

        target_root = self.temp_dir / "workspace-host"
        runtime_publish = self.memory_system.publish_host_memory(
            target_root=target_root,
            context=context,
        )
        openclaw_publish = self.memory_system.publish_openclaw_memory(
            target_root=target_root,
            context=context,
        )
        self.assertEqual(runtime_publish["decision_brief"], openclaw_publish["decision_brief"])
        self.assertEqual(runtime_publish["published"], openclaw_publish["published"])

    def test_report_metrics_aggregates_run_outcomes(self):
        self.memory_system.learn_immediately(
            {
                "type": "user_feedback",
                "goal": "Respond to the user",
                "context": {"task": "incident_triage", "workspace": "support-bot", "surface": "chat"},
                "feedback": "Be concise",
                "memory_type": "preference",
                "category": "communication_style",
            }
        )
        context = {"task": "incident_triage", "workspace": "support-bot", "surface": "chat"}
        brief = self.memory_system.build_runtime_brief(context)
        manifest = self.memory_system.start_run_metrics(
            context=context,
            brief=brief,
            decision_brief=brief["decision_brief"],
        )

        task_event = self.memory_system.log_event(
            type="task_complete",
            goal="Handle incident",
            context=context,
            action="Sent a concise reply",
            outcome="success",
        )
        feedback_event = self.memory_system.log_event(
            type="user_feedback",
            goal="Handle incident",
            context=context,
            action="Sent a concise reply",
            outcome="feedback_received",
            feedback="Be even more direct",
        )
        self.memory_system.record_task_complete_metrics(manifest["trace_id"], task_event)
        self.memory_system.record_user_feedback_metrics(manifest["trace_id"], feedback_event)

        report = self.memory_system.report_metrics(window_days=7)

        self.assertEqual(report["total_runs"], 1)
        self.assertEqual(report["by_memory_type"]["preference"]["exposed_runs"], 1)
        self.assertEqual(report["by_memory_type"]["preference"]["correction_rate"], 1.0)
        self.assertIn("summary", report)
        self.assertIn("headline_verdict", report["summary"])

    def test_metrics_assessment_links_high_leverage_workflow_feedback(self):
        strategy = self.memory_system.learn_immediately(
            {
                "type": "user_feedback",
                "goal": "Investigate incident",
                "context": {"task": "incident_triage", "workspace": "support-bot", "surface": "chat"},
                "action": "Skipped logs",
                "feedback": "Check local logs before proposing a root cause",
            }
        )
        preference = self.memory_system.learn_immediately(
            {
                "type": "user_feedback",
                "goal": "Respond to the user",
                "context": {"task": "incident_triage", "workspace": "support-bot", "surface": "chat"},
                "feedback": "Be concise",
                "memory_type": "preference",
                "category": "communication_style",
            }
        )

        context = {"task": "incident_triage", "workspace": "support-bot", "surface": "chat"}
        brief = self.memory_system.build_runtime_brief(context)
        manifest = self.memory_system.start_run_metrics(
            context=context,
            brief=brief,
            decision_brief=brief["decision_brief"],
        )
        feedback_event = self.memory_system.log_event(
            type="user_feedback",
            goal="Investigate incident",
            context=context,
            action="Guessed the cause without checking logs",
            outcome="feedback_received",
            feedback="Don't guess. Read the logs first.",
        )
        self.memory_system.record_user_feedback_metrics(manifest["trace_id"], feedback_event)
        assessments = self.memory_system.get_metric_assessments(manifest["trace_id"])
        by_memory_id = {item["memory_id"]: item for item in assessments}

        self.assertEqual(by_memory_id[strategy["id"]]["status"], "likely_contradicted")
        self.assertEqual(by_memory_id[preference["id"]]["status"], "unresolved")

        report = self.memory_system.report_metrics(window_days=7)
        self.assertEqual(report["summary"]["linked_contradictions"], 1)
        self.assertEqual(
            report["summary"]["top_contradicted_items"][0]["memory_id"],
            strategy["id"],
        )
        self.assertTrue(report["summary"]["top_watchouts"])

    def test_report_metrics_includes_bucket_comparison(self):
        support_context = {
            "task": "incident_triage",
            "workspace": "support-bot",
            "surface": "chat",
        }
        blog_context = {
            "task": "content_publishing",
            "workspace": "blog",
            "surface": "chat",
        }

        for context, outcome in ((support_context, "success"), (blog_context, "failure")):
            brief = self.memory_system.build_runtime_brief(context)
            manifest = self.memory_system.start_run_metrics(
                context=context,
                brief=brief,
                decision_brief=brief["decision_brief"],
            )
            event = self.memory_system.log_event(
                type="task_complete",
                goal="Do work",
                context=context,
                action="Handled task",
                outcome=outcome,
            )
            self.memory_system.record_task_complete_metrics(manifest["trace_id"], event)

        report = self.memory_system.report_metrics(window_days=7, top_buckets=5)
        text_report = self.memory_system.render_metrics_report(window_days=7, top_buckets=5)

        self.assertEqual(len(report["by_bucket"]), 2)
        self.assertEqual(
            report["summary"]["healthiest_bucket"]["bucket"],
            "incident_triage|support-bot|chat",
        )
        self.assertIn("Bucket Comparison", text_report)
        self.assertIn("incident_triage|support-bot|chat", text_report)
        self.assertIn("Verdict:", text_report)


if __name__ == "__main__":
    unittest.main()
