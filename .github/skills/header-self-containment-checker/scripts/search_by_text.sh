
jq -r '
  def objs: .. | objects;
  objs
  | select(.compile_output? and (.compile_output | contains("unknown type name") and contains("u8")))
  | .header_file? // empty
' $WORKSPACE/sources/imc/tools/scripts/header_self_contained/header_check_output/userspace_results.json \
| sed '/^$/d' | sort -u \
> $WORKSPACE/sources/imc/tools/scripts/header_self_contained/header_check_output/userspace_u8_unknown_headers.txt

wc -l $WORKSPACE/sources/imc/tools/scripts/header_self_contained/header_check_output/userspace_u8_unknown_headers.txt
head -n 30 $WORKSPACE/sources/imc/tools/scripts/header_self_contained/header_check_output/userspace_u8_unknown_headers.txt

