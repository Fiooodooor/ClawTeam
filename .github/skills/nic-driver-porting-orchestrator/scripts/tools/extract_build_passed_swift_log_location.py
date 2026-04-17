#!/usr/bin/env python3
"""
Extract Passed Swift Test Logs from ETH_FW_CI_DB

Queries for successful Swift test runs by project name and test name.
Returns the most recent passing test within a specified time window.

Arguments:
    --project-name: (Required) Project name (e.g., IPU_ONE_IMAGE)
    --test-name: (Required) Test name to filter (case-insensitive, partial match)
    --days: (Optional) Days to look back (default: 7)
    --limit: (Optional) Max results (default: 1)
    --output: (Optional) JSON output file path

Examples:
    python3 extract_build_passed_swift_log_location.py --project-name <PROJECT_NAME> --test-name <TEST_NAME>
    python3 extract_build_passed_swift_log_location.py --project-name <PROJECT_NAME> --test-name <TEST_NAME> --limit <NUMBER> --days <DAYS>
    python3 extract_build_passed_swift_log_location.py --project-name <PROJECT_NAME> --test-name <TEST_NAME> --output <OUTPUT_FILE>
"""

import argparse
import json
import mysql.connector
import os
import logging
from datetime import datetime, timedelta
from typing import List, Dict
import traceback
from dotenv import load_dotenv
from langchain_core.tools import tool

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.env'))


class BuildPassedSwiftLogExtractor:
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
        try:
            self.logger.debug("Connecting to CI Database...")
            self.connection = mysql.connector.connect(**self.db_config)
            self.logger.debug("Connection established")
            return True
        except mysql.connector.Error as e:
            self.logger.error(f"Error connecting to database: {e}")
            return False

    def disconnect_from_database(self):
        if self.connection:
            self.connection.close()
            self.logger.debug("Database connection closed")

    def execute_query(self, query: str, params: tuple = None) -> List[Dict]:
        try:
            cursor = self.connection.cursor(dictionary=True)
            cursor.execute(query, params) if params else cursor.execute(query)
            results = cursor.fetchall()
            cursor.close()
            return results
        except mysql.connector.Error as e:
            self.logger.error(f"Error executing query: {e}")
            return []

    def get_swift_passed_test_logs(self, project_name: str, test_name: str, days: int = 7, limit: int = 1) -> List[Dict]:
        self.logger.debug(f"Query passed tests (Project: {project_name}, Test: {test_name}, Last {days} days)")

        cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

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
            `v_testResult`.`project` = %s
            AND `v_testResult`.`framework` = 'SWIFT'
            AND `v_testResult`.`stageStartTime` >= %s
            AND LOWER(`v_testResult`.`testName`) LIKE %s
            AND `v_testResult`.`result` = 'PASS'
        )
        ORDER BY `v_testResult`.`stageStartTime` DESC, `v_testResult`.`testName` ASC
        LIMIT %s
        """

        params = (project_name, cutoff_date, f'%{test_name.lower()}%', limit)
        results = self.execute_query(query, params)

        # Normalize URLs in results
        if results:
            for test in results:
                if test.get('log'):
                    test['log'] = self.normalize_url(test['log'])
                self.logger.debug(f"Found passed test: {test['testName']}")
                if test.get('log'):
                    self.logger.debug(f"  Log: {test['log']}")
        else:
            self.logger.warning("No passed tests found matching criteria")

        return results

    def extract_log_locations(self, project_name: str, test_name: str, days: int = 7, limit: int = 1) -> Dict:
        passed_tests = self.get_swift_passed_test_logs(project_name, test_name, days, limit)

        if not passed_tests:
            return {
                'project_name': project_name,
                'test_name_filter': test_name,
                'extraction_timestamp': datetime.now().isoformat(),
                'has_passed_tests': False,
                'passed_count': 0,
                'passed_tests': [],
            }

        test_cycles = {t['testCycle_name'] for t in passed_tests if t.get('testCycle_name')}
        unique_tests = {t['testName'] for t in passed_tests if t.get('testName')}

        return {
            'project_name': project_name,
            'test_name_filter': test_name,
            'extraction_timestamp': datetime.now().isoformat(),
            'has_passed_tests': True,
            'passed_count': len(passed_tests),
            'unique_test_count': len(unique_tests),
            'test_cycle_count': len(test_cycles),
            'test_cycles': list(test_cycles),
            'unique_tests': list(unique_tests),
            'passed_tests': passed_tests
        }

    def export_log_locations(self, log_data: Dict, output_file: str = None) -> str:
        if not output_file:
            return None
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(log_data, f, indent=2, default=str, ensure_ascii=False)
            return output_file
        except Exception as e:
            self.logger.error(f"Error exporting: {e}")
            return None


@tool
def get_passed_test_logs(project: str, test_name: str, output_path: str, days: int = 7, limit: int = 1) -> str:
    """Query CI database for recent passed runs of a specific test.

    Searches for successful test executions within the specified time window.
    Useful for finding reference logs from passing tests. Results saved to JSON.

    Args:
        project: The project name to filter by.
        test_name: Test name to search for (case-insensitive, partial match supported).
        output_path: Directory path where results JSON file will be saved.
        days: Number of days to search back (default: 7).
        limit: Maximum number of results to return (default: 1).

    Returns:
        str: JSON string containing:
            - status: "success" or "error"
            - project: The queried project name
            - test_name_filter: The test name filter used
            - has_passed_tests: Whether passed tests were found
            - passed_count: Number of passed test runs found
            - unique_test_count: Number of unique test names
            - output_file: Path to detailed results JSON file
            - message: Error description (on failure)

    Output File (passed_tests_{test_name}.json):
        - passed_tests: Array of test records with testName, log URL, result
        - unique_tests: Deduplicated test name list
        - test_cycles: Test cycle metadata

    Environment:
        Requires DB_PASSWORD environment variable.
    """
    # Get logger from the calling context
    logger = logging.getLogger('agent')

    try:
        # Create extractor with logger
        extractor = BuildPassedSwiftLogExtractor(logger=logger)

        # Connect to database
        if not extractor.connect_to_database():
            return json.dumps({
                "status": "error",
                "message": "Failed to connect to database"
            })

        try:
            # Extract log locations
            log_data = extractor.extract_log_locations(project, test_name, days, limit)

            # Ensure output directory exists
            os.makedirs(output_path, exist_ok=True)

            # Prepare output file path
            output_file = os.path.join(output_path, f"passed_tests_{test_name.replace(' ', '_')}.json")

            # Export results
            result_file = extractor.export_log_locations(log_data, output_file)

            # Prepare response
            response = {
                "status": "success",
                "project": log_data['project_name'],
                "test_name_filter": log_data['test_name_filter'],
                "has_passed_tests": log_data['has_passed_tests'],
                "passed_count": log_data['passed_count'],
                "output_file": result_file
            }

            if log_data['has_passed_tests']:
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
    parser = argparse.ArgumentParser(
        description='Extract passed Swift test logs for a project (queries by project name, NOT build number)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 extract_build_passed_swift_log_location.py --project-name <PROJECT_NAME> --test-name <TEST_NAME>
  python3 extract_build_passed_swift_log_location.py --project-name <PROJECT_NAME> --test-name <TEST_NAME> --limit <NUMBER>
  python3 extract_build_passed_swift_log_location.py --project-name <PROJECT_NAME> --test-name <TEST_NAME> --output <OUTPUT_FILE>
        """
    )

    parser.add_argument('--project-name', required=True, help='Project name (e.g., IPU_ONE_IMAGE)')
    parser.add_argument('--test-name', required=True, help='Test name to filter (case-insensitive, partial match)')
    parser.add_argument('--days', type=int, default=7, help='Days to look back (default: 7)')
    parser.add_argument('--limit', type=int, default=1, help='Max results to return (default: 1)')
    parser.add_argument('--output', help='JSON output file path (optional)')

    args = parser.parse_args()
    extractor = BuildPassedSwiftLogExtractor()

    if not extractor.connect_to_database():
        return 1

    try:
        log_data = extractor.extract_log_locations(args.project_name, args.test_name, args.days, args.limit)

        print(f"{'='*80}")
        print(f"LOG EXTRACTION COMPLETED")
        print(f"{'='*80}")
        print(f"Project: {log_data['project_name']}")
        print(f"Test Filter: {log_data['test_name_filter']}")
        print(f"Passed tests: {log_data['passed_count']}")
        print(f"{'='*80}\n")

        if args.output:
            output_file = extractor.export_log_locations(log_data, args.output)
            if output_file:
                print(f"✅ Results saved to: {output_file}\n")
        return 0

    except Exception as e:
        print(f"\nError: {e}")
        traceback.print_exc()
        return 1
    finally:
        extractor.disconnect_from_database()


if __name__ == "__main__":
    exit(main())
