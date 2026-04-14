#!/usr/bin/env python3
"""
Extract Archive File

This tool extracts archive files (7z, zip, tar, etc.) to a specified directory.
Can be used as a standalone script or imported as a LangChain tool.

Arguments (CLI mode):
    --archive: (Required) Full path to the archive file
    --output-dir: (Required) Directory to extract files into

Usage:
    python3 extract_archive.py --archive "/tmp/file.7z" --output-dir "/tmp/output"

Examples:
    python3 extract_archive.py --archive "/tmp/Logs-test.7z" --output-dir "/tmp/extracted"
"""

import argparse
import os
import logging
from pathlib import Path
import py7zr
from langchain_core.tools import tool


class ArchiveExtractor:
    def __init__(self, logger=None):
        self.logger = logger or logging.getLogger(__name__)

    def extract_archive(self, archive_path: str, output_dir: str) -> dict:
        """
        Extract an archive file to a specified directory

        Args:
            archive_path: Full path to the archive file
            output_dir: Directory to extract files into

        Returns:
            Dict with status, extracted files list, and metadata
        """
        try:
            # Validate archive exists
            archive_file = Path(archive_path)
            if not archive_file.exists():
                error_msg = f"Archive file not found: {archive_path}"
                self.logger.error(error_msg)
                return {
                    "status": "error",
                    "message": error_msg
                }

            # Create output directory if needed
            output_path = Path(output_dir)
            output_path.mkdir(parents=True, exist_ok=True)

            archive_name = archive_file.name
            self.logger.debug(f"Extracting: {archive_name}")
            self.logger.debug(f"From: {archive_path}")
            self.logger.debug(f"To: {output_dir}")

            # Extract based on file extension
            extracted_files = []

            if archive_path.endswith('.7z'):
                # Extract 7z archive
                with py7zr.SevenZipFile(archive_path, mode='r') as archive:
                    archive.extractall(path=output_dir)
                    extracted_files = archive.getnames()
            else:
                error_msg = f"Unsupported archive format: {archive_name}"
                self.logger.error(error_msg)
                return {
                    "status": "error",
                    "message": error_msg
                }

            self.logger.debug(f"Extraction complete: {len(extracted_files)} files")
            self.logger.debug(f"Extracted to: {output_dir}")

            return {
                "status": "success",
                "archive_name": archive_name,
                "extracted_to": output_dir,
                "files_count": len(extracted_files)
            }

        except py7zr.Bad7zFile as e:
            error_msg = f"Invalid 7z archive format: {e}"
            self.logger.error(error_msg)
            return {
                "status": "error",
                "message": error_msg,
                "archive_path": archive_path
            }
        except Exception as e:
            error_msg = f"Error extracting archive: {e}"
            self.logger.error(error_msg)
            return {
                "status": "error",
                "message": error_msg,
                "archive_path": archive_path
            }


@tool
def extract_archive(archive_path: str, output_dir: str) -> dict:
    """Extract contents of an archive file to a local directory.

    Extracts compressed archive files to the specified output directory.
    Currently supports 7z format. Creates output directory if needed.

    Args:
        archive_path: Full local path to the archive file.
        output_dir: Directory path where contents will be extracted.

    Returns:
        dict: Contains:
            - status: "success" or "error"
            - extracted_to: Path where files were extracted
            - files_count: Number of files extracted
            - archive_name: Name of the source archive
            - message: Error description (on failure)
    """
    logger = logging.getLogger('agent')
    extractor = ArchiveExtractor(logger=logger)
    return extractor.extract_archive(archive_path, output_dir)


def main():
    """Main function for standalone CLI usage"""
    parser = argparse.ArgumentParser(
        description='Extract archive file',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        '--archive',
        type=str,
        required=True,
        help='Full path to the archive file'
    )

    parser.add_argument(
        '--output-dir',
        type=str,
        required=True,
        help='Directory to extract files into'
    )

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(levelname)s - %(message)s'
    )

    # Extract archive
    result = extract_archive.invoke({
        "archive_path": args.archive,
        "output_dir": args.output_dir
    })

    print("\n" + "="*80)
    print("EXTRACTION RESULT")
    print("="*80)
    if result["status"] == "success":
        print(f"✅ Success: Extracted {result['files_count']} files")
        print(f"   Output: {result['extracted_to']}")
    else:
        print(f"❌ Error: {result['message']}")
    print("="*80)


if __name__ == "__main__":
    main()
