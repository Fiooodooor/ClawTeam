
jq -r '
  [.. | objects
     | select(has("header_file") and has("status"))
     | select((.status|tostring)|test("^(OK|PASSED|SUCCESS)$")|not)]
  | sort_by(.header_file)[]
  | .header_file
' $WORKSPACE/sources/imc/tools/scripts/header_self_contained/header_check_output/userspace_results.json
