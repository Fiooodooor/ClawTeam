"""
LangChain callback handlers for the pipeline.

Provides logging and debugging utilities for agent tool calls.
"""

import logging
from langchain_core.callbacks import BaseCallbackHandler


class ToolCallLogger(BaseCallbackHandler):
    """Log tool calls with arguments at DEBUG level."""

    def __init__(self, logger_instance: logging.Logger, agent_name: str = "agent"):
        self.logger = logger_instance
        self.agent_name = agent_name

    def on_tool_start(self, serialized, input_str, **kwargs):
        """Called when a tool starts running."""
        tool_name = serialized.get("name", "unknown")
        # Truncate and clean path prefixes for readability
        args = str(input_str)[:450].replace("/tmp/analysis_output/", "./")
        self.logger.debug(f"[{self.agent_name}] [TOOL] {tool_name} | {args}")
