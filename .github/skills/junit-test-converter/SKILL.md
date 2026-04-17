---
name: junit-test-converter
description: "Convert proprietary unit test log output into standard JUnit XML format for CI reporting. Use when: integrating custom test frameworks with CI dashboards (Jenkins, Azure DevOps), converting test logs to JUnit XML, or troubleshooting test result parsing."
argument-hint: "Path to unit test log file to convert"
---

# JUnit Test Converter

Converts proprietary unit test log output to standard JUnit XML format for CI system consumption.

## Source

Based on: `tools/scripts/covertUtLogToJunit/` (contains `ut_to_junit.exe` binary converter)

## When to Use

- Converting internal unit test log formats to JUnit XML
- Integrating custom test frameworks with Jenkins/Azure DevOps test result visualization
- Post-processing test output for CI pipeline consumption

## Usage

```bash
./ut_to_junit.exe <input_test_log> <output_junit_xml>
```

## JUnit XML Format Reference

If implementing a custom converter, target this structure:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<testsuites>
  <testsuite name="SuiteName" tests="3" failures="1" errors="0" time="0.123">
    <testcase name="test_pass_example" classname="SuiteName" time="0.045"/>
    <testcase name="test_fail_example" classname="SuiteName" time="0.078">
      <failure message="Expected 5 but got 3" type="AssertionError">
        Detailed failure output here
      </failure>
    </testcase>
    <testcase name="test_error_example" classname="SuiteName" time="0.000">
      <error message="Segmentation fault" type="RuntimeError"/>
    </testcase>
  </testsuite>
</testsuites>
```

## Notes

- The binary `ut_to_junit.exe` is a pre-compiled Windows executable
- For Linux environments, consider using a Python-based converter or Wine
- CI systems (Jenkins, Azure DevOps, GitLab) natively parse JUnit XML for test reporting
