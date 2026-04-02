#!/bin/bash

# Header Check Results Analyzer
# Extracts and displays failed header compilation results in an easy-to-read format

RESULTS_FILE="$1"

if [[ -z "$RESULTS_FILE" ]]; then
    echo "Usage: $0 <results.json>"
    echo "Example: $0 header_check_output/hifmc_results.json"
    exit 1
fi

if [[ ! -f "$RESULTS_FILE" ]]; then
    echo "Error: Results file not found: $RESULTS_FILE"
    exit 1
fi

echo "=== Header Self-Containment Check Results ==="
echo "File: $RESULTS_FILE"
echo

# Extract summary
echo "📊 SUMMARY:"
jq -r '.summary | "Total: \(.total) headers | ✅ Passed: \(.passed) | ❌ Failed: \(.failed) | Success Rate: \(.success_rate)%"' "$RESULTS_FILE"
echo

# Show failed headers with error details
echo "❌ FAILED HEADERS:"
echo "=================="

jq -r '.results[] | select(.status == "FAILED") |
"\n📁 Header: \(.header_file | split("/") | .[-1])
🏠 Path: \(.header_file)
⚠️  Error: \(.compile_output | split("\n") | map(select(contains("error:"))) | if length > 0 then .[0] | split("error:")[1] | ltrimstr(" ") else "Unable to parse error" end)
"' "$RESULTS_FILE"

echo
echo "🔍 FAILURE ANALYSIS:"
echo "===================="

# Count failures by error type
echo "Most common errors:"
jq -r '.results[] | select(.status == "FAILED") | .compile_output' "$RESULTS_FILE" | \
grep "fatal error:" | \
sed 's/.*fatal error: //' | \
sed 's/: No such file or directory//' | \
sort | uniq -c | sort -nr | \
head -10 | \
while read count error; do
    echo "  $count × Missing: $error"

done

echo
echo "🎯 QUICK FIXES NEEDED:"
echo "====================="
echo "Based on the errors above, you likely need to:"
echo "1. Add missing include paths for hif-shared components"
echo "2. Check if build configuration is properly collecting dependencies"
echo "3. Verify CMake files are being parsed correctly"

# Show which directories have the most failures
echo
echo "📂 Failures by directory:"
jq -r '.results[] | select(.status == "FAILED") | .header_file' "$RESULTS_FILE" | \
while read file; do
    dirname "$file" | sed 's|.*/sources/imc/||'
done | \
sort | uniq -c | sort -nr | head -5 | \
while read count dir; do
    echo "  $count failures in: $dir"
done

# ============
# Final stats – minimal additions per request
# ============

echo
echo "📈 FINAL STATISTICS:"
echo "===================="

# Total failed headers due to missing .h files (fatal error: *.h: No such file or directory)
missing_h_count=$(jq -r '[.results[]
  | select(.status == "FAILED")
  | select(.compile_output | test("fatal error: .*\\.h: No such file or directory"))] | length' "$RESULTS_FILE")

# Fallback if jq test() is unavailable
if [[ -z "$missing_h_count" || "$missing_h_count" == "null" ]]; then
  missing_h_count=$(jq -r '.results[] | select(.status=="FAILED") | .compile_output' "$RESULTS_FILE" | \
    grep -E 'fatal error: .*\.h: No such file or directory' | wc -l)
fi

total_failed=$(jq -r '.summary.failed // 0' "$RESULTS_FILE")

echo "❌ Headers failing due to missing .h files: $missing_h_count / $total_failed"

echo
echo "📜 Missing headers (full, sorted by frequency):"
echo "----------------------------------------------"
# Full sorted list of missing headers (no truncation)
jq -r '.results[] | select(.status == "FAILED") | .compile_output' "$RESULTS_FILE" | \
  grep -E 'fatal error: .*\.h: No such file or directory' | \
  sed 's/.*fatal error: //' | \
  sed 's/: No such file or directory//' | \
  sort | uniq -c | sort -nr | \
  awk '{cnt=$1; $1=""; hdr=substr($0,2); printf("  %s × %s\n", cnt, hdr)}'
