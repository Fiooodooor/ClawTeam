"""
Pipeline Orchestrator — Multi-Agent Swarm for NIC Driver Porting

Uses LangGraph StateGraph to orchestrate the full porting pipeline:
- Phase 0: Core Layout & Source Analysis (directory scaffolding, Linux extraction)
- Phase 1: API Inventory & Native Mapping Tables
- Phase 2: TDD Test Writing (failing tests first)
- Phase 3: Coder (implement ported code)
- Phase 4: Native Validation & Code Review
- Phase 5: Performance Engineering & Portability Validation
- Phase 6: Risk Audit & Verification Execution
- Phase 7: Final Validation Checklist (Section 14)

Each sub-step follows the agent chain:
  TDD Writer → Coder → Native Validator → Reviewer →
  Performance Engineer → Portability Validator → Risk Auditor →
  Verification Executor → Supervisor gate

Gates: native_score ≥ 98, portability_score ≥ 95, zero critical risks.

The StateGraph provides:
- Typed state management across nodes
- Conditional routing with gate enforcement
- Checkpointing capability (Postgres or file fallback)
"""

import os
import sys
import logging
from typing import Dict, List, Any, Optional, Literal

from langchain_openai import AzureChatOpenAI
from langgraph.graph import StateGraph, END

# Import pipeline components
from .state import PipelineState, create_initial_state
from .data_collector import SourceAnalysisAgent, create_source_analysis_agent
from .log_analyzer import (
    TDDWriterAgent, CoderAgent, NativeValidatorAgent,
    CodeReviewerAgent, PerformanceEngineerAgent,
    PortabilityValidatorAgent, RiskAuditorAgent, VerificationExecutorAgent,
)
from .fusioner import ValidationAgent, create_validation_agent
from .summarizer import FinalChecklistGenerator, create_checklist_generator

# ---------------------------------------------------------------------------
# Gate thresholds (from the porting guide's non-negotiable principles)
# ---------------------------------------------------------------------------
NATIVE_SCORE_THRESHOLD = 98.0
PORTABILITY_SCORE_THRESHOLD = 95.0


def create_porting_pipeline(
    llm: AzureChatOpenAI,
    logger: logging.Logger,
) -> StateGraph:
    """
    Create the LangGraph StateGraph for the driver porting pipeline.

    Pipeline Flow:
    ```
    [START] → phase0_source_analysis → gate_phase0?
        → phase1_api_inventory → gate_phase1?
        → phase2_tdd_tests → phase3_coder → phase4_native_validation
        → phase5_perf_portability → gate_scores?
            → phase6_risk_verification → gate_risks?
                → phase7_final_checklist → [END]
    ```
    """

    # Create specialist agents
    source_agent = create_source_analysis_agent(llm, logger)
    validation_agent = create_validation_agent(llm, logger)
    checklist_generator = create_checklist_generator(llm, logger)

    # Specialist worker agents for the inner porting loop
    tdd_writer = TDDWriterAgent(llm, logger)
    coder = CoderAgent(llm, logger)
    native_validator = NativeValidatorAgent(llm, logger)
    code_reviewer = CodeReviewerAgent(llm, logger)
    perf_engineer = PerformanceEngineerAgent(llm, logger)
    portability_validator = PortabilityValidatorAgent(llm, logger)
    risk_auditor = RiskAuditorAgent(llm, logger)
    verification_executor = VerificationExecutorAgent(llm, logger)

    # ------------------------------------------------------------------
    # Node functions
    # ------------------------------------------------------------------

    def phase0_node(state: PipelineState) -> PipelineState:
        """Phase 0: Core Layout, Build Skeletons & Source Analysis"""
        print("[ORCHESTRATOR] Phase 0 — Core Layout & Source Analysis")
        logger.info("=" * 60)
        logger.info("[PHASE 0] Core Layout & Source Analysis")
        logger.info("=" * 60)

        try:
            state = source_agent.run(state)
            state['phase_status']['phase0_source_analysis'] = 'completed'
            linux_apis = len(state.get('source_analysis', {}).get('linux_apis_found', []))
            print(f"[ORCHESTRATOR] Phase 0 done — {linux_apis} Linux APIs identified")
            logger.info(f"[PHASE 0] Done — {linux_apis} Linux APIs identified")
        except Exception as e:
            logger.error(f"Phase 0 failed: {e}")
            state['errors'].append(f"Phase 0 failed: {str(e)}")
            state['should_continue'] = False
            state['phase_status']['phase0_source_analysis'] = 'failed'

        return state

    def phase1_node(state: PipelineState) -> PipelineState:
        """Phase 1: API Inventory & Native Mapping Tables"""
        print("[ORCHESTRATOR] Phase 1 — API Inventory & Mapping Tables")
        logger.info("=" * 60)
        logger.info("[PHASE 1] API Inventory & Native Mapping Tables")
        logger.info("=" * 60)

        try:
            state = source_agent.build_api_inventory(state)
            state['phase_status']['phase1_api_inventory'] = 'completed'
            mappings = len(state.get('api_mappings', []))
            print(f"[ORCHESTRATOR] Phase 1 done — {mappings} API mappings created")
            logger.info(f"[PHASE 1] Done — {mappings} API mappings")
        except Exception as e:
            logger.error(f"Phase 1 failed: {e}")
            state['errors'].append(f"Phase 1 failed: {str(e)}")
            state['should_continue'] = False
            state['phase_status']['phase1_api_inventory'] = 'failed'

        return state

    def phase2_tdd_node(state: PipelineState) -> PipelineState:
        """Phase 2: TDD Test Writer — write failing tests first"""
        print("[ORCHESTRATOR] Phase 2 — TDD Test Writing (failing tests first)")
        logger.info("=" * 60)
        logger.info("[PHASE 2] TDD Test Writing")
        logger.info("=" * 60)

        try:
            state = tdd_writer.run(state)
            state['phase_status']['phase2_tdd'] = 'completed'
            print("[ORCHESTRATOR] Phase 2 done — failing tests written")
        except Exception as e:
            logger.error(f"Phase 2 failed: {e}")
            state['errors'].append(f"Phase 2 TDD failed: {str(e)}")
            state['phase_status']['phase2_tdd'] = 'failed'

        return state

    def phase3_coder_node(state: PipelineState) -> PipelineState:
        """Phase 3: Coder — implement ported driver code"""
        print("[ORCHESTRATOR] Phase 3 — Coder (implementing ported code)")
        logger.info("=" * 60)
        logger.info("[PHASE 3] Coder — Implement Ported Code")
        logger.info("=" * 60)

        try:
            state = coder.run(state)
            state['phase_status']['phase3_coder'] = 'completed'
            artifacts = len(state.get('porting_artifacts', []))
            print(f"[ORCHESTRATOR] Phase 3 done — {artifacts} artifacts produced")
        except Exception as e:
            logger.error(f"Phase 3 failed: {e}")
            state['errors'].append(f"Phase 3 Coder failed: {str(e)}")
            state['phase_status']['phase3_coder'] = 'failed'

        return state

    def phase4_validation_node(state: PipelineState) -> PipelineState:
        """Phase 4: Native Validation & Code Review"""
        print("[ORCHESTRATOR] Phase 4 — Native Validation & Code Review")
        logger.info("=" * 60)
        logger.info("[PHASE 4] Native Validation & Code Review")
        logger.info("=" * 60)

        try:
            state = native_validator.run(state)
            state = code_reviewer.run(state)
            state['phase_status']['phase4_validation'] = 'completed'
            score = state.get('native_score', 0)
            print(f"[ORCHESTRATOR] Phase 4 done — native_score={score:.1f}")
        except Exception as e:
            logger.error(f"Phase 4 failed: {e}")
            state['errors'].append(f"Phase 4 Validation failed: {str(e)}")
            state['phase_status']['phase4_validation'] = 'failed'

        return state

    def phase5_perf_portability_node(state: PipelineState) -> PipelineState:
        """Phase 5: Performance Engineering & Portability Validation"""
        print("[ORCHESTRATOR] Phase 5 — Performance & Portability")
        logger.info("=" * 60)
        logger.info("[PHASE 5] Performance & Portability Validation")
        logger.info("=" * 60)

        try:
            state = perf_engineer.run(state)
            state = portability_validator.run(state)
            state['phase_status']['phase5_perf_portability'] = 'completed'
            ns = state.get('native_score', 0)
            ps = state.get('portability_score', 0)
            print(f"[ORCHESTRATOR] Phase 5 done — native={ns:.1f} portability={ps:.1f}")
        except Exception as e:
            logger.error(f"Phase 5 failed: {e}")
            state['errors'].append(f"Phase 5 failed: {str(e)}")
            state['phase_status']['phase5_perf_portability'] = 'failed'

        return state

    def phase6_risk_verification_node(state: PipelineState) -> PipelineState:
        """Phase 6: Risk Audit & Verification Execution"""
        print("[ORCHESTRATOR] Phase 6 — Risk Audit & Verification")
        logger.info("=" * 60)
        logger.info("[PHASE 6] Risk Audit & Verification")
        logger.info("=" * 60)

        try:
            state = risk_auditor.run(state)
            state = verification_executor.run(state)
            state['phase_status']['phase6_risk_verification'] = 'completed'
            critical = sum(
                1 for r in state.get('risk_register', [])
                if r.get('severity') == 'critical' and r.get('status') == 'open'
            )
            print(f"[ORCHESTRATOR] Phase 6 done — {critical} critical open risks")
        except Exception as e:
            logger.error(f"Phase 6 failed: {e}")
            state['errors'].append(f"Phase 6 failed: {str(e)}")
            state['phase_status']['phase6_risk_verification'] = 'failed'

        return state

    def phase7_final_node(state: PipelineState) -> PipelineState:
        """Phase 7 / Section 14: Final Validation Checklist"""
        print("[ORCHESTRATOR] Phase 7 — Final Validation Checklist")
        logger.info("=" * 60)
        logger.info("[PHASE 7] Final Validation Checklist (Section 14)")
        logger.info("=" * 60)

        try:
            state = checklist_generator.run(state)
            state['phase_status']['phase7_final_checklist'] = 'completed'
        except Exception as e:
            logger.error(f"Phase 7 failed: {e}")
            state['errors'].append(f"Phase 7 Final Checklist failed: {str(e)}")
            state['phase_status']['phase7_final_checklist'] = 'failed'

        return state

    # ------------------------------------------------------------------
    # Gate functions
    # ------------------------------------------------------------------

    def gate_after_phase0(state: PipelineState) -> Literal["phase1_api_inventory", "end"]:
        """Gate: source analysis must succeed to proceed"""
        if not state.get('should_continue', True):
            logger.info("Pipeline stopped after Phase 0: should_continue is False")
            return "end"
        if not state.get('source_analysis', {}).get('linux_apis_found'):
            logger.info("Pipeline stopped: no Linux APIs found in source")
            return "end"
        return "phase1_api_inventory"

    def gate_after_phase1(state: PipelineState) -> Literal["phase2_tdd", "end"]:
        """Gate: API mappings must exist to proceed"""
        if not state.get('should_continue', True):
            return "end"
        if not state.get('api_mappings'):
            logger.info("Pipeline stopped: no API mappings created")
            return "end"
        return "phase2_tdd"

    def gate_scores(state: PipelineState) -> Literal["phase6_risk_verification", "end"]:
        """Gate: native_score ≥ 98, portability_score ≥ 95"""
        ns = state.get('native_score', 0)
        ps = state.get('portability_score', 0)
        if ns < NATIVE_SCORE_THRESHOLD:
            logger.warning(f"GATE FAIL: native_score {ns:.1f} < {NATIVE_SCORE_THRESHOLD}")
            state['errors'].append(f"Gate fail: native_score {ns:.1f} < {NATIVE_SCORE_THRESHOLD}")
            return "end"
        if ps < PORTABILITY_SCORE_THRESHOLD:
            logger.warning(f"GATE FAIL: portability_score {ps:.1f} < {PORTABILITY_SCORE_THRESHOLD}")
            state['errors'].append(f"Gate fail: portability_score {ps:.1f} < {PORTABILITY_SCORE_THRESHOLD}")
            return "end"
        return "phase6_risk_verification"

    def gate_risks(state: PipelineState) -> Literal["phase7_final_checklist", "end"]:
        """Gate: zero critical open risks"""
        critical_open = sum(
            1 for r in state.get('risk_register', [])
            if r.get('severity') == 'critical' and r.get('status') == 'open'
        )
        if critical_open > 0:
            logger.warning(f"GATE FAIL: {critical_open} critical open risks remain")
            state['errors'].append(f"Gate fail: {critical_open} critical open risks")
            return "end"
        return "phase7_final_checklist"

    # ------------------------------------------------------------------
    # Build the graph
    # ------------------------------------------------------------------
    workflow = StateGraph(PipelineState)

    # Add nodes (Phases 0–7)
    workflow.add_node("phase0_source_analysis", phase0_node)
    workflow.add_node("phase1_api_inventory", phase1_node)
    workflow.add_node("phase2_tdd", phase2_tdd_node)
    workflow.add_node("phase3_coder", phase3_coder_node)
    workflow.add_node("phase4_validation", phase4_validation_node)
    workflow.add_node("phase5_perf_portability", phase5_perf_portability_node)
    workflow.add_node("phase6_risk_verification", phase6_risk_verification_node)
    workflow.add_node("phase7_final_checklist", phase7_final_node)

    # Entry point
    workflow.set_entry_point("phase0_source_analysis")

    # Edges with conditional gates
    workflow.add_conditional_edges(
        "phase0_source_analysis", gate_after_phase0,
        {"phase1_api_inventory": "phase1_api_inventory", "end": END},
    )
    workflow.add_conditional_edges(
        "phase1_api_inventory", gate_after_phase1,
        {"phase2_tdd": "phase2_tdd", "end": END},
    )
    workflow.add_edge("phase2_tdd", "phase3_coder")
    workflow.add_edge("phase3_coder", "phase4_validation")
    workflow.add_edge("phase4_validation", "phase5_perf_portability")
    workflow.add_conditional_edges(
        "phase5_perf_portability", gate_scores,
        {"phase6_risk_verification": "phase6_risk_verification", "end": END},
    )
    workflow.add_conditional_edges(
        "phase6_risk_verification", gate_risks,
        {"phase7_final_checklist": "phase7_final_checklist", "end": END},
    )
    workflow.add_edge("phase7_final_checklist", END)

    return workflow.compile()


# ======================================================================
# High-level wrappers
# ======================================================================

class PortingPipeline:
    """
    High-level wrapper for the LangGraph driver porting pipeline.

    Provides a simple interface for running the complete swarm.
    """

    def __init__(self, llm: AzureChatOpenAI, logger: logging.Logger):
        self.llm = llm
        self.logger = logger
        self.graph = create_porting_pipeline(llm, logger)

    def run(
        self,
        driver_name: str,
        target_os: str = "freebsd",
        output_dir: str = "./artifacts",
        source_dir: str = "",
        connection_info: Optional[Dict[str, Any]] = None,
    ) -> PipelineState:
        """
        Execute the full porting pipeline for a driver.

        Args:
            driver_name: Name of the driver to port (e.g. "ixgbe", "ice")
            target_os: Primary target OS (default: "freebsd")
            output_dir: Directory for output artifacts
            source_dir: Path to reference Linux driver source
            connection_info: SSH connection info for target VMs

        Returns:
            Final pipeline state with all results and scores
        """
        self.logger.info(f"[ORCHESTRATOR] Starting swarm for driver: {driver_name}")

        state = create_initial_state(
            driver_name=driver_name,
            target_os=target_os,
            output_dir=output_dir,
            source_dir=source_dir,
            connection_info=connection_info,
        )
        state['phase_status'] = {
            'phase0_source_analysis': 'pending',
            'phase1_api_inventory': 'pending',
            'phase2_tdd': 'pending',
            'phase3_coder': 'pending',
            'phase4_validation': 'pending',
            'phase5_perf_portability': 'pending',
            'phase6_risk_verification': 'pending',
            'phase7_final_checklist': 'pending',
        }

        final_state = self.graph.invoke(state)
        return final_state


# Convenience aliases matching old API names
AnalysisPipeline = PortingPipeline


def create_pipeline(
    llm: AzureChatOpenAI,
    logger: logging.Logger,
    max_parallel: int = 2,
) -> PortingPipeline:
    """Factory function to create the porting pipeline"""
    return PortingPipeline(llm, logger)


def run_pipeline(
    driver_name: str,
    target_os: str,
    output_dir: str,
    llm: AzureChatOpenAI,
    logger: logging.Logger,
    source_dir: str = "",
    connection_info: Optional[Dict[str, Any]] = None,
    **kwargs,
) -> PipelineState:
    """
    Convenience function to create and run the porting pipeline.

    Args:
        driver_name: Driver to port (e.g. "ixgbe", "ice")
        target_os: Primary target OS ("freebsd", "windows", etc.)
        output_dir: Directory for output artifacts
        llm: LangChain LLM instance
        logger: Logger instance
        source_dir: Path to reference Linux driver source
        connection_info: SSH connection info for target VMs

    Returns:
        Final pipeline state with all results
    """
    pipeline = create_pipeline(llm, logger)
    return pipeline.run(
        driver_name=driver_name,
        target_os=target_os,
        output_dir=output_dir,
        source_dir=source_dir,
        connection_info=connection_info,
    )


# Keep backward-compatible name
create_analysis_pipeline = create_porting_pipeline
