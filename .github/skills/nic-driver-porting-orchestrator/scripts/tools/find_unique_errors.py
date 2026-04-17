#!/usr/bin/env python3
"""
Find Unique Errors in Failed Test

This tool compares error files from failed and passed tests to identify
errors unique to the failed test (true failure indicators).

Arguments (CLI mode):
    --failed-errors: (Required) File containing errors from failed test
    --passed-errors: (Required) File containing errors from passed test
    --output: (Optional) Write results to specified file
    --strip-timestamps: (Optional) Strip timestamps before comparison

Usage:
    python3 find_unique_errors.py --failed-errors failed.txt --passed-errors passed.txt --output unique.txt
    python3 find_unique_errors.py --failed-errors failed.txt --passed-errors passed.txt --strip-timestamps
"""

import argparse
import logging
import os
import re
from pathlib import Path
from langchain_core.tools import tool


# Timestamp patterns for different log formats
# HTML logs: <td>MM-DD HH:MM</td>
HTML_TIMESTAMP_PATTERN = re.compile(r'<td>\d{2}-\d{2} \d{2}:\d{2}</td>')
# Text logs: [DD-MM-YYYY HH:MM:SS]:
TEXT_TIMESTAMP_PATTERN = re.compile(r'\[\d{2}-\d{2}-\d{4} \d{2}:\d{2}:\d{2}\]:\s*')


def strip_timestamp(line: str) -> str:
    """Strip timestamps from a log line for comparison.

    Supports:
    - HTML format: <td>12-30 13:02</td> -> <td></td>
    - Text format: [30-12-2025 13:02:32]: -> (removed)
    """
    # Try HTML pattern first
    result = HTML_TIMESTAMP_PATTERN.sub('<td></td>', line)
    # Then text log pattern
    result = TEXT_TIMESTAMP_PATTERN.sub('', result)
    return result


class UniqueErrorFinder:
    def __init__(self, logger=None):
        self.logger = logger or logging.getLogger(__name__)

    def find_unique_errors(self, failed_errors_file: str, passed_errors_file: str,
                           output_file: str = None, strip_timestamps: bool = False) -> dict:
        """
        Find errors unique to the failed test log

        Args:
            failed_errors_file: File containing errors from failed test
            passed_errors_file: File containing errors from passed test
            output_file: Optional path to write unique errors
            strip_timestamps: If True, strip timestamps before comparison

        Returns:
            Dict with status, unique error count, and error lines
        """
        try:
            # Validate files exist
            failed_path = Path(failed_errors_file)
            passed_path = Path(passed_errors_file)

            if not failed_path.exists():
                error_msg = f"Failed errors file not found: {failed_errors_file}"
                self.logger.error(error_msg)
                return {"status": "error", "message": error_msg}

            if not passed_path.exists():
                error_msg = f"Passed errors file not found: {passed_errors_file}"
                self.logger.error(error_msg)
                return {"status": "error", "message": error_msg}

            self.logger.debug(f"Comparing failed errors: {failed_errors_file}")
            self.logger.debug(f"Against passed errors: {passed_errors_file}")
            if strip_timestamps:
                self.logger.debug("Timestamp stripping enabled for comparison")

            # Read error lines (preserve order for failed, use set for passed)
            with open(failed_errors_file, 'r', encoding='utf-8', errors='ignore') as f:
                failed_lines = [line.strip() for line in f if line.strip()]

            with open(passed_errors_file, 'r', encoding='utf-8', errors='ignore') as f:
                passed_lines = [line.strip() for line in f if line.strip()]

            # Apply timestamp stripping if requested
            if strip_timestamps:
                # For comparison, strip timestamps but keep original lines for output
                failed_normalized = [strip_timestamp(line) for line in failed_lines]
                passed_normalized = set(strip_timestamp(line) for line in passed_lines)

                # Find unique errors by comparing normalized versions
                unique_errors = [
                    failed_lines[i] for i, norm in enumerate(failed_normalized)
                    if norm not in passed_normalized
                ]
            else:
                # Original exact comparison
                passed_set = set(passed_lines)
                unique_errors = [err for err in failed_lines if err not in passed_set]

            self.logger.debug(f"Failed test errors: {len(failed_lines)}")
            self.logger.debug(f"Passed test errors: {len(passed_lines)}")
            self.logger.debug(f"Unique to failed test: {len(unique_errors)}")

            # Write to output file if specified
            if output_file:
                output_path = Path(output_file)
                output_path.parent.mkdir(parents=True, exist_ok=True)
                with open(output_file, 'w', encoding='utf-8') as f:
                    for error in unique_errors:
                        f.write(error + '\n')
                self.logger.debug(f"Unique errors written to: {output_file}")

            return {
                "status": "success",
                "failed_errors_file": failed_errors_file,
                "passed_errors_file": passed_errors_file,
                "failed_error_count": len(failed_lines),
                "passed_error_count": len(passed_lines),
                "unique_error_count": len(unique_errors),
                "strip_timestamps": strip_timestamps,
                "output_file": output_file,
                "output_lines": len(unique_errors),
                "output_size_bytes": os.path.getsize(output_file) if output_file else 0
            }

        except Exception as e:
            error_msg = f"Error finding unique errors: {e}"
            self.logger.error(error_msg)
            return {
                "status": "error",
                "message": error_msg
            }


@tool
def find_unique_errors(failed_errors_file: str, passed_errors_file: str,
                       output_file: str = None, strip_timestamps: bool = False) -> dict:
    """Find errors unique to one file by comparing against a reference file.

    Compares two error files and identifies lines present in the first file
    but not in the second. Useful for filtering out known/expected errors.

    By default, this tool performs EXACT string comparison. Use strip_timestamps=True
    when comparing logs that contain timestamps to avoid false matches from
    timestamp differences (same error appearing at different times).

    Supported timestamp formats when strip_timestamps=True:
    - HTML logs: <td>MM-DD HH:MM</td>
    - Text logs: [DD-MM-YYYY HH:MM:SS]:

    Args:
        failed_errors_file: Path to file containing errors to analyze.
        passed_errors_file: Path to reference file with known/expected errors.
        output_file: Optional path to write unique errors.
        strip_timestamps: If True, strip timestamps before comparison to avoid
            false matches from same errors occurring at different times.

    Returns:
        dict: Contains:
            - status: "success" or "error"
            - failed_error_count: Total errors in first file
            - passed_error_count: Total errors in reference file
            - unique_error_count: Errors only in first file
            - strip_timestamps: Whether timestamps were stripped
            - output_file: Path where results were written (if specified)
            - output_lines: Number of lines written to output file
            - output_size_bytes: Size of output file in bytes
            - message: Error description (on failure)

        Note: Use read_file tool to read actual content from output_file.
    """
    logger = logging.getLogger('agent')
    finder = UniqueErrorFinder(logger=logger)
    return finder.find_unique_errors(failed_errors_file, passed_errors_file, output_file, strip_timestamps)


def main():
    """Main function for standalone CLI usage"""
    parser = argparse.ArgumentParser(description='Find unique errors in failed test')
    parser.add_argument('--failed-errors', required=True, help='Failed test errors file')
    parser.add_argument('--passed-errors', required=True, help='Passed test errors file')
    parser.add_argument('--output', help='Output file path')
    parser.add_argument('--strip-timestamps', action='store_true',
                        help='Strip timestamps before comparison')
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')

    result = find_unique_errors.invoke({
        "failed_errors_file": args.failed_errors,
        "passed_errors_file": args.passed_errors,
        "output_file": args.output,
        "strip_timestamps": args.strip_timestamps
    })

    print("\n" + "="*80)
    print("UNIQUE ERROR ANALYSIS")
    print("="*80)
    if result["status"] == "success":
        print(f"✅ Found {result['unique_error_count']} unique errors in failed test")
        print(f"   Failed test total: {result['failed_error_count']}")
        print(f"   Passed test total: {result['passed_error_count']}")
        if result["output_file"]:
            print(f"   Output: {result['output_file']}")
    else:
        print(f"❌ Error: {result['message']}")
    print("="*80)


if __name__ == "__main__":
    main()
