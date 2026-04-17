"""
JSON parsing utilities for robust extraction from LLM responses.
"""

import json
import logging
from typing import Dict, Any, Optional


def extract_json_object(content: str) -> Optional[str]:
    """
    Extract JSON object from content using brace matching.

    Handles nested objects correctly by counting braces and
    respecting string boundaries.

    Args:
        content: String that may contain a JSON object

    Returns:
        Extracted JSON string or None if not found
    """
    start = content.find('{')
    if start == -1:
        return None

    # Count braces to find matching closing brace
    depth = 0
    in_string = False
    escape_next = False

    for i, char in enumerate(content[start:], start):
        if escape_next:
            escape_next = False
            continue

        if char == '\\' and in_string:
            escape_next = True
            continue

        if char == '"' and not escape_next:
            in_string = not in_string
            continue

        if in_string:
            continue

        if char == '{':
            depth += 1
        elif char == '}':
            depth -= 1
            if depth == 0:
                return content[start:i+1]

    # If we didn't find a matching brace, fall back to rfind
    end = content.rfind('}')
    if end > start:
        return content[start:end+1]
    return None


def parse_llm_json_response(
    content: str,
    logger: Optional[logging.Logger] = None
) -> Optional[Dict[str, Any]]:
    """
    Parse JSON from an LLM response, handling various formats.

    Supports:
    - JSON in ```json code blocks
    - JSON in ``` code blocks
    - Raw JSON in text (with proper brace matching)

    Args:
        content: Raw LLM response content
        logger: Optional logger for error messages

    Returns:
        Parsed JSON dict or None if parsing failed
    """
    json_str = None

    try:
        # Try to find JSON in the response
        # Look for JSON block in markdown
        if '```json' in content:
            json_start = content.find('```json') + 7
            json_end = content.find('```', json_start)
            if json_end == -1:
                # Missing closing fence; fall back to brace-matching extraction
                json_str = extract_json_object(content[json_start:])
            else:
                json_str = content[json_start:json_end].strip()
        elif '```' in content:
            json_start = content.find('```') + 3
            json_end = content.find('```', json_start)
            if json_end == -1:
                # Missing closing fence; fall back to brace-matching extraction
                json_str = extract_json_object(content[json_start:])
            else:
                json_str = content[json_start:json_end].strip()
        elif '{' in content:
            # Try to find raw JSON - use brace matching for nested objects
            json_str = extract_json_object(content)
        else:
            if logger:
                logger.error("No JSON found in response")
            return None

        if json_str:
            return json.loads(json_str)
        return None

    except json.JSONDecodeError as e:
        if logger:
            logger.error(f"Failed to parse JSON response: {e}")
            # Log full problematic JSON for debugging
            if json_str:
                logger.debug(f"Problematic JSON (full, {len(json_str)} chars):\n{json_str}")
        return None
