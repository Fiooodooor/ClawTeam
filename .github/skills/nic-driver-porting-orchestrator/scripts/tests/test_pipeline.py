"""
Test suite for the NIC Driver Porting Orchestrator pipeline.

Tests import consistency, state management, checklist evaluation,
report generation, and backward compatibility without needing LLM access.
"""

import json
import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path

# Ensure the project root is on sys.path
PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, PROJECT_ROOT)


class TestStateModule(unittest.TestCase):
    """Tests for agent.pipeline.state"""

    def test_import_all_types(self):
        from agent.pipeline.state import (
            PipelineState, create_initial_state, SourceAnalysis,
            DirectoryLayout, APIMapping, PortingArtifact, SubstepResult,
            TestResult, RiskEntry, merge_dicts, merge_lists,
        )

    def test_create_initial_state_defaults(self):
        from agent.pipeline.state import create_initial_state
        state = create_initial_state("ixgbe")
        self.assertEqual(state["driver_name"], "ixgbe")
        self.assertEqual(state["target_os"], "freebsd")
        self.assertEqual(state["output_dir"], "./artifacts")
        self.assertEqual(state["source_dir"], "")
        self.assertEqual(state["native_score"], 0.0)
        self.assertEqual(state["portability_score"], 0.0)
        self.assertTrue(state["should_continue"])
        self.assertEqual(state["errors"], [])
        self.assertEqual(state["api_mappings"], [])
        self.assertEqual(state["substep_results"], [])
        self.assertEqual(state["porting_artifacts"], [])
        self.assertEqual(state["test_results"], [])
        self.assertEqual(state["risk_register"], [])
        self.assertEqual(state["final_checklist"], {})
        self.assertEqual(state["current_phase"], "init")

    def test_create_initial_state_custom(self):
        from agent.pipeline.state import create_initial_state
        conn = {"host": "10.0.0.5", "user": "root"}
        state = create_initial_state(
            driver_name="ice",
            target_os="windows",
            output_dir="/tmp/out",
            source_dir="/src/ice",
            connection_info=conn,
        )
        self.assertEqual(state["driver_name"], "ice")
        self.assertEqual(state["target_os"], "windows")
        self.assertEqual(state["output_dir"], "/tmp/out")
        self.assertEqual(state["source_dir"], "/src/ice")
        self.assertEqual(state["connection_info"], conn)

    def test_merge_dicts(self):
        from agent.pipeline.state import merge_dicts
        left = {"a": 1, "b": 2}
        right = {"b": 3, "c": 4}
        result = merge_dicts(left, right)
        self.assertEqual(result, {"a": 1, "b": 3, "c": 4})
        # Original left unchanged
        self.assertEqual(left, {"a": 1, "b": 2})

    def test_merge_lists(self):
        from agent.pipeline.state import merge_lists
        self.assertEqual(merge_lists([1, 2], [3, 4]), [1, 2, 3, 4])
        self.assertEqual(merge_lists([], [1]), [1])
        self.assertEqual(merge_lists([1], []), [1])


class TestSkillsModule(unittest.TestCase):
    """Tests for agent.skills"""

    def test_load_all_skills(self):
        from agent.skills import load_skill
        for name in ["source_analysis", "api_mapping", "tdd_writer",
                      "coder", "validation", "risk_auditor"]:
            content = load_skill(name)
            self.assertIsInstance(content, str)
            self.assertGreater(len(content), 50, f"Skill {name} too short")

    def test_load_skill_not_found(self):
        from agent.skills import load_skill
        with self.assertRaises(FileNotFoundError):
            load_skill("nonexistent_skill_xyz")

    def test_list_available_skills(self):
        from agent.skills import list_available_skills
        skills = list_available_skills()
        self.assertIsInstance(skills, list)
        self.assertGreaterEqual(len(skills), 6)
        for expected in ["source_analysis", "api_mapping", "tdd_writer",
                         "coder", "validation", "risk_auditor"]:
            self.assertIn(expected, skills)

    def test_convenience_functions(self):
        from agent.skills import (
            get_source_analysis_skills, get_api_mapping_skills,
            get_tdd_writer_skills, get_coder_skills,
            get_validation_skills, get_risk_auditor_skills,
        )
        for fn in [get_source_analysis_skills, get_api_mapping_skills,
                    get_tdd_writer_skills, get_coder_skills,
                    get_validation_skills, get_risk_auditor_skills]:
            content = fn()
            self.assertIsInstance(content, str)
            self.assertGreater(len(content), 50)

    def test_backward_compat_aliases(self):
        from agent.skills import get_data_collector_skills, get_fusioner_skills
        # These should work and return non-empty content
        self.assertGreater(len(get_data_collector_skills()), 50)
        self.assertGreater(len(get_fusioner_skills()), 50)


class TestBackwardCompatibility(unittest.TestCase):
    """Verify all backward-compatible aliases resolve correctly."""

    def test_pipeline_class_aliases(self):
        from agent.pipeline.orchestrator import PortingPipeline, AnalysisPipeline
        self.assertIs(AnalysisPipeline, PortingPipeline)

    def test_pipeline_function_aliases(self):
        from agent.pipeline.orchestrator import (
            create_porting_pipeline, create_analysis_pipeline,
        )
        self.assertIs(create_analysis_pipeline, create_porting_pipeline)

    def test_agent_aliases(self):
        from agent.pipeline.data_collector import (
            SourceAnalysisAgent, DataCollectionAgent,
            create_source_analysis_agent, create_data_collection_agent,
        )
        self.assertIs(DataCollectionAgent, SourceAnalysisAgent)
        self.assertIs(create_data_collection_agent, create_source_analysis_agent)

    def test_fusioner_aliases(self):
        from agent.pipeline.fusioner import (
            ValidationAgent, FusionAgent,
            create_validation_agent, create_fusion_agent,
        )
        self.assertIs(FusionAgent, ValidationAgent)
        self.assertIs(create_fusion_agent, create_validation_agent)

    def test_summarizer_aliases(self):
        from agent.pipeline.summarizer import (
            FinalChecklistGenerator, SummaryGenerator,
            create_checklist_generator, create_summary_generator,
        )
        self.assertIs(SummaryGenerator, FinalChecklistGenerator)
        self.assertIs(create_summary_generator, create_checklist_generator)

    def test_log_analyzer_aliases(self):
        from agent.pipeline.log_analyzer import (
            TDDWriterAgent, CoderAgent, NativeValidatorAgent,
            FwdkAnalyzer, UartAnalyzer, SimicsAnalyzer,
        )
        self.assertIs(FwdkAnalyzer, TDDWriterAgent)
        self.assertIs(UartAnalyzer, CoderAgent)
        self.assertIs(SimicsAnalyzer, NativeValidatorAgent)


class TestPackageInit(unittest.TestCase):
    """Tests for the pipeline package __init__.py exports."""

    def test_all_exports_importable(self):
        from agent.pipeline import __all__
        import agent.pipeline as pkg
        for name in __all__:
            self.assertTrue(
                hasattr(pkg, name),
                f"{name} listed in __all__ but not importable from agent.pipeline",
            )

    def test_agent_init_metadata(self):
        from agent import __version__, __release_date__, __description__
        self.assertEqual(__version__, "2.0.0")
        self.assertEqual(__release_date__, "2026-03-23")
        self.assertIn("porting", __description__.lower())


class TestFinalChecklist(unittest.TestCase):
    """Tests for the FinalChecklistGenerator (summarizer.py)."""

    def _make_generator(self):
        from agent.pipeline.summarizer import FinalChecklistGenerator
        logger = MagicMock()
        return FinalChecklistGenerator(llm=None, logger=logger)

    def _make_state(self, **overrides):
        from agent.pipeline.state import create_initial_state
        state = create_initial_state("test_driver", "freebsd", "/tmp/test_out")
        state["phase_status"] = {
            "phase0_source_analysis": "completed",
            "phase1_api_inventory": "completed",
            "phase2_tdd": "completed",
            "phase3_coder": "completed",
            "phase4_validation": "completed",
            "phase5_perf_portability": "completed",
            "phase6_risk_verification": "completed",
            "phase7_final_checklist": "pending",
        }
        state.update(overrides)
        return state

    def test_checklist_all_green(self):
        gen = self._make_generator()
        state = self._make_state(
            native_score=99.5,
            portability_score=97.0,
            test_results=[{"test_name": "t1", "passed": True}],
            substep_results=[{"build_ok": True}],
            risk_register=[{"severity": "low", "status": "mitigated"}],
        )
        checklist = gen._evaluate_checklist(state)
        self.assertTrue(checklist["native_score_ge_98"])
        self.assertTrue(checklist["portability_score_ge_95"])
        self.assertTrue(checklist["zero_critical_risks"])
        self.assertTrue(checklist["all_tdd_tests_pass"])
        self.assertTrue(checklist["build_ok_target_os"])
        self.assertTrue(all(checklist.values()))

    def test_checklist_native_score_low(self):
        gen = self._make_generator()
        state = self._make_state(native_score=90.0, portability_score=96.0)
        checklist = gen._evaluate_checklist(state)
        self.assertFalse(checklist["native_score_ge_98"])
        self.assertFalse(checklist["adapter_native_only"])

    def test_checklist_critical_risk(self):
        gen = self._make_generator()
        state = self._make_state(
            native_score=99.0,
            portability_score=96.0,
            risk_register=[{"severity": "critical", "status": "open"}],
        )
        checklist = gen._evaluate_checklist(state)
        self.assertFalse(checklist["zero_critical_risks"])

    def test_checklist_no_tests(self):
        gen = self._make_generator()
        state = self._make_state(native_score=99.0, portability_score=96.0)
        # Empty test_results
        checklist = gen._evaluate_checklist(state)
        self.assertFalse(checklist["all_tdd_tests_pass"])

    def test_checklist_failed_test(self):
        gen = self._make_generator()
        state = self._make_state(
            native_score=99.0,
            portability_score=96.0,
            test_results=[
                {"test_name": "t1", "passed": True},
                {"test_name": "t2", "passed": False},
            ],
        )
        checklist = gen._evaluate_checklist(state)
        self.assertFalse(checklist["all_tdd_tests_pass"])

    def test_write_report(self):
        gen = self._make_generator()
        state = self._make_state(
            native_score=99.0,
            portability_score=96.0,
            final_checklist={"native_score_ge_98": True, "portability_score_ge_95": True},
            porting_artifacts=[{"file_path": "core/rx.c", "artifact_type": "source", "description": "Rx path"}],
            test_results=[{"test_name": "test_rx", "target_os": "freebsd", "passed": True}],
            risk_register=[{"risk_id": "R001", "severity": "low", "category": "dma", "description": "Minor", "status": "mitigated"}],
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            report_path = gen._write_report(state, tmpdir)
            self.assertTrue(os.path.isfile(report_path))
            with open(report_path) as f:
                content = f.read()
            self.assertIn("test_driver", content)
            self.assertIn("freebsd", content)
            self.assertIn("99.0", content)
            self.assertIn("core/rx.c", content)
            self.assertIn("test_rx", content)
            self.assertIn("R001", content)

    def test_write_json_artifacts(self):
        gen = self._make_generator()
        state = self._make_state(
            native_score=99.0,
            portability_score=96.0,
            final_checklist={"item1": True},
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            gen._write_json_artifacts(state, tmpdir)
            json_path = os.path.join(tmpdir, "porting_results.json")
            self.assertTrue(os.path.isfile(json_path))
            with open(json_path) as f:
                data = json.load(f)
            self.assertEqual(data["driver_name"], "test_driver")
            self.assertEqual(data["target_os"], "freebsd")
            self.assertEqual(data["native_score"], 99.0)
            self.assertIn("generated_at", data)

    def test_full_run(self):
        """Test the full run() method (end to end, no LLM needed)."""
        gen = self._make_generator()
        state = self._make_state(
            native_score=99.0,
            portability_score=96.0,
            test_results=[{"test_name": "t1", "passed": True}],
            substep_results=[{"build_ok": True}],
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            state["output_dir"] = tmpdir
            result = gen.run(state)
            self.assertIn("final_checklist", result)
            self.assertTrue(os.path.isfile(result["final_report_path"]))
            self.assertTrue(os.path.isfile(os.path.join(tmpdir, "porting_results.json")))
            self.assertEqual(result["current_phase"], "completed")


class TestValidationAgent(unittest.TestCase):
    """Tests for the cross-phase ValidationAgent (fusioner.py)."""

    def test_build_prompt_contains_scores(self):
        from agent.pipeline.fusioner import ValidationAgent
        from agent.pipeline.state import create_initial_state

        mock_llm = MagicMock()
        logger = MagicMock()
        agent = ValidationAgent(mock_llm, logger)

        state = create_initial_state("ixgbe")
        state["native_score"] = 99.5
        state["portability_score"] = 96.2
        state["risk_register"] = [{"severity": "low", "category": "dma", "description": "test"}]

        prompt = agent._build_prompt(state)
        self.assertIn("99.5", prompt)
        self.assertIn("96.2", prompt)
        self.assertIn("ixgbe", prompt)
        self.assertIn("dma", prompt)


class TestPipelineGates(unittest.TestCase):
    """Test gate threshold constants."""

    def test_thresholds(self):
        from agent.pipeline.orchestrator import (
            NATIVE_SCORE_THRESHOLD, PORTABILITY_SCORE_THRESHOLD,
        )
        self.assertEqual(NATIVE_SCORE_THRESHOLD, 98.0)
        self.assertEqual(PORTABILITY_SCORE_THRESHOLD, 95.0)


class TestChecklistItems(unittest.TestCase):
    """Test that FINAL_CHECKLIST_ITEMS is complete."""

    def test_checklist_count(self):
        from agent.pipeline.summarizer import FINAL_CHECKLIST_ITEMS
        self.assertEqual(len(FINAL_CHECKLIST_ITEMS), 14)

    def test_checklist_items_match_evaluation(self):
        from agent.pipeline.summarizer import FINAL_CHECKLIST_ITEMS, FinalChecklistGenerator
        from agent.pipeline.state import create_initial_state

        gen = FinalChecklistGenerator(llm=None, logger=MagicMock())
        state = create_initial_state("test")
        checklist = gen._evaluate_checklist(state)

        # Every item in the constant list must appear in evaluated checklist
        for item in FINAL_CHECKLIST_ITEMS:
            self.assertIn(item, checklist, f"Checklist item {item!r} missing from evaluation")

        # Evaluate must not produce extra items
        for key in checklist:
            self.assertIn(key, FINAL_CHECKLIST_ITEMS, f"Extra checklist key {key!r} not in FINAL_CHECKLIST_ITEMS")


if __name__ == "__main__":
    unittest.main()
