#!/usr/bin/env python3
"""
Download File from Artifactory

This tool downloads a specific file from Artifactory to a target directory.
Can be used as a standalone script or imported as a LangChain tool.

Arguments (CLI mode):
    --url: (Required) Full URL to the file (including filename)
    --output-dir: (Required) Directory to save the downloaded file

Environment Variables Required:
    ARTIFACTORY_TOKEN: Artifactory API token for authentication

Usage:
    python3 download_artifactory_file.py --url "https://ubit-artifactory-or.intel.com/.../file.7z" --output-dir "/tmp/output"

Examples:
    python3 download_artifactory_file.py --url "https://ubit-artifactory-or.intel.com/artifactory/.../Logs-test.7z" --output-dir "/tmp/logs"
"""

import argparse
import os
import logging
import requests
from pathlib import Path
from dotenv import load_dotenv
from langchain_core.tools import tool

# Load environment variables
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.env'))


class ArtifactoryDownloader:
    def __init__(self, logger=None):
        self.logger = logger or logging.getLogger(__name__)
        self.artifactory_token = os.getenv('ARTIFACTORY_TOKEN')
        # SSL verification - can be disabled for corporate proxies
        self.verify_ssl = os.getenv('ARTIFACTORY_VERIFY_SSL', 'true').lower() != 'false'

        if not self.artifactory_token:
            self.logger.warning("ARTIFACTORY_TOKEN not set in environment")

    def download_file(self, url: str, output_dir: str) -> dict:
        """
        Download a file from Artifactory

        Args:
            url: Full URL to the file (including filename)
            output_dir: Directory to save the downloaded file

        Returns:
            Dict with status, file path, and metadata
        """
        if not self.artifactory_token:
            return {
                "status": "error",
                "message": "ARTIFACTORY_TOKEN not set in environment variables"
            }

        try:
            # Extract filename from URL
            filename = os.path.basename(url)

            # Create output directory if needed
            output_path = Path(output_dir)
            output_path.mkdir(parents=True, exist_ok=True)

            # Full path for downloaded file
            file_path = output_path / filename

            self.logger.debug(f"Downloading: {filename}")
            self.logger.debug(f"From: {url}")
            self.logger.debug(f"To: {output_dir}")

            # Download file
            headers = {
                'X-JFrog-Art-Api': self.artifactory_token
            }

            response = requests.get(url, headers=headers, timeout=300, stream=True, verify=self.verify_ssl)
            response.raise_for_status()

            # Write file in chunks
            with open(file_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)

            # Verify download
            file_size = file_path.stat().st_size
            self.logger.debug(f"Download complete: {file_path} ({file_size} bytes)")

            return {
                "status": "success",
                "url": url,
                "file_path": str(file_path),
                "filename": filename,
                "size_bytes": file_size,
                "output_dir": output_dir
            }

        except requests.exceptions.RequestException as e:
            error_msg = f"Failed to download file: {e}"
            self.logger.error(error_msg)
            return {
                "status": "error",
                "message": error_msg,
                "url": url
            }
        except Exception as e:
            error_msg = f"Error downloading file: {e}"
            self.logger.error(error_msg)
            return {
                "status": "error",
                "message": error_msg,
                "url": url
            }


@tool
def download_artifactory_file(url: str, output_dir: str) -> dict:
    """Download a file from Artifactory to a local directory.

    Downloads the file at the specified URL and saves it to the output directory.
    Creates the output directory if it doesn't exist.

    Args:
        url: Complete URL to the file (must include filename, not a directory).
        output_dir: Local directory path where the file will be saved.

    Returns:
        dict: Contains:
            - status: "success" or "error"
            - file_path: Full local path to downloaded file
            - filename: Name of the downloaded file
            - size_bytes: File size in bytes
            - output_dir: Directory where file was saved
            - message: Error description (on failure)

    Environment:
        Requires ARTIFACTORY_TOKEN environment variable.
    """
    logger = logging.getLogger('agent')
    downloader = ArtifactoryDownloader(logger=logger)
    return downloader.download_file(url, output_dir)


def main():
    """Main function for standalone CLI usage"""
    parser = argparse.ArgumentParser(
        description='Download file from Artifactory',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        '--url',
        type=str,
        required=True,
        help='Full URL to the file (including filename)'
    )

    parser.add_argument(
        '--output-dir',
        type=str,
        required=True,
        help='Directory to save the downloaded file'
    )

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(levelname)s - %(message)s'
    )

    # Download file
    result = download_artifactory_file.invoke({
        "url": args.url,
        "output_dir": args.output_dir
    })

    print("\n" + "="*80)
    print("DOWNLOAD RESULT")
    print("="*80)
    if result["status"] == "success":
        print(f"✅ Success: {result['file_path']}")
        print(f"   Size: {result['size_bytes']} bytes")
    else:
        print(f"❌ Error: {result['message']}")
    print("="*80)


if __name__ == "__main__":
    main()
