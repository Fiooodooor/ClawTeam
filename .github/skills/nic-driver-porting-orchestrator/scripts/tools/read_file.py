#!/usr/bin/env python3
"""
Read File Tool for LangChain Agent

This tool allows the agent to read file contents with optional line filtering.

Arguments (CLI mode):
    FILE_PATH: (Required) Path to the file to read
    -s, --start-line: Start reading from this line (1-based)
    -e, --end-line: Stop reading at this line (1-based, inclusive)
    -t, --tail: Read last N lines only
    -H, --head: Read first N lines only
    -m, --max-lines: Maximum lines to return (default: 1000)
    -n, --line-numbers: Prefix each line with line number

Usage:
    python3 read_file.py test.log
    python3 read_file.py test.log -s 100 -e 200
    python3 read_file.py test.log --tail 50 -n
    python3 read_file.py test.log --head 100 --line-numbers
"""

import argparse
import logging
from collections import deque
from itertools import islice
from pathlib import Path
from typing import Optional, List, Tuple
from langchain_core.tools import tool


class FileReader:
    """
    Memory-efficient file reader with line range and filtering support.

    Optimizations:
    - tail: Uses deque with maxlen for O(N) memory (N = tail size)
    - head: Uses islice for early termination
    - line range: Uses islice to skip without storing
    """

    DEFAULT_MAX_LINES = 1000

    def __init__(self, logger=None):
        self.logger = logger or logging.getLogger(__name__)

    def _count_lines(self, file_path: str) -> int:
        """Count total lines in file efficiently."""
        count = 0
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            for _ in f:
                count += 1
        return count

    def _read_tail(self, file_path: str, n: int) -> Tuple[List[str], int, int]:
        """
        Read last N lines using deque - O(N) memory.
        Returns (lines, start_line_number, total_lines)
        """
        total_lines = 0
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            # deque with maxlen keeps only last N items
            tail_lines = deque(f, maxlen=n)
            # Count total by re-reading (or we can count during deque)

        # Need total count for line numbers - count efficiently
        total_lines = self._count_lines(file_path)
        start_idx = max(0, total_lines - len(tail_lines))

        return list(tail_lines), start_idx, total_lines

    def _read_head(self, file_path: str, n: int, max_lines: int) -> Tuple[List[str], int]:
        """
        Read first N lines using islice - stops reading early.
        Returns (lines, total_lines)
        """
        # Read only what we need
        limit = min(n, max_lines)
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            head_lines = list(islice(f, limit))

        # Get total count for metadata
        total_lines = self._count_lines(file_path)

        return head_lines, total_lines

    def _read_range(self, file_path: str, start: int, end: Optional[int], max_lines: int) -> Tuple[List[str], int, int]:
        """
        Read line range using islice - skips without storing.
        start/end are 1-based.
        Returns (lines, start_idx, total_lines)
        """
        start_idx = max(0, start - 1)  # Convert to 0-based

        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            if end is not None:
                # Read specific range: skip to start, take (end - start + 1) lines
                count = end - start + 1
                limit = min(count, max_lines)
                selected = list(islice(f, start_idx, start_idx + limit))
            else:
                # Read from start to max_lines
                selected = list(islice(f, start_idx, start_idx + max_lines))

        total_lines = self._count_lines(file_path)

        return selected, start_idx, total_lines

    def _read_full(self, file_path: str, max_lines: int) -> Tuple[List[str], int]:
        """
        Read full file up to max_lines.
        Returns (lines, total_lines)
        """
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = list(islice(f, max_lines))

        total_lines = self._count_lines(file_path)

        return lines, total_lines

    def read_file(
        self,
        file_path: str,
        start_line: Optional[int] = None,
        end_line: Optional[int] = None,
        tail: Optional[int] = None,
        head: Optional[int] = None,
        max_lines: int = DEFAULT_MAX_LINES,
        line_numbers: bool = False
    ) -> dict:
        """
        Read file contents with optional line filtering (memory-efficient).

        Args:
            file_path: Path to the file to read
            start_line: Start reading from this line (1-based)
            end_line: Stop reading at this line (1-based, inclusive)
            tail: Read last N lines only (overrides start_line/end_line)
            head: Read first N lines only (overrides start_line/end_line)
            max_lines: Maximum lines to return (default: 1000)
            line_numbers: Prefix each line with line number

        Returns:
            Dict with status, content, and metadata
        """
        try:
            # Validate file exists
            path = Path(file_path)
            if not path.exists():
                return {
                    "status": "error",
                    "message": f"File not found: {file_path}"
                }

            self.logger.debug(f"Reading file: {file_path}")

            # Determine read mode and get lines efficiently
            truncated = False

            if tail is not None:
                # OPTIMIZED: Use deque for O(N) memory
                self.logger.debug(f"Reading tail: last {tail} lines")
                selected_lines, start_idx, total_lines = self._read_tail(file_path, tail)

                # Apply max_lines limit
                if len(selected_lines) > max_lines:
                    selected_lines = selected_lines[:max_lines]
                    truncated = True

            elif head is not None:
                # OPTIMIZED: Use islice for early termination
                self.logger.debug(f"Reading head: first {head} lines")
                selected_lines, total_lines = self._read_head(file_path, head, max_lines)
                start_idx = 0
                truncated = len(selected_lines) < head and len(selected_lines) >= max_lines

            elif start_line is not None:
                # OPTIMIZED: Use islice to skip without storing
                self.logger.debug(f"Reading range: lines {start_line}-{end_line or 'end'}")
                selected_lines, start_idx, total_lines = self._read_range(
                    file_path, start_line, end_line, max_lines
                )
                expected_count = (end_line - start_line + 1) if end_line else max_lines
                truncated = len(selected_lines) >= max_lines and expected_count > max_lines

            else:
                # Full file read (with max_lines limit)
                self.logger.debug(f"Reading full file (max {max_lines} lines)")
                selected_lines, total_lines = self._read_full(file_path, max_lines)
                start_idx = 0
                truncated = total_lines > max_lines

            self.logger.debug(f"File has {total_lines} lines, returning {len(selected_lines)}")

            if truncated:
                self.logger.warning(f"Output truncated to {max_lines} lines")

            # Format output
            if line_numbers:
                # Add line numbers (1-based, relative to original file)
                formatted_lines = []
                for i, line in enumerate(selected_lines):
                    line_num = start_idx + i + 1
                    formatted_lines.append(f"{line_num}: {line}")
                content = ''.join(formatted_lines)
            else:
                content = ''.join(selected_lines)

            # Build result
            result = {
                "status": "success",
                "file_path": file_path,
                "total_lines": total_lines,
                "lines_returned": len(selected_lines),
                "line_range": f"{start_idx + 1}-{start_idx + len(selected_lines)}",
                "truncated": truncated,
                "content": content
            }

            if truncated:
                result["truncated_message"] = f"Output limited to {max_lines} lines. Use start_line/end_line for specific ranges."

            return result

        except Exception as e:
            error_msg = f"Error reading file {file_path}: {e}"
            self.logger.error(error_msg)
            return {
                "status": "error",
                "message": error_msg
            }


@tool
def read_file(
    file_path: str,
    start_line: Optional[int] = None,
    end_line: Optional[int] = None,
    tail: Optional[int] = None,
    head: Optional[int] = None,
    max_lines: int = 1000,
    line_numbers: bool = False
) -> dict:
    """Read contents of a text file with optional line filtering.

    Reads file contents with support for line ranges, head/tail, and line numbers.
    Useful for reading specific sections of large log files.

    Args:
        file_path: Full path to the file to read.
        start_line: Start reading from this line number (1-based). Use with end_line for ranges.
        end_line: Stop reading at this line number (1-based, inclusive).
        tail: Read only the last N lines. Overrides start_line/end_line.
        head: Read only the first N lines. Overrides start_line/end_line.
        max_lines: Maximum lines to return (default: 1000). Safety limit.
        line_numbers: If True, prefix each line with its line number.

    Returns:
        dict: {
            "status": "success" or "error",
            "file_path": path to file,
            "total_lines": total lines in file,
            "lines_returned": number of lines returned,
            "line_range": "start-end" range of lines returned,
            "truncated": True if output was truncated,
            "content": file content as string
        }
    """
    reader = FileReader(logging.getLogger('agent'))
    return reader.read_file(
        file_path=file_path,
        start_line=start_line,
        end_line=end_line,
        tail=tail,
        head=head,
        max_lines=max_lines,
        line_numbers=line_numbers
    )


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description='Read file contents with optional line filtering',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 read_file.py test.log                    # Read entire file (max 1000 lines)
  python3 read_file.py test.log -s 100 -e 200      # Read lines 100-200
  python3 read_file.py test.log --tail 50          # Read last 50 lines
  python3 read_file.py test.log --head 100 -n      # Read first 100 lines with line numbers
  python3 read_file.py test.log -s 500 -e 600 -n   # Read lines 500-600 with line numbers
        """
    )
    parser.add_argument('file_path', help='Path to the file to read')
    parser.add_argument('-s', '--start-line', type=int, help='Start line (1-based)')
    parser.add_argument('-e', '--end-line', type=int, help='End line (1-based, inclusive)')
    parser.add_argument('-t', '--tail', type=int, help='Read last N lines')
    parser.add_argument('-H', '--head', type=int, help='Read first N lines')
    parser.add_argument('-m', '--max-lines', type=int, default=1000, help='Max lines to return (default: 1000)')
    parser.add_argument('-n', '--line-numbers', action='store_true', help='Show line numbers')

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')

    # Run reader
    reader = FileReader()
    result = reader.read_file(
        file_path=args.file_path,
        start_line=args.start_line,
        end_line=args.end_line,
        tail=args.tail,
        head=args.head,
        max_lines=args.max_lines,
        line_numbers=args.line_numbers
    )

    # Output
    if result["status"] == "error":
        print(f"Error: {result['message']}")
        exit(1)

    print(f"\n{'='*80}")
    print(f"FILE: {result['file_path']}")
    print(f"TOTAL LINES: {result['total_lines']} | RETURNED: {result['lines_returned']} | RANGE: {result['line_range']}")
    if result.get('truncated'):
        print(f"⚠ TRUNCATED: {result.get('truncated_message', 'Output was truncated')}")
    print('='*80)
    print(result['content'])
    print('='*80)


if __name__ == "__main__":
    main()
