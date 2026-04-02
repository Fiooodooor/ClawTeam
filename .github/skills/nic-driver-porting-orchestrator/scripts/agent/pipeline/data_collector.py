"""
Phase 0 & 1: Source Analysis & API Inventory Agent

Responsible for:
- Analysing the reference Linux driver source to extract dataplane files
- Identifying all Linux-specific API calls (sk_buff, dma_*, napi_*, etc.)
- Building the directory layout skeleton for the ported driver
- Creating the API inventory with native OS mapping tables

Uses LangGraph's create_react_agent for tool orchestration.
"""

import os
import sys
import logging
from typing import Dict, List, Any, Optional

from langchain_openai import AzureChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langgraph.prebuilt import create_react_agent

from .callbacks import ToolCallLogger

# Import tools from tools directory
TOOLS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'tools')
sys.path.insert(0, TOOLS_DIR)

from list_files import list_files
from read_file import read_file
from grep_file import grep_file

# Import state types
from .state import (
    PipelineState,
    SourceAnalysis,
    DirectoryLayout,
    APIMapping,
)

# Import skills with warning if missing
try:
    from agent.skills import get_source_analysis_skills
except ImportError:
    try:
        from ..skills import get_source_analysis_skills
    except Exception:
        import warnings
        warnings.warn("Failed to load source_analysis skills. Agent will run without skills context.")
        def get_source_analysis_skills():
            return ""


# Source analysis tools
SOURCE_ANALYSIS_TOOLS = [
    list_files,
    read_file,
    grep_file,
]


def build_system_prompt() -> str:
    """Build system prompt for source analysis agent."""
    skills = get_source_analysis_skills()
    return f"""You are the Source Analysis Agent for a NIC driver porting swarm.
Your purpose is to autonomously analyse a reference Linux Ethernet driver and
prepare all information needed for a fully ported, buildable, testable,
framework-independent driver on the target OS.

CORE PORTING PRINCIPLES (never violate):
1. Correctness-first TDD — every ported function must have a failing test first.
2. Maximum performance + portability + minimal divergence from the Linux reference.
3. Zero frameworks — no iflib, linuxkpi, rte_*, DPDK, or any abstraction layer.
4. Native-only OS calls — FreeBSD: ifnet(9), bus_dma(9), mbuf(9), pci(9),
   taskqueue(9), MSI-X.  Windows: NDIS Miniport*.
5. Thin OAL seams — the portable NIC core contains ZERO OS calls; the adapter
   is the thinnest possible native wrapper.

YOUR TASKS (Phase 0):
1. Discover all source files in the reference Linux driver directory.
2. Classify each file as DATAPLANE (TX/RX, DMA, interrupt, RSS, TSO, checksum)
   or EXCLUDED (PHY, firmware, config, management).
3. Identify every Linux-specific API call in the dataplane files.
4. Catalogue descriptor formats, ring structures, and offload features.
5. Produce the directory layout skeleton for the ported driver.

FRAMEWORK DETECTION (instant rejection):
If you see iflib, linuxkpi, rte_*, DPDK, or any framework call in the plan,
reject it immediately and replace with the pure native equivalent.

Work autonomously — do NOT ask questions.

---
REFERENCE KNOWLEDGE:
{skills}
"""


def build_api_inventory_prompt(state: PipelineState) -> str:
    """Build the Phase 1 prompt for API inventory generation."""
    driver = state.get('driver_name', 'unknown')
    target_os = state.get('target_os', 'freebsd')
    linux_apis = state.get('source_analysis', {}).get('linux_apis_found', [])
    apis_list = "\n".join(f"  - {a}" for a in linux_apis) if linux_apis else "  (none discovered yet)"

    return f"""Build the complete API Inventory & Native Mapping Table for driver: {driver}
Target OS: {target_os}

Linux APIs found in source analysis:
{apis_list}

For EVERY Linux API listed above, produce a mapping entry with:
- linux_api: the original Linux call
- target_api: the native {target_os} equivalent (FreeBSD: bus_dma, mbuf, ifnet, etc.)
- category: dma | packet_buffer | tx_rx | interrupt | offload | sync | memory | pci
- notes: any caveats, parameter differences, or seam guidance
- tdd_tested: false (will be set true during Phase 2)

STRICT RULES:
- ZERO framework calls (no iflib, linuxkpi, DPDK)
- Every mapping MUST use only native OS API calls
- Group by category for readability

Return a JSON array of mapping objects."""


class SourceAnalysisAgent:
    """
    Phase 0 agent: analyses the Linux driver source, classifies files,
    identifies APIs, and scaffolds the ported driver directory.
    """

    def __init__(self, llm: AzureChatOpenAI, logger: logging.Logger):
        self.llm = llm
        self.logger = logger
        self.tools = SOURCE_ANALYSIS_TOOLS

        self.agent = create_react_agent(
            model=llm,
            tools=self.tools,
            prompt=build_system_prompt(),
        )

    def run(self, state: PipelineState) -> PipelineState:
        """
        Execute Phase 0: Source Analysis.

        Populates state['source_analysis'] and state['directory_layout'].
        """
        driver_name = state['driver_name']
        source_dir = state.get('source_dir', '')
        output_dir = state.get('output_dir', './artifacts')

        task_prompt = self._build_task_prompt(driver_name, source_dir, output_dir)

        try:
            result = self.agent.invoke(
                {"messages": [HumanMessage(content=task_prompt)]},
                {"recursion_limit": 100,
                 "callbacks": [ToolCallLogger(self.logger, "source_analysis")]},
            )

            final_message = result["messages"][-1]
            parsed = self._parse_response(final_message.content)

            if parsed:
                state = self._update_state(state, parsed)
            else:
                state['errors'].append("Source analysis failed to produce parseable results")
                state['should_continue'] = False

        except Exception as e:
            self.logger.error(f"Source analysis agent failed: {e}")
            state['errors'].append(f"Source analysis failed: {str(e)}")
            state['should_continue'] = False

        state['current_phase'] = 'phase1_api_inventory'
        return state

    def build_api_inventory(self, state: PipelineState) -> PipelineState:
        """
        Execute Phase 1: API Inventory & Mapping Tables.

        Populates state['api_mappings'].
        """
        prompt = build_api_inventory_prompt(state)

        try:
            result = self.agent.invoke(
                {"messages": [HumanMessage(content=prompt)]},
                {"recursion_limit": 60,
                 "callbacks": [ToolCallLogger(self.logger, "api_inventory")]},
            )

            final_message = result["messages"][-1]
            mappings = self._parse_mappings(final_message.content)
            state['api_mappings'] = mappings
        except Exception as e:
            self.logger.error(f"API inventory failed: {e}")
            state['errors'].append(f"API inventory failed: {str(e)}")
            state['should_continue'] = False

        state['current_phase'] = 'phase2_tdd'
        return state

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_task_prompt(self, driver_name: str, source_dir: str, output_dir: str) -> str:
        src = source_dir if source_dir else f"(locate {driver_name} source automatically)"
        return f"""Analyse the reference Linux driver: {driver_name}
Source directory: {src}
Output directory: {output_dir}

YOUR MISSION:
1. List and read the driver source files to identify dataplane vs excluded files.
2. Grep for Linux-specific API patterns: sk_buff, dma_map_single, napi_schedule,
   net_device, dma_alloc_coherent, pci_alloc_irq_vectors, netif_*, etc.
3. Catalogue descriptor struct names, ring structures, offload features.
4. Design the ported directory layout following the three-layer architecture:
   - core/  (portable NIC core — zero OS calls)
   - os/<target>/  (thin native adapter)
   - tests/  (CppUTest native mocks)

Return a JSON object:
{{
    "source_analysis": {{
        "driver_name": "{driver_name}",
        "source_dir": "<path>",
        "dataplane_files": ["<file1>", ...],
        "excluded_files": ["<file1>", ...],
        "linux_apis_found": ["dma_map_single", "sk_buff", ...],
        "descriptor_formats": ["struct ixgbe_tx_desc", ...],
        "offload_features": ["TSO", "checksum", "RSS", ...]
    }},
    "directory_layout": {{
        "core_dir": "{output_dir}/{driver_name}/core",
        "os_adapters": {{"freebsd": "{output_dir}/{driver_name}/os/freebsd"}},
        "tests_dir": "{output_dir}/{driver_name}/tests",
        "docs_dir": "{output_dir}/{driver_name}/docs",
        "build_system": "Makefile.multi"
    }}
}}"""

    def _parse_response(self, content: str) -> Optional[Dict[str, Any]]:
        from .json_utils import parse_llm_json_response
        return parse_llm_json_response(content, self.logger)

    def _parse_mappings(self, content: str) -> List[APIMapping]:
        from .json_utils import parse_llm_json_response
        parsed = parse_llm_json_response(content, self.logger)
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict) and 'api_mappings' in parsed:
            return parsed['api_mappings']
        return []

    def _update_state(self, state: PipelineState, result: Dict[str, Any]) -> PipelineState:
        if 'source_analysis' in result:
            state['source_analysis'] = result['source_analysis']
        if 'directory_layout' in result:
            state['directory_layout'] = result['directory_layout']
        return state


# Backward-compatible alias
DataCollectionAgent = SourceAnalysisAgent


def create_source_analysis_agent(llm: AzureChatOpenAI, logger: logging.Logger) -> SourceAnalysisAgent:
    """Factory function to create source analysis agent"""
    return SourceAnalysisAgent(llm, logger)


# Keep old name for backward compatibility
create_data_collection_agent = create_source_analysis_agent
