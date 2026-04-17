#!/usr/bin/env python3
"""
Extract Build Failed Swift Log Location from ETH_FW_CI_DB

This script extracts Swift test failure log locations for a specific build number and project.

Output Behavior:
    - Console (always): Displays basic summary information (test names, status, log links)
    - JSON file (optional): Exports comprehensive test data including all metadata

Arguments:
    --build-number: (Required) Exact build number to match (e.g., 582 matches #582 but not #12582)
    --project-name: (Required) Project name to filter by (e.g., MMG, NSC, IPU_ONE_IMAGE)
    --ring-type: (Optional) Filter by ring type pattern (default: BAT). Matches ring types containing this pattern (e.g., BAT Tests, PIT Tests, Nightly Tests, WEEKLY Tests)
    --output: (Optional) Output JSON file path. If not provided, only basic info is displayed on console

Usage:
    # Display results to console only
    python3 extract_build_failed_swift_log_location.py --build-number <NUMBER> --project-name <NAME>

    # Export results to JSON file
    python3 extract_build_failed_swift_log_location.py --build-number <NUMBER> --project-name <NAME> --output <FILE>

Examples:
    python3 extract_build_failed_swift_log_location.py --build-number 30724 --project-name IPU_ONE_IMAGE
    python3 extract_build_failed_swift_log_location.py --build-number 12345 --project-name MMG --output results.json
"""

import argparse
import json
import mysql.connector
import sys
import os
import logging
from datetime import datetime
from typing import List, Dict, Optional
import traceback
from dotenv import load_dotenv
from langchain_core.tools import tool

# Load environment variables from .env file (in parent directory)
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.env'))


class BuildFailedSwiftLogExtractor:
    def __init__(self, logger=None):
        self.logger = logger or logging.getLogger(__name__)
        self.db_config = {
            'host': 'maria3155-lb-lc-in.dbaas.intel.com',
            'port': 3307,
            'user': 'ETH_FW_CI_DB_ro',
            'password': os.getenv('DB_PASSWORD'),
            'database': 'ETH_FW_CI_DB',
            'charset': 'utf8mb4',
            'connect_timeout': 30,
            'autocommit': True
        }
        self.connection = None

    @staticmethod
    def normalize_url(url: str) -> str:
        """Normalize URLs by replacing backslashes with forward slashes

        Args:
            url: URL string that may contain backslashes

        Returns:
            Normalized URL with forward slashes
        """
        if url:
            # Replace all backslashes with forward slashes
            normalized = url.replace('\\', '/')
            # Fix protocol separator if needed (https:/ -> https://)
            if normalized.startswith('https:/') and not normalized.startswith('https://'):
                normalized = normalized.replace('https:/', 'https://', 1)
            elif normalized.startswith('http:/') and not normalized.startswith('http://'):
                normalized = normalized.replace('http:/', 'http://', 1)
            return normalized
        return url

    def connect_to_database(self):
        """Establish database connection"""
        try:
            self.logger.debug("Connecting to CI Database...")
            self.connection = mysql.connector.connect(**self.db_config)
            self.logger.debug("Connection established")
            return True
        except mysql.connector.Error as e:
            self.logger.error(f"Error connecting to database: {e}")
            return False

    def disconnect_from_database(self):
        """Close database connection"""
        if self.connection:
            self.connection.close()
            self.logger.debug("Database connection closed")

    def execute_query(self, query: str, params: tuple = None) -> List[Dict]:
        """Execute a SQL query and return results"""
        try:
            cursor = self.connection.cursor(dictionary=True)
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            results = cursor.fetchall()
            cursor.close()
            return results
        except mysql.connector.Error as e:
            self.logger.error(f"Error executing query: {e}")
            self.logger.error(f"Query: {query}")
            if params:
                self.logger.error(f"Parameters: {params}")
            return []

    def get_swift_failed_test_logs(self, build_number: str, project_name: str, ring_type: str = 'BAT') -> List[Dict]:
        """
        Get Swift test failure log locations for a specific build number and project

        Args:
            build_number (str): Build number to search for
            project_name (str): Project name to filter by
            ring_type (str): Filter by ring type pattern (default: BAT). Matches ring types containing this pattern (e.g., BAT Tests, PIT Tests, Nightly Tests, WEEKLY Tests)

        Returns:
            List[Dict]: List of Swift test failure log locations
        """
        self.logger.debug(f"Query build test results (Build: {build_number}, Project: {project_name}, Ring: {ring_type})")

        # Build base query
        query = """
        SELECT
            `v_testResult`.`testResultId` AS `testResultId`,
            `v_testResult`.`testCycle_name` AS `testCycle_name`,
            `v_testResult`.`testCycleStatus` AS `testCycleStatus`,
            `v_testResult`.`project` AS `project`,
            `v_testResult`.`stageName` AS `stageName`,
            `v_testResult`.`testProject` AS `testProject`,
            `v_testResult`.`testStageStatus` AS `testStageStatus`,
            `v_testResult`.`testName` AS `testName`,
            `v_testResult`.`image` AS `image`,
            `v_testResult`.`feature` AS `feature`,
            `v_testResult`.`result` AS `result`,
            `v_testResult`.`errorInfo` AS `errorInfo`,
            `v_testResult`.`version` AS `version`,
            `v_testResult`.`duration` AS `duration`,
            `v_testResult`.`duration(sec)` AS `duration_sec`,
            `v_testResult`.`hostname` AS `hostname`,
            `v_testResult`.`framework` AS `framework`,
            `v_testResult`.`platform` AS `platform`,
            `v_testResult`.`testDbId` AS `testDbId`,
            `v_testResult`.`burnId` AS `burnId`,
            `v_testResult`.`featureOwner` AS `featureOwner`,
            `v_testResult`.`log` AS `log`,
            `v_testResult`.`stageStartTime` AS `stageStartTime`,
            `v_testResult`.`stageEndTime` AS `stageEndTime`,
            `v_testResult`.`work_week` AS `work_week`
        FROM `v_testResult`
        WHERE (
            `v_testResult`.`testCycle_name` REGEXP %s
            AND `v_testResult`.`project` = %s
            AND `v_testResult`.`framework` = 'SWIFT'
            AND (
                `v_testResult`.`result` = 'FAIL'
                OR `v_testResult`.`result` = 'INCONCLUSIVE'
                OR `v_testResult`.`result` = 'UNKNOWN'
            )
        """

        # Build regex pattern: #<build_number> followed by non-digit or end of string
        # Example: #582 matches "NSSHIP-#582" but not "BAT-#12582" or "BAT-#15582"
        build_pattern = f'#{build_number}([^0-9]|$)'
        params = [build_pattern, project_name]

        # Add ring type filter if specified (filter by stageName field)
        if ring_type:
            query += "\n            AND `v_testResult`.`stageName` LIKE %s"
            params.append(f'%{ring_type}%')

        query += "\n        )\n        LIMIT 300\n        "

        results = self.execute_query(query, tuple(params))

        # Normalize URLs in results
        if results:
            for test in results:
                if test.get('log'):
                    test['log'] = self.normalize_url(test['log'])
                self.logger.debug(f"Found test: {test['testName']} ({test['result']})")
                if test.get('log'):
                    self.logger.debug(f"  Log: {test['log']}")
        else:
            self.logger.warning("No Swift test failure logs found for the specified build and project")

        return results

    def extract_log_locations(self, build_number: str, project_name: str, ring_type: str = 'BAT') -> Dict:
        """
        Extract Swift test failure log locations for a build

        Args:
            build_number (str): Build number
            project_name (str): Project name
            ring_type (str): Filter by ring type pattern (default: BAT). Matches ring types containing this pattern (e.g., BAT Tests, PIT Tests, Nightly Tests, WEEKLY Tests)

        Returns:
            Dict: Extracted log locations and test information
        """
        failures = self.get_swift_failed_test_logs(build_number, project_name, ring_type)

        if not failures:
            return {
                'build_number': build_number,
                'project_name': project_name,
            'extraction_timestamp': datetime.now().isoformat(),
            'ring_type': ring_type,
            'has_failures': False,
            'failure_count': 0,
            'failed_tests': [],
            }

        # Extract statistics
        test_cycles = set()
        unique_tests = set()
        for failure in failures:
            if failure.get('testCycle_name'):
                test_cycles.add(failure['testCycle_name'])
            if failure.get('testName'):
                unique_tests.add(failure['testName'])


        return {
            'build_number': build_number,
            'project_name': project_name,
            'extraction_timestamp': datetime.now().isoformat(),
            'ring_type': ring_type,
            'has_failures': True,
            'failure_count': len(failures),
            'unique_test_count': len(unique_tests),
            'test_cycle_count': len(test_cycles),
            'test_cycles': list(test_cycles),
            'unique_tests': list(unique_tests),
            'failed_tests': failures
        }

    def export_log_locations(self, log_data: Dict, output_file: str = None) -> str:
        """Export log locations to JSON file"""
        if output_file is None:
            return None

        try:
            def datetime_converter(obj):
                if isinstance(obj, datetime):
                    return obj.isoformat()
                elif hasattr(obj, 'isoformat'):
                    return obj.isoformat()
                elif hasattr(obj, 'total_seconds'):  # timedelta
                    return obj.total_seconds()
                elif hasattr(obj, '__float__'):
                    return float(obj)
                elif hasattr(obj, '__int__'):
                    return int(obj)
                raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(log_data, f, indent=2, default=datetime_converter, ensure_ascii=False)

            return output_file

        except Exception as e:
            self.logger.error(f"Error exporting log locations: {e}")
            return None


@tool
def get_failed_test_logs(build_number: str, project: str, output_path: str, ring_type: str = 'BAT') -> str:
    """Query CI database for failed test information from a specific build.

    Retrieves failed test records including test names, error info, and log URLs
    from the CI database. Results are saved to a JSON file.

    Args:
        build_number: The CI build number to query.
        project: The project name to filter by.
        output_path: Directory path where results JSON file will be saved.
        ring_type: Filter by ring type pattern (default: BAT). Matches ring types containing this pattern (e.g., BAT Tests, PIT Tests, Nightly Tests, WEEKLY Tests).

    Returns:
        str: JSON string containing:
            - status: "success" or "error"
            - build_number: The queried build number
            - project: The queried project name
            - has_failures: Whether failures were found
            - failure_count: Number of failed tests
            - unique_test_count: Number of unique test names
            - unique_tests: List of unique test names
            - output_file: Path to detailed results JSON file
            - message: Error description (on failure)

    Output File (failed_tests_{build_number}.json):
        - failed_tests: Array of test records with testName, log URL, result, errorInfo
        - unique_tests: Deduplicated test name list
        - test_cycles: Test cycle metadata

    Environment:
        Requires DB_PASSWORD environment variable.
    """
    # Get logger from the calling context
    logger = logging.getLogger('agent')

    try:
        # Create extractor with logger
        extractor = BuildFailedSwiftLogExtractor(logger=logger)

        # Connect to database
        if not extractor.connect_to_database():
            return json.dumps({
                "status": "error",
                "message": "Failed to connect to database"
            })

        try:
            # Extract log locations
            log_data = extractor.extract_log_locations(build_number, project, ring_type)

            # Ensure output directory exists
            os.makedirs(output_path, exist_ok=True)

            # Prepare output file path
            output_file = os.path.join(output_path, f"failed_tests_{build_number}.json")

            # Export results
            result_file = extractor.export_log_locations(log_data, output_file)

            # Prepare response
            response = {
                "status": "success",
                "build_number": log_data['build_number'],
                "project": log_data['project_name'],
                "has_failures": log_data['has_failures'],
                "failure_count": log_data['failure_count'],
                "output_file": result_file
            }

            if log_data['has_failures']:
                response["unique_test_count"] = log_data['unique_test_count']
                response["test_cycles"] = log_data.get('test_cycles', [])
                response["unique_tests"] = log_data.get('unique_tests', [])

            return json.dumps(response, indent=2)

        finally:
            extractor.disconnect_from_database()

    except Exception as e:
        return json.dumps({
            "status": "error",
            "message": str(e),
            "traceback": traceback.format_exc()
        })


def main():
    """Main function"""
    parser = argparse.ArgumentParser(
        description='Extract Swift test failure log locations for a specific build',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 extract_build_failed_swift_log_location.py --build-number 12345 --project-name MMG
  python3 extract_build_failed_swift_log_location.py --build-number CI_KeepAlive_123 --project-name NSC --output results.json
  python3 extract_build_failed_swift_log_location.py --build-number 30724 --project-name IPU_ONE_IMAGE
        """
    )

    parser.add_argument('--build-number', type=str, required=True,
                       help='Exact build number to match (e.g., 582 matches #582 but not #12582)')
    parser.add_argument('--project-name', type=str, required=True,
                       help='Project name to filter by (e.g., MMG, NSC, IPU_ONE_IMAGE)')
    parser.add_argument('--ring-type', type=str, default='BAT',
                       help='Filter by ring type pattern (default: BAT). Matches ring types containing this pattern (e.g., BAT Tests, PIT Tests, Nightly Tests, WEEKLY Tests)')
    parser.add_argument('--output', type=str, default=None,
                       help='Output JSON file path (optional). Saves comprehensive test data with all metadata. Console always shows basic summary')

    args = parser.parse_args()

    # Create extractor
    extractor = BuildFailedSwiftLogExtractor()

    # Connect to database
    if not extractor.connect_to_database():
        print("Failed to connect to database. Exiting.")
        return 1

    try:
        # Extract log locations
        log_data = extractor.extract_log_locations(args.build_number, args.project_name, args.ring_type)

        # Print summary
        print(f"\n{'='*80}")
        print(f"LOG EXTRACTION COMPLETED")
        print(f"{'='*80}")
        print(f"Build Number: {log_data['build_number']}")
        print(f"Project: {log_data['project_name']}")
        print(f"Total failure logs: {log_data['failure_count']}")
        print(f"{'='*80}")

        # Export results if output file specified
        if args.output:
            output_file = extractor.export_log_locations(log_data, args.output)
            if not output_file:
                return 1
            print(f"\n✅ Results saved to: {output_file}")

        return 0

    except Exception as e:
        print(f"Error during log extraction: {e}")
        traceback.print_exc()
        return 1

    finally:
        extractor.disconnect_from_database()


if __name__ == "__main__":
    exit(main())
