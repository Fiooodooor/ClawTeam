#!/usr/bin/env python3
"""
Multi-Agent Swarm Orchestrator for NIC Driver Porting — CLI

Autonomously drives the entire multi-agent swarm to produce complete, fully
ported, buildable, testable, framework-independent driver code.

Porting pipeline phases:
- Phase 0: Core Layout & Source Analysis (Linux dataplane extraction)
- Phase 1: API Inventory & Native Mapping Tables
- Phase 2: TDD Test Writing (failing tests first)
- Phase 3: Coder (implement ported code)
- Phase 4: Native Validation & Code Review
- Phase 5: Performance Engineering & Portability Validation
- Phase 6: Risk Audit & Verification Execution
- Phase 7: Final Validation Checklist (Section 14)

Usage:
    python -m agent.analyze_build --driver <DRIVER_NAME> --output-dir <OUTPUT_DIR>

Example:
    python -m agent.analyze_build --driver ixgbe --target-os freebsd --output-dir ./artifacts/ixgbe
"""

import argparse
import os
import sys
import json
import logging
import warnings
from datetime import datetime
from pathlib import Path
from typing import Dict, Any

# Suppress urllib3 InsecureRequestWarning
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from dotenv import load_dotenv
from langchain_openai import AzureChatOpenAI
from langchain_core.globals import set_debug, set_verbose
from azure.identity import DefaultAzureCredential, get_bearer_token_provider

# Import pipeline
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pipeline import run_pipeline, PipelineState
from agent import __version__, __release_date__, __description__

# Load environment variables
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.env'))


def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description='Multi-agent swarm orchestrator for autonomous NIC driver data-plane porting',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --driver ixgbe --output-dir ./artifacts/ixgbe
  %(prog)s --driver ice --target-os freebsd --source-dir /src/drivers/net/ethernet/intel/ice
  %(prog)s --driver mynic --target-os freebsd --connection-info ./connection-info.yaml

Porting Phases:
  Phase 0: Core Layout & Source Analysis (Linux dataplane extraction)
  Phase 1: API Inventory & Native Mapping Tables
  Phase 2: TDD Test Writing (failing tests first)
  Phase 3: Coder (implement ported code)
  Phase 4: Native Validation & Code Review
  Phase 5: Performance & Portability Validation
  Phase 6: Risk Audit & Verification
  Phase 7: Final Validation Checklist

Gate Thresholds:
  native_score >= 98  |  portability_score >= 95  |  zero critical risks
        """
    )

    parser.add_argument(
        '--version', '-V',
        action='version',
        version=f'%(prog)s {__version__} ({__release_date__})\n{__description__}'
    )

    parser.add_argument(
        '--driver', '-d',
        type=str,
        required=True,
        help='Driver name to port (e.g., ixgbe, ice, i40e, mynic_native)'
    )

    parser.add_argument(
        '--target-os', '-t',
        type=str,
        default='freebsd',
        choices=['freebsd', 'windows', 'illumos', 'netbsd', 'rtos'],
        help='Primary target OS (default: freebsd)'
    )

    parser.add_argument(
        '--source-dir', '-s',
        type=str,
        default='',
        help='Path to reference Linux driver source directory'
    )

    parser.add_argument(
        '--output-dir', '-o',
        type=str,
        required=True,
        help='Output directory path for porting artifacts and results'
    )

    parser.add_argument(
        '--connection-info', '-c',
        type=str,
        default='',
        help='Path to YAML file with SSH connection info for target VMs'
    )

    parser.add_argument(
        '--guide', '-g',
        type=str,
        default='',
        help='Path to the NIC Data Plane Porting Guide (optional override)'
    )

    return parser.parse_args()


def validate_environment_variables(logger=None):
    """Validate that all required environment variables are set"""
    required_vars = {
        'AZURE_OPENAI_ENDPOINT': 'Azure OpenAI endpoint URL',
        'AZURE_OPENAI_DEPLOYMENT': 'Azure OpenAI deployment name',
    }

    missing_vars = []
    for var_name, description in required_vars.items():
        if not os.getenv(var_name):
            missing_vars.append(f"  - {var_name}: {description}")

    if missing_vars:
        error_msg = "Required environment variables are missing:"
        missing_list = "\n".join(missing_vars)
        footer = "\nPlease add these variables to your .env file\nSee .env.example for reference"

        print(f"Error: {error_msg}", file=sys.stderr)
        print(missing_list, file=sys.stderr)
        print(footer, file=sys.stderr)

        if logger:
            logger.error(error_msg)
            for var in missing_vars:
                logger.error(var)

        sys.exit(1)


def initialize_llm() -> AzureChatOpenAI:
    """Initialize the LangChain LLM using Azure OpenAI with DefaultAzureCredential"""
    # Set proxy environment variables for Azure OpenAI access
    os.environ['HTTP_PROXY'] = 'http://proxy-dmz.intel.com:912'
    os.environ['HTTPS_PROXY'] = 'http://proxy-dmz.intel.com:912'
    # Exclude Azure OpenAI endpoints from proxy - access via VPN/private endpoint
    os.environ["no_proxy"] = "openai.azure.com"
    os.environ["NO_PROXY"] = "openai.azure.com"

    # Get Azure OpenAI configuration (already validated)
    endpoint = os.getenv('AZURE_OPENAI_ENDPOINT')
    deployment = os.getenv('AZURE_OPENAI_DEPLOYMENT')
    api_version = os.getenv('AZURE_OPENAI_API_VERSION', '2024-08-01-preview')
    temperature = float(os.getenv('AZURE_OPENAI_TEMPERATURE', '0'))

    # Use DefaultAzureCredential which supports Workload Identity (K8s),
    # Managed Identity, Azure CLI, and other credential types automatically.
    credential = DefaultAzureCredential()
    token_provider = get_bearer_token_provider(
        credential, "https://cognitiveservices.azure.com/.default"
    )

    # Initialize Azure ChatOpenAI with auto-refreshing token provider
    llm = AzureChatOpenAI(
        azure_deployment=deployment,
        api_version=api_version,
        temperature=temperature,
        azure_endpoint=endpoint,
        azure_ad_token_provider=token_provider
    )

    return llm


def _load_connection_info(path: str) -> Dict[str, Any]:
    """Load VM connection info from YAML file"""
    if not path or not os.path.exists(path):
        return {}
    import yaml
    with open(path, 'r') as f:
        return yaml.safe_load(f) or {}


def setup_logging(output_path: str) -> logging.Logger:
    """Setup logging to file only.

    All logs are written to pipeline.log at DEBUG level.
    Console output is handled via print() for key progress messages.
    """

    # Create output directory
    os.makedirs(output_path, exist_ok=True)

    # File handler only - all logger output goes to pipeline.log, not console
    log_file = os.path.join(output_path, 'pipeline.log')
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.DEBUG)  # Always log DEBUG to file
    file_format = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
    )
    file_handler.setFormatter(file_format)

    # Configure root logger to capture all logs (file only, no console)
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)  # Capture everything at root
    root_logger.handlers.clear()
    root_logger.addHandler(file_handler)

    # Create pipeline logger (inherits root handlers)
    logger = logging.getLogger('pipeline')
    logger.setLevel(logging.DEBUG)

    # Keep LangChain/LangGraph loggers at INFO to avoid excessive verbosity
    for lc_logger_name in ['langchain', 'langchain_core', 'langchain_openai', 'langgraph', 'openai', 'httpcore']:
        lc_logger = logging.getLogger(lc_logger_name)
        lc_logger.setLevel(logging.INFO)

    # Suppress httpx HTTP request logs (they log at INFO level)
    logging.getLogger('httpx').setLevel(logging.WARNING)

    # Never enable LangChain's set_debug/set_verbose - too verbose
    set_verbose(False)
    set_debug(False)

    return logger


def main():
    """Main entry point"""
    args = parse_arguments()

    # Setup logging (file only, console via print())
    logger = setup_logging(args.output_dir)

    # Console: key startup info
    print("=" * 60)
    print("NIC Driver Porting — Multi-Agent Swarm Orchestrator")
    print("=" * 60)
    print(f"Driver: {args.driver} | Target OS: {args.target_os}")
    print(f"Source: {args.source_dir or '(auto-detect)'}")
    print(f"Output: {args.output_dir}")
    print("=" * 60)

    # Log to file
    logger.info("NIC Driver Porting Swarm Started")
    logger.info(f"Driver: {args.driver}")
    logger.info(f"Target OS: {args.target_os}")
    logger.info(f"Source Dir: {args.source_dir}")
    logger.info(f"Output Dir: {args.output_dir}")

    # Validate environment
    validate_environment_variables(logger)

    # Load connection info for SSH access to VMs
    connection_info = _load_connection_info(args.connection_info)

    # Initialize LLM
    print("Initializing Azure OpenAI...")
    logger.info("Initializing Azure OpenAI...")
    try:
        llm = initialize_llm()
        print("Azure OpenAI initialized successfully")
        logger.info("LLM initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize LLM: {e}")
        sys.exit(1)

    # Run the porting pipeline
    start_time = datetime.now()

    try:
        print("[ORCHESTRATOR] Guide loaded successfully. Starting swarm "
              f"for driver: {args.driver}")

        state = run_pipeline(
            driver_name=args.driver,
            target_os=args.target_os,
            output_dir=args.output_dir,
            source_dir=args.source_dir,
            connection_info=connection_info,
            llm=llm,
            logger=logger,
        )

        # Print phase status
        print("\nPhase Status:")
        for phase, status in state.get('phase_status', {}).items():
            icon = "✓" if status == 'completed' else "✗" if status == 'failed' else "○"
            print(f"  {icon} {phase}: {status}")

        # Print scores
        ns = state.get('native_score', 0)
        ps = state.get('portability_score', 0)
        print(f"\nScores: native={ns:.1f} | portability={ps:.1f}")

        elapsed = datetime.now() - start_time
        duration_msg = f"Pipeline completed in {elapsed.total_seconds():.1f} seconds"
        print(duration_msg)
        logger.info(duration_msg)

        # Final success message (from system prompt spec)
        if not state.get('errors'):
            print("\n" + "=" * 40)
            print("ORCHESTRATOR COMPLETE — FULL PORT READY")
            print(f"Driver: {args.driver}")
            print(f"Native score: {ns:.1f} | Portability: {ps:.1f}")
            print("All phases 0–7 + Sections 12–14 executed")
            print(f"Artifacts: {args.output_dir}")
            print("=" * 40)
            sys.exit(0)
        else:
            print(f"\nCompleted with {len(state['errors'])} error(s)")
            sys.exit(1)

    except KeyboardInterrupt:
        logger.warning("Pipeline interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.exception(f"Pipeline failed with error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
