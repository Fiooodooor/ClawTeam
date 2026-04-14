#!/usr/bin/env python3
"""
Filter Pattern Context

Searches for a pattern in a file and extracts surrounding context lines for each match.
Writes matching contexts to an output file and returns metadata.

Arguments (CLI mode):
    --input-file: (Required) Path to the file to search
    --output-file: (Required) Path to write the context results
    --pattern: (Required) Pattern to search for (regex supported)
    --before: (Optional) Number of lines before match (default: 5)
    --after: (Optional) Number of lines after match (default: 5)
    --max-matches: (Optional) Maximum matches to extract (default: 50)

Usage:
    python3 filter_pattern_context.py --input-file test.log --output-file contexts.txt --pattern "ERROR|FAIL"
    python3 filter_pattern_context.py --input-file data.txt --output-file out.txt --pattern "timeout" --before 10 --after 5
"""

import argparse
import os
import re
import logging
from pathlib import Path
from langchain_core.tools import tool


class PatternContextFilter:
    def __init__(self, logger=None):
        self.logger = logger or logging.getLogger(__name__)

    def filter_pattern_context(
        self,
        input_file: str,
        output_file: str,
        pattern: str,
        lines_before: int = 5,
        lines_after: int = 5,
        max_matches: int = 50
    ) -> dict:
        """
        Search for pattern and extract surrounding context for each match.
        Writes contexts to output file and returns metadata.
        """
        try:
            file_path = Path(input_file)
            if not file_path.exists():
                return {"status": "error", "message": f"File not found: {input_file}"}

            if not pattern:
                return {"status": "error", "message": "Pattern is required"}

            if not output_file:
                return {"status": "error", "message": "Output file is required"}

            self.logger.debug(f"Searching in: {input_file}")
            self.logger.debug(f"Pattern: {pattern}")

            try:
                compiled_pattern = re.compile(pattern, re.IGNORECASE)
            except re.error as e:
                return {"status": "error", "message": f"Invalid regex pattern '{pattern}': {e}"}

            with open(input_file, 'r', encoding='utf-8', errors='ignore') as f:
                file_lines = f.readlines()

            total_lines = len(file_lines)

            # Find all matching line indices
            match_indices = [i for i, line in enumerate(file_lines) if compiled_pattern.search(line)]

            self.logger.debug(f"Found {len(match_indices)} matches")

            # Extract context for each match (up to max_matches)
            contexts = []
            for idx in match_indices[:max_matches]:
                start_idx = max(0, idx - lines_before)
                end_idx = min(total_lines, idx + lines_after + 1)
                context_text = ''.join(file_lines[start_idx:end_idx]).rstrip()
                contexts.append(context_text)

            # Write contexts to output file
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            with open(output_file, 'w', encoding='utf-8') as f:
                output_line_count = 0
                for i, ctx in enumerate(contexts, 1):
                    f.write(f"--- Match {i} ---\n")
                    output_line_count += 1
                    f.write(ctx)
                    output_line_count += ctx.count('\n') + 1
                    f.write("\n\n")
                    output_line_count += 2

            self.logger.debug(f"Contexts written to: {output_file}")

            return {
                "status": "success",
                "input_file": input_file,
                "pattern": pattern,
                "match_count": len(match_indices),
                "contexts_extracted": len(contexts),
                "output_file": output_file,
                "output_lines": output_line_count,
                "output_size_bytes": os.path.getsize(output_file)
            }

        except Exception as e:
            return {"status": "error", "message": str(e)}


@tool
def filter_pattern_context(
    input_file: str,
    output_file: str,
    pattern: str,
    lines_before: int = 5,
    lines_after: int = 5,
    max_matches: int = 50
) -> dict:
    """Search for a pattern in a file and write surrounding context for each match to output file.

    Args:
        input_file: Path to the file to search.
        output_file: Path to write the context results.
        pattern: Regex pattern to search for (case-insensitive).
        lines_before: Lines to include before match (default: 5).
        lines_after: Lines to include after match (default: 5).
        max_matches: Maximum matches to extract (default: 50).

    Returns:
        dict: Contains:
            - status: "success" or "error"
            - input_file: Path to the input file
            - pattern: The search pattern used
            - match_count: Total matches found in the file
            - contexts_extracted: Number of contexts written to output file
            - output_file: Path to the output file with contexts
            - output_lines: Number of lines written to output file
            - output_size_bytes: Size of output file in bytes
            - message: Error description (on failure)
    """
    logger = logging.getLogger('agent')
    extractor = PatternContextFilter(logger=logger)
    return extractor.filter_pattern_context(input_file, output_file, pattern, lines_before, lines_after, max_matches)


def main():
    parser = argparse.ArgumentParser(description='Filter pattern context from files')
    parser.add_argument('--input-file', required=True, help='Path to the input file')
    parser.add_argument('--output-file', required=True, help='Path to write context results')
    parser.add_argument('--pattern', required=True, help='Regex pattern to search for')
    parser.add_argument('--before', type=int, default=5, help='Lines before match (default: 5)')
    parser.add_argument('--after', type=int, default=5, help='Lines after match (default: 5)')
    parser.add_argument('--max-matches', type=int, default=50, help='Max matches (default: 50)')
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')

    result = filter_pattern_context.invoke({
        "input_file": args.input_file,
        "output_file": args.output_file,
        "pattern": args.pattern,
        "lines_before": args.before,
        "lines_after": args.after,
        "max_matches": args.max_matches
    })

    print("\n" + "=" * 80)
    if result["status"] == "success":
        print(f"✅ Found {result['match_count']} matches, extracted {result['contexts_extracted']} contexts")
        print(f"📄 Output written to: {result['output_file']}")
    else:
        print(f"❌ Error: {result['message']}")
    print("=" * 80)


if __name__ == "__main__":
    main()
