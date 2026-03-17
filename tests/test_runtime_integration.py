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
    for module_name in ("memory", "decision_layer", "metrics_layer", "runtime_integration"):
        sys.modules.pop(module_name, None)

    memory = importlib.import_module("memory")
    integration = importlib.import_module("runtime_integration")
    return memory, integration


class RuntimeIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.memory_module, self.integration_module = load_modules()
        self.temp_dir = Path(tempfile.mkdtemp(prefix="agent-memory-runtime-tests-", dir="/tmp"))
        self.memory_system = self.memory_module.MemorySystem(base_path=self.temp_dir)
        self.adapter = self.integration_module.AgentMemoryAdapter(
            memory_system=self.memory_system,
            limit_per_type=3,
        )

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_session_start_returns_generic_runtime_payload(self):
        self.adapter.user_feedback(
            goal="Respond to the user",
            context={"surface": "chat", "workspace": "generic-runtime"},
            action="Sent a verbose answer",
            feedback="Be concise",
            memory_type="preference",
            category="communication_style",
        )

        payload = self.adapter.session_start(
            {"task": "reply", "workspace": "generic-runtime", "surface": "chat"}
        )

        self.assertIn("brief", payload)
        self.assertIn("decision_brief", payload)
        self.assertIn("prompt_block", payload)
        self.assertIn("trace_id", payload)
        self.assertIn("### Priority Preferences", payload["prompt_block"])
        self.assertIn("concise", payload["prompt_block"].lower())

    def test_metrics_report_tracks_run_level_outcomes(self):
        self.adapter.user_feedback(
            goal="Respond to the user",
            context={"task": "incident_triage", "workspace": "generic-runtime", "surface": "chat"},
            action="Sent a long answer",
            feedback="Be concise",
            memory_type="preference",
            category="communication_style",
        )
        start_payload = self.adapter.session_start(
            {"task": "incident_triage", "workspace": "generic-runtime", "surface": "chat"}
        )
        self.adapter.task_complete(
            goal="Handle incident",
            context={"task": "incident_triage", "workspace": "generic-runtime", "surface": "chat"},
            action="Proposed a concise answer",
            outcome="success",
        )
        self.adapter.user_feedback(
            goal="Handle incident",
            context={"task": "incident_triage", "workspace": "generic-runtime", "surface": "chat"},
            action="Sent a concise answer",
            feedback="Be even more direct",
            memory_type="preference",
            category="communication_style",
            trace_id=start_payload["trace_id"],
        )

        report = self.adapter.metrics_report(window_days=7)

        self.assertEqual(report["total_runs"], 1)
        self.assertGreater(report["by_memory_type"]["preference"]["exposed_runs"], 0)
        self.assertGreater(report["by_memory_type"]["preference"]["correction_rate"], 0.0)
        self.assertIn("summary", report)
        self.assertEqual(report["summary"]["most_exposed_type"]["type"], "preference")
        self.assertIn("headline_verdict", report["summary"])
        self.assertIn("top_watchouts", report["summary"])

    def test_generic_adapter_uses_generic_sources(self):
        result = self.adapter.user_feedback(
            goal="Respond to the user",
            context={"surface": "chat"},
            action="Sent a verbose answer",
            feedback="Be concise",
            memory_type="preference",
            category="communication_style",
        )

        self.assertEqual(result["memory_item"]["source"], "agent_feedback")

        error_result = self.adapter.record_error(
            goal="Generate image",
            context={"task": "image_generation"},
            action="Used emoji in image label",
            outcome="renderer_failed",
            prevention="Use plain text labels instead of emoji",
        )
        self.assertEqual(error_result["memory_item"]["source"], "agent_error")

    def test_phase_two_links_workflow_feedback_without_failing_unrelated_memory(self):
        strategy_result = self.adapter.user_feedback(
            goal="Investigate incident",
            context={"task": "incident_triage", "workspace": "generic-runtime", "surface": "chat"},
            action="Skipped local logs",
            feedback="Check local logs before proposing a root cause",
        )
        preference_result = self.adapter.user_feedback(
            goal="Respond to the user",
            context={"task": "incident_triage", "workspace": "generic-runtime", "surface": "chat"},
            action="Sent a long answer",
            feedback="Be concise",
            memory_type="preference",
            category="communication_style",
        )

        payload = self.adapter.session_start(
            {"task": "incident_triage", "workspace": "generic-runtime", "surface": "chat"}
        )
        result = self.adapter.user_feedback(
            goal="Investigate incident",
            context={"task": "incident_triage", "workspace": "generic-runtime", "surface": "chat"},
            action="Guessed the cause without checking logs",
            feedback="Don't guess. Read the logs first.",
            trace_id=payload["trace_id"],
        )

        assessments = {item["memory_id"]: item for item in result["assessments"]}
        self.assertEqual(
            assessments[strategy_result["memory_item"]["id"]]["status"],
            "likely_contradicted",
        )
        self.assertEqual(
            assessments[preference_result["memory_item"]["id"]]["status"],
            "unresolved",
        )

        text_report = self.adapter.render_metrics_report(window_days=7)
        self.assertIn("Agent-Memory Metrics Report", text_report)
        self.assertIn("Linked contradictions", text_report)
        self.assertIn("Verdict:", text_report)
        self.assertIn("Top Watchouts", text_report)


if __name__ == "__main__":
    unittest.main()
