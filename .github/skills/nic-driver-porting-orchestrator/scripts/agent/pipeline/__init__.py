"""
Multi-Agent Swarm Pipeline for NIC Driver Porting

This pipeline implements an eight-phase porting architecture (Phases 0–7)
plus Sections 12–14 (Testing, Risk Register, Final Validation):
- Phase 0: Core Layout & Source Analysis
- Phase 1: API Inventory & Native Mapping Tables
- Phase 2: TDD Test Writing (failing tests first)
- Phase 3: Coder (implement ported code)
- Phase 4: Native Validation & Code Review
- Phase 5: Performance & Portability Validation
- Phase 6: Risk Audit & Verification Execution
- Phase 7: Final Validation Checklist (Section 14)

Usage:
    from pipeline import run_pipeline

    result = run_pipeline(
        driver_name="ixgbe",
        target_os="freebsd",
        output_dir="./artifacts/ixgbe",
        llm=my_llm,
        logger=my_logger,
    )
"""

from .state import (
    PipelineState,
    create_initial_state,
    SourceAnalysis,
    DirectoryLayout,
    APIMapping,
    PortingArtifact,
    SubstepResult,
    TestResult,
    RiskEntry,
)
from .orchestrator import (
    PortingPipeline,
    AnalysisPipeline,  # backward compat alias
    create_pipeline,
    run_pipeline,
    create_porting_pipeline,
    create_analysis_pipeline,  # backward compat alias
)
from .data_collector import (
    SourceAnalysisAgent,
    DataCollectionAgent,  # backward compat alias
    create_source_analysis_agent,
    create_data_collection_agent,  # backward compat alias
)
from .fusioner import (
    ValidationAgent,
    FusionAgent,  # backward compat alias
    create_validation_agent,
    create_fusion_agent,  # backward compat alias
)
from .summarizer import (
    FinalChecklistGenerator,
    SummaryGenerator,  # backward compat alias
    create_checklist_generator,
    create_summary_generator,  # backward compat alias
)

__all__ = [
    # Main entry points
    'run_pipeline',
    'create_pipeline',
    'PortingPipeline',
    'AnalysisPipeline',

    # State types
    'PipelineState',
    'create_initial_state',
    'SourceAnalysis',
    'DirectoryLayout',
    'APIMapping',
    'PortingArtifact',
    'SubstepResult',
    'TestResult',
    'RiskEntry',

    # LangGraph pipeline
    'create_porting_pipeline',
    'create_analysis_pipeline',

    # Phase agents
    'SourceAnalysisAgent',
    'DataCollectionAgent',
    'ValidationAgent',
    'FusionAgent',
    'FinalChecklistGenerator',
    'SummaryGenerator',

    # Factory functions
    'create_source_analysis_agent',
    'create_data_collection_agent',
    'create_validation_agent',
    'create_fusion_agent',
    'create_checklist_generator',
    'create_summary_generator',
]
