#!/usr/bin/env python3
"""
Browse Artifactory Directory

This script lists files in an Artifactory URL and optionally filters results.
Can be used as a standalone script or imported as a LangChain tool.

Arguments (CLI mode):
    --url: (Required) Full Artifactory URL to browse
    --filter: (Optional) Pattern to filter results
    --output: (Optional) JSON output file path

Environment Variables Required:
    ARTIFACTORY_TOKEN: Artifactory API token for authentication

Usage:
    python3 browse_artifactory.py --url "https://ubit-artifactory-or.intel.com/..." --filter "test_name"
    python3 browse_artifactory.py --url "https://ubit-artifactory-or.intel.com/..." --output results.json

Examples:
    python3 browse_artifactory.py --url "https://ubit-artifactory-or.intel.com/artifactory/snic_fw_ci-or-local/..."
"""

import argparse
import json
import os
import sys
import logging
import requests
from typing import List, Dict, Optional
from dotenv import load_dotenv
from langchain_core.tools import tool

# Load environment variables
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.env'))


class ArtifactoryBrowser:
    def __init__(self, logger=None):
        self.logger = logger or logging.getLogger(__name__)
        self.artifactory_token = os.getenv('ARTIFACTORY_TOKEN')
        # SSL verification - can be disabled for corporate proxies
        self.verify_ssl = os.getenv('ARTIFACTORY_VERIFY_SSL', 'true').lower() != 'false'

        if not self.artifactory_token:
            self.logger.warning("ARTIFACTORY_TOKEN not set in environment")

    def browse_directory(self, url: str, filter_pattern: Optional[str] = None) -> Dict:
        """
        Browse Artifactory directory and list files

        Args:
            url: Full Artifactory URL to browse
            filter_pattern: Optional pattern to filter results (case-insensitive)

        Returns:
            Dict with status, file list, and metadata
        """
        if not self.artifactory_token:
            return {
                "status": "error",
                "message": "ARTIFACTORY_TOKEN not set in environment variables"
            }

        # Ensure URL ends with /
        if not url.endswith('/'):
            url = url + '/'

        self.logger.debug(f"Browsing Artifactory URL: {url}")
        if filter_pattern:
            self.logger.debug(f"Filter pattern: {filter_pattern}")

        try:
            # Make request to Artifactory
            headers = {
                'X-JFrog-Art-Api': self.artifactory_token
            }

            response = requests.get(url, headers=headers, timeout=30, verify=self.verify_ssl)
            response.raise_for_status()

            content = response.text
            lines = content.strip().split('\n')

            # Filter if pattern provided
            if filter_pattern:
                filtered_lines = [line for line in lines if filter_pattern.lower() in line.lower()]
                self.logger.debug(f"Found {len(filtered_lines)} items matching filter (out of {len(lines)} total)")
                result_lines = filtered_lines
            else:
                self.logger.debug(f"Found {len(lines)} items")
                result_lines = lines

            # Parse lines to extract file information
            files = []
            for line in result_lines:
                # Simple parsing - each line is typically a file/directory reference
                if line.strip():
                    files.append(line.strip())

            return {
                "status": "success",
                "url": url,
                "filter_pattern": filter_pattern,
                "total_items": len(lines),
                "filtered_items": len(result_lines),
                "files": files
            }

        except requests.exceptions.RequestException as e:
            error_msg = f"Failed to browse Artifactory: {e}"
            self.logger.error(error_msg)
            return {
                "status": "error",
                "message": error_msg,
                "url": url
            }
        except Exception as e:
            error_msg = f"Unexpected error: {e}"
            self.logger.error(error_msg)
            return {
                "status": "error",
                "message": error_msg,
                "url": url
            }

    def export_results(self, data: Dict, output_file: str) -> Optional[str]:
        """Export browse results to JSON file"""
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return output_file
        except Exception as e:
            self.logger.error(f"Error exporting results: {e}")
            return None


@tool
def browse_artifactory(url: str, filter_pattern: str = "", output_path: str = "") -> str:
    """List contents of an Artifactory directory.

    Retrieves a listing of files and subdirectories at the specified Artifactory URL.
    Supports optional filtering and JSON export.

    Args:
        url: Full Artifactory URL to browse (must be a directory, not a file).
        filter_pattern: Optional case-insensitive substring to filter results.
        output_path: Optional local directory path to save results as JSON file.
                     The filename is auto-generated from the URL.

    Returns:
        str: JSON string containing:
            - status: "success" or "error"
            - url: The browsed URL
            - files: List of file/directory names (directories end with '/')
            - total_items: Count before filtering
            - filtered_items: Count after filtering
            - output_file: Path to saved JSON file (only when output_path provided)
            - message: Error description (on failure)

    Environment:
        Requires ARTIFACTORY_TOKEN environment variable.
    """
    # Get logger from the calling context
    logger = logging.getLogger('agent')

    try:
        # Create browser with logger
        browser = ArtifactoryBrowser(logger=logger)

        # Browse directory
        result = browser.browse_directory(url, filter_pattern if filter_pattern else None)

        # Export to file if output_path provided
        if output_path and result.get("status") == "success":
            # Ensure output directory exists
            os.makedirs(output_path, exist_ok=True)
            # Generate filename from URL
            url_safe = url.replace('https://', '').replace('http://', '').replace('/', '_').replace(':', '_')
            if len(url_safe) > 100:
                url_safe = url_safe[:100]
            output_file = os.path.join(output_path, f"artifactory_browse_{url_safe}.json")
            result["output_file"] = browser.export_results(result, output_file)

        return json.dumps(result, indent=2)

    except Exception as e:
        return json.dumps({
            "status": "error",
            "message": str(e),
            "url": url
        })


def main():
    """Main function for CLI usage"""
    parser = argparse.ArgumentParser(
        description='Browse Artifactory directory and list files',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 browse_artifactory.py --url "https://ubit-artifactory-or.intel.com/artifactory/..."
  python3 browse_artifactory.py --url "https://..." --filter "test_name"
  python3 browse_artifactory.py --url "https://..." --output results.json
        """
    )

    parser.add_argument('--url', required=True, help='Full Artifactory URL to browse')
    parser.add_argument('--filter', default='', help='Optional pattern to filter results')
    parser.add_argument('--output', help='Optional JSON output file path')

    args = parser.parse_args()

    # Set up logging for standalone mode
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    # Create browser
    browser = ArtifactoryBrowser()

    # Browse directory
    result = browser.browse_directory(args.url, args.filter if args.filter else None)

    # Print summary
    print("=" * 80)
    print("ARTIFACTORY BROWSE RESULTS")
    print("=" * 80)
    print(f"URL: {result.get('url', args.url)}")
    print(f"Status: {result.get('status', 'unknown')}")

    if result.get('status') == 'success':
        print(f"Total items: {result.get('total_items', 0)}")
        print(f"Filtered items: {result.get('filtered_items', 0)}")
        print("=" * 80)
        print("\nFiles:")
        for file in result.get('files', []):
            print(f"  - {file}")
    else:
        print(f"Error: {result.get('message', 'Unknown error')}")

    print("=" * 80)

    # Export if requested
    if args.output:
        output_file = browser.export_results(result, args.output)
        if output_file:
            print(f"\nResults saved to: {output_file}")

    return 0 if result.get('status') == 'success' else 1


if __name__ == "__main__":
    sys.exit(main())
