#!/usr/bin/env python3
"""
Grep File Tool - Search for patterns in files

A grep-like tool for searching patterns in log files.
Supports common grep flags: -i, -v, -n, -c, -o, -A, -B, -C, -E, -F

Arguments (CLI mode):
    --input: (Required) Path to the file to search
    --pattern: (Required) Pattern to search for
    --output: (Required) Write results to specified file
    -i, --ignore-case: Case-insensitive matching (default: True)
    -v, --invert-match: Select non-matching lines
    -n, --line-number: Prefix each line with line number
    -c, --count: Only print count of matching lines
    -o, --only-matching: Print only the matched parts
    -A, --after-context: Print NUM lines after match
    -B, --before-context: Print NUM lines before match
    -C, --context: Print NUM lines before and after match
    -E, --extended-regexp: Pattern is an extended regex (default)
    -F, --fixed-strings: Pattern is a literal string

Usage:
    python3 grep_file.py --input test.log --pattern "ERROR|FAIL"
    python3 grep_file.py --input test.log --pattern "error" -i -n -C 3
    python3 grep_file.py --input test.log --pattern "fatal" -c
"""

import argparse
import os
import re
import logging
from pathlib import Path
from typing import List, Optional
from langchain_core.tools import tool


class GrepFile:
    def __init__(self, logger=None):
        self.logger = logger or logging.getLogger(__name__)

    def grep(
        self,
        input_file: str,
        pattern: str,
        output_file: str,
        ignore_case: bool = True,
        invert_match: bool = False,
        line_number: bool = False,
        count_only: bool = False,
        only_matching: bool = False,
        after_context: int = 0,
        before_context: int = 0,
        context: int = 0,
        fixed_strings: bool = False,
        exclude_pattern: str = None
    ) -> dict:
        """
        Search for pattern in a file (grep-like functionality)

        Args:
            input_file: Path to the file to search
            pattern: Pattern to search for (regex or fixed string). Use empty string
                or ".*" to match all lines (useful for exclude-only filtering).
            output_file: Path to write results (required)
            ignore_case: Case-insensitive matching (default True)
            invert_match: Select non-matching lines (-v)
            line_number: Include line numbers (-n)
            count_only: Only return count of matches (-c)
            only_matching: Return only matched portions (-o)
            after_context: Lines to show after match (-A)
            before_context: Lines to show before match (-B)
            context: Lines to show before and after (-C, overrides -A/-B)
            fixed_strings: Treat pattern as literal string (-F)
            exclude_pattern: Regex pattern to exclude from results. Lines matching
                this pattern are removed AFTER the main pattern match. Use regex
                alternation to exclude multiple patterns: "pattern1|pattern2|pattern3".
                Useful for filtering out known false errors from error extraction.

        Returns:
            Dict with status, match count, and output_file path
        """
        try:
            # Validate input file exists
            input_path = Path(input_file)
            if not input_path.exists():
                error_msg = f"File not found: {input_file}"
                self.logger.error(error_msg)
                return {"status": "error", "message": error_msg}

            # Allow exclude-only mode: if pattern is empty/None or ".*", match all lines
            match_all_lines = not pattern or pattern == ".*"
            if not pattern and not exclude_pattern:
                error_msg = "Either pattern or exclude_pattern is required"
                self.logger.error(error_msg)
                return {"status": "error", "message": error_msg}

            self.logger.debug(f"Searching in: {input_file}")
            self.logger.debug(f"Pattern: {pattern or '(match all lines)'}")

            # Handle context flags (-C overrides -A and -B)
            if context > 0:
                after_context = context
                before_context = context

            # Compile pattern
            flags = re.IGNORECASE if ignore_case else 0
            if match_all_lines:
                # In match-all mode, every line matches
                compiled_pattern = None
            elif fixed_strings:
                # Escape regex special characters for literal matching
                compiled_pattern = re.compile(re.escape(pattern), flags)
            else:
                compiled_pattern = re.compile(pattern, flags)

            # Compile exclude pattern if provided
            compiled_exclude = None
            if exclude_pattern:
                self.logger.debug(f"Exclude pattern: {exclude_pattern}")
                if fixed_strings:
                    compiled_exclude = re.compile(re.escape(exclude_pattern), flags)
                else:
                    compiled_exclude = re.compile(exclude_pattern, flags)

            # Read file
            with open(input_file, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()

            # Find matching lines
            matches = []
            match_indices = set()

            for i, line in enumerate(lines):
                # In match-all mode, every line matches initially
                if match_all_lines:
                    line_matches = True
                else:
                    line_matches = bool(compiled_pattern.search(line))

                # Handle invert match
                if invert_match:
                    line_matches = not line_matches

                # Handle exclude pattern (filter out matches)
                if line_matches and compiled_exclude:
                    if compiled_exclude.search(line):
                        line_matches = False

                if line_matches:
                    match_indices.add(i)

                    if only_matching and not invert_match and compiled_pattern:
                        # Extract only the matched portions (skip in match-all mode)
                        found = compiled_pattern.findall(line)
                        for match in found:
                            if line_number:
                                matches.append(f"{i + 1}:{match}")
                            else:
                                matches.append(match)
                    else:
                        if line_number:
                            matches.append(f"{i + 1}:{line.rstrip()}")
                        else:
                            matches.append(line.rstrip())

            total_matches = len(match_indices)
            self.logger.debug(f"Found {total_matches} matching lines")

            # Handle count only
            if count_only:
                result = {
                    "status": "success",
                    "input_file": input_file,
                    "pattern": pattern,
                    "match_count": total_matches
                }
                if output_file:
                    self._write_output(output_file, [str(total_matches)])
                    result["output_file"] = output_file
                return result

            # Handle context lines
            if (before_context > 0 or after_context > 0) and not only_matching:
                matches = self._add_context(
                    lines, match_indices, before_context, after_context, line_number
                )

            # Write to output file (required)
            self._write_output(output_file, matches)
            self.logger.debug(f"Results written to: {output_file}")

            return {
                "status": "success",
                "input_file": input_file,
                "pattern": pattern,
                "match_count": total_matches,
                "output_file": output_file,
                "output_lines": len(matches),
                "output_size_bytes": os.path.getsize(output_file)
            }

        except re.error as e:
            error_msg = f"Invalid regex pattern '{pattern}': {e}"
            self.logger.error(error_msg)
            return {"status": "error", "message": error_msg, "input_file": input_file}
        except Exception as e:
            error_msg = f"Error searching file: {e}"
            self.logger.error(error_msg)
            return {"status": "error", "message": error_msg, "input_file": input_file}

    def _add_context(
        self,
        lines: List[str],
        match_indices: set,
        before: int,
        after: int,
        line_number: bool
    ) -> List[str]:
        """Add context lines around matches"""
        # Build set of all line indices to include
        include_indices = set()
        for idx in match_indices:
            for i in range(max(0, idx - before), min(len(lines), idx + after + 1)):
                include_indices.add(i)

        # Build output with separators between non-contiguous sections
        result = []
        sorted_indices = sorted(include_indices)
        prev_idx = -2

        for idx in sorted_indices:
            # Add separator if there's a gap
            if idx > prev_idx + 1 and prev_idx >= 0:
                result.append("--")

            line = lines[idx].rstrip()
            if line_number:
                # Use : for matches, - for context
                sep = ":" if idx in match_indices else "-"
                result.append(f"{idx + 1}{sep}{line}")
            else:
                result.append(line)

            prev_idx = idx

        return result

    def _write_output(self, output_file: str, lines: List[str]):
        """Write results to output file"""
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, 'w', encoding='utf-8') as f:
            for line in lines:
                f.write(line + '\n')


@tool
def grep_file(
    input_file: str,
    output_file: str,
    pattern: str = "",
    ignore_case: bool = True,
    invert_match: bool = False,
    line_number: bool = False,
    count_only: bool = False,
    only_matching: bool = False,
    context: int = 0,
    fixed_strings: bool = False,
    exclude_pattern: Optional[str] = None
) -> dict:
    """Search for pattern in a file (grep-like functionality).

    Searches a file for lines matching a regex pattern. Supports common grep
    options like case-insensitive search, inverted matching, line numbers,
    and context lines. Results are written to output_file.

    Can also be used in EXCLUDE-ONLY MODE: omit the pattern (or use ".*") to
    match all lines, then use exclude_pattern to filter out unwanted lines.

    Args:
        input_file: Path to the file to search.
        output_file: Path to write matching lines (required).
        pattern: Regex pattern to search for (e.g., "error|fail|exception").
            Use empty string or ".*" to match all lines (exclude-only mode).
        ignore_case: Case-insensitive matching (default: True).
        invert_match: Select lines that do NOT match the pattern.
        line_number: Prefix each output line with its line number.
        count_only: Only return the count of matching lines, not the lines.
        only_matching: Return only the matched text, not full lines.
        context: Number of lines to show before and after each match.
        fixed_strings: Treat pattern as literal string, not regex.
        exclude_pattern: Regex pattern to exclude from results. Lines matching
            this pattern are removed AFTER the main pattern match. Use regex
            alternation to exclude multiple patterns: "pattern1|pattern2|pattern3".
            Useful for filtering out known false errors from error extraction.

    Returns:
        dict: Contains:
            - status: "success" or "error"
            - input_file: The searched file path
            - pattern: The pattern used
            - match_count: Number of matching lines
            - output_file: Path where results were written
            - output_lines: Number of lines written to output file
            - output_size_bytes: Size of output file in bytes
            - message: Error description (on failure)

    Note:
        Results are written to output_file. Use read_file tool to access matching lines.
    """
    logger = logging.getLogger('agent')
    grep = GrepFile(logger=logger)
    return grep.grep(
        input_file=input_file,
        pattern=pattern,
        output_file=output_file,
        ignore_case=ignore_case,
        invert_match=invert_match,
        line_number=line_number,
        count_only=count_only,
        only_matching=only_matching,
        context=context,
        fixed_strings=fixed_strings,
        exclude_pattern=exclude_pattern
    )


def main():
    """Main function for standalone CLI usage"""
    parser = argparse.ArgumentParser(
        description='Search for patterns in files (grep-like)',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('--input', '-f', required=True, help='Input file to search')
    parser.add_argument('--pattern', '-e', required=True, help='Pattern to search for')
    parser.add_argument('--output', '-o', required=True, help='Output file for results')
    parser.add_argument('-i', '--ignore-case', action='store_true', default=True,
                        help='Case-insensitive matching (default)')
    parser.add_argument('--case-sensitive', action='store_true',
                        help='Case-sensitive matching')
    parser.add_argument('-v', '--invert-match', action='store_true',
                        help='Select non-matching lines')
    parser.add_argument('-n', '--line-number', action='store_true',
                        help='Prefix lines with line number')
    parser.add_argument('-c', '--count', action='store_true',
                        help='Only print count of matching lines')
    parser.add_argument('-m', '--only-matching', action='store_true',
                        help='Print only the matched parts')
    parser.add_argument('-A', '--after-context', type=int, default=0,
                        help='Print NUM lines after match')
    parser.add_argument('-B', '--before-context', type=int, default=0,
                        help='Print NUM lines before match')
    parser.add_argument('-C', '--context', type=int, default=0,
                        help='Print NUM lines before and after match')
    parser.add_argument('-F', '--fixed-strings', action='store_true',
                        help='Treat pattern as literal string')
    parser.add_argument('-x', '--exclude', dest='exclude_pattern',
                        help='Exclude lines matching this pattern')

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')

    # Handle case sensitivity (--case-sensitive overrides -i)
    ignore_case = not args.case_sensitive

    # Handle context (use -C if set, otherwise use max of -A/-B)
    ctx = args.context if args.context > 0 else max(args.before_context, args.after_context)

    result = grep_file.invoke({
        "input_file": args.input,
        "pattern": args.pattern,
        "output_file": args.output,
        "ignore_case": ignore_case,
        "invert_match": args.invert_match,
        "line_number": args.line_number,
        "count_only": args.count,
        "only_matching": args.only_matching,
        "context": ctx,
        "fixed_strings": args.fixed_strings,
        "exclude_pattern": args.exclude_pattern
    })

    print("\n" + "=" * 80)
    print("GREP RESULTS")
    print("=" * 80)

    if result["status"] == "success":
        print(f"File: {result['input_file']}")
        print(f"Pattern: {result['pattern']}")
        print(f"Matches: {result['match_count']}")
        print(f"Output: {result['output_file']}")

        if not args.count:
            print("-" * 80)
            print(f"Results saved to: {result['output_file']}")
            print("Use 'cat' or 'head' to view results")
    else:
        print(f"❌ Error: {result['message']}")

    print("=" * 80)


if __name__ == "__main__":
    main()
