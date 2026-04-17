#!/bin/bash

# Advanced Makefile parser for extracting include paths, defines, and dependencies
# Handles complex Makefile syntax including multi-line definitions, variables, and includes

set -euo pipefail

SCRIPT_VERSION="1.0.0"
MAKEFILE=""
OUTPUT_FORMAT="json"
LOG_LEVEL="INFO"

# Logging functions
log_error() {
    [[ "$LOG_LEVEL" != "QUIET" ]] && echo "❌ ERROR: $*" >&2
}

log_warn() {
    [[ "$LOG_LEVEL" != "QUIET" ]] && echo "⚠️  WARN: $*" >&2
}

log_info() {
    [[ "$LOG_LEVEL" != "QUIET" ]] && echo "ℹ️  INFO: $*" >&2
}

log_debug() {
    [[ "$LOG_LEVEL" == "DEBUG" ]] && echo "🔍 DEBUG: $*" >&2
}

# Function to show help
show_help() {
    cat << EOF
Advanced Makefile Parser v$SCRIPT_VERSION

USAGE:
    $0 [OPTIONS] MAKEFILE

DESCRIPTION:
    Parses Makefiles to extract include paths, compiler definitions,
    flags, and dependencies. Handles complex Makefile syntax including
    multi-line definitions, variables, and included files.

OPTIONS:
    --output-format FORMAT  Output format: json, text (default: json)
    --log-level LEVEL       Log level: QUIET, INFO, VERBOSE, DEBUG (default: INFO)
    -h, --help              Show this help message

EXAMPLES:
    $0 /path/to/Makefile
    $0 --output-format text --log-level DEBUG /path/to/Makefile

EOF
}

# Parse command line arguments
parse_arguments() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            -h|--help)
                show_help
                exit 0
                ;;
            --output-format)
                OUTPUT_FORMAT="$2"
                shift 2
                ;;
            --log-level)
                LOG_LEVEL="$2"
                shift 2
                ;;
            -*)
                log_error "Unknown option: $1"
                exit 1
                ;;
            *)
                if [[ -z "$MAKEFILE" ]]; then
                    MAKEFILE="$1"
                else
                    log_error "Multiple Makefiles specified"
                    exit 1
                fi
                shift
                ;;
        esac
    done

    if [[ -z "$MAKEFILE" ]]; then
        log_error "Makefile must be specified"
        exit 1
    fi

    if [[ ! -f "$MAKEFILE" ]]; then
        log_error "Makefile not found: $MAKEFILE"
        exit 1
    fi
}

# Function to resolve variables in Makefile content
resolve_variables() {
    local content="$1"
    local -A variables
    local resolved_content=""

    # First pass: collect variable definitions
    while IFS= read -r line; do
        # Skip comments and empty lines
        [[ "$line" =~ ^[[:space:]]*# ]] && continue
        [[ "$line" =~ ^[[:space:]]*$ ]] && continue

        # Look for variable assignments (VAR = value, VAR := value, VAR += value)
        if [[ "$line" =~ ^[[:space:]]*([A-Za-z_][A-Za-z0-9_]*)[[:space:]]*[:+]?=[[:space:]]*(.*)$ ]]; then
            local var_name="${BASH_REMATCH[1]}"
            local var_value="${BASH_REMATCH[2]}"

            # Handle += operator
            if [[ "$line" =~ \+= ]]; then
                var_value="${variables[$var_name]:-} $var_value"
            fi

            variables["$var_name"]="$var_value"
            log_debug "Variable: $var_name = $var_value"
        fi
    done <<< "$content"

    # Second pass: substitute variables
    while IFS= read -r line; do
        local resolved_line="$line"

        # Substitute $(VAR) and ${VAR} patterns
        for var_name in "${!variables[@]}"; do
            local var_value="${variables[$var_name]}"
            resolved_line="${resolved_line//\$($var_name)/$var_value}"
            resolved_line="${resolved_line//\${$var_name}/$var_value}"
        done

        resolved_content+="$resolved_line"$'\n'
    done <<< "$content"

    echo "$resolved_content"
}

# Function to handle multi-line definitions
handle_multiline() {
    local content="$1"
    local processed_content=""
    local current_line=""
    local in_multiline=false

    while IFS= read -r line; do
        # Check if line ends with backslash (continuation)
        if [[ "$line" =~ \\[[:space:]]*$ ]]; then
            # Remove backslash and add to current line
            current_line+="${line%\\*} "
            in_multiline=true
        else
            # End of multi-line or single line
            current_line+="$line"
            processed_content+="$current_line"$'\n'
            current_line=""
            in_multiline=false
        fi
    done <<< "$content"

    echo "$processed_content"
}

# Function to find included makefiles
find_includes() {
    local content="$1"
    local makefile_dir="$(dirname "$MAKEFILE")"
    local includes=()

    while IFS= read -r line; do
        # Look for include statements
        if [[ "$line" =~ ^[[:space:]]*-?include[[:space:]]+(.+)$ ]]; then
            local include_files="${BASH_REMATCH[1]}"

            # Split multiple files
            IFS=' ' read -ra file_array <<< "$include_files"
            for file in "${file_array[@]}"; do
                # Remove quotes and resolve path
                file=$(echo "$file" | tr -d '"' | tr -d "'")
                if [[ "$file" != /* ]]; then
                    file="$makefile_dir/$file"
                fi
                if [[ -f "$file" ]]; then
                    includes+=("$file")
                    log_debug "Found include: $file"
                else
                    log_warn "Include file not found: $file"
                fi
            done
        fi
    done <<< "$content"

    printf '%s\n' "${includes[@]}"
}

# Function to extract include paths
extract_includes() {
    local content="$1"
    local makefile_dir="$(dirname "$MAKEFILE")"
    local includes=()

    # Look for -I flags in various contexts
    while IFS= read -r line; do
        # Skip comments
        [[ "$line" =~ ^[[:space:]]*# ]] && continue

        # Find all -I patterns in the line
        local temp_line="$line"
        while [[ "$temp_line" =~ -I[[:space:]]*([^[:space:]]+) ]]; do
            local include_path="${BASH_REMATCH[1]}"

            # Remove quotes
            include_path=$(echo "$include_path" | tr -d '"' | tr -d "'")

            # Resolve relative paths
            if [[ "$include_path" != /* ]]; then
                include_path="$makefile_dir/$include_path"
            fi

            # Normalize path
            include_path=$(realpath -m "$include_path" 2>/dev/null || echo "$include_path")

            includes+=("$include_path")
            log_debug "Found include path: $include_path"

            # Remove the matched part and continue searching
            temp_line="${temp_line#*${BASH_REMATCH[0]}}"
        done
    done <<< "$content"

    # Remove duplicates
    printf '%s\n' "${includes[@]}" | sort -u
}

# Function to extract compiler defines
extract_defines() {
    local content="$1"
    local defines=()

    # Look for -D flags in various contexts
    while IFS= read -r line; do
        # Skip comments
        [[ "$line" =~ ^[[:space:]]*# ]] && continue

        # Find all -D patterns in the line
        local temp_line="$line"
        while [[ "$temp_line" =~ -D[[:space:]]*([^[:space:]]+) ]]; do
            local define="${BASH_REMATCH[1]}"

            # Remove quotes
            define=$(echo "$define" | tr -d '"' | tr -d "'")

            defines+=("$define")
            log_debug "Found define: $define"

            # Remove the matched part and continue searching
            temp_line="${temp_line#*${BASH_REMATCH[0]}}"
        done
    done <<< "$content"

    # Remove duplicates
    printf '%s\n' "${defines[@]}" | sort -u
}

# Function to extract compiler flags
extract_flags() {
    local content="$1"
    local flags=()

    # Look for common flag variables
    local flag_vars=("CFLAGS" "CPPFLAGS" "CXXFLAGS" "LDFLAGS" "ASFLAGS")

    for var in "${flag_vars[@]}"; do
        while IFS= read -r line; do
            # Look for variable assignments
            if [[ "$line" =~ ^[[:space:]]*$var[[:space:]]*[:+]?=[[:space:]]*(.*)$ ]]; then
                local flag_value="${BASH_REMATCH[1]}"
                flags+=("$var=$flag_value")
                log_debug "Found flag: $var=$flag_value"
            fi
        done <<< "$content"
    done

    printf '%s\n' "${flags[@]}"
}

# Function to extract targets and dependencies
extract_targets() {
    local content="$1"
    local targets=()

    while IFS= read -r line; do
        # Look for target definitions (target: dependencies)
        if [[ "$line" =~ ^([^[:space:]#][^:]*):([^=]*)?$ ]]; then
            local target="${BASH_REMATCH[1]}"
            local deps="${BASH_REMATCH[2]:-}"

            # Clean up target name
            target=$(echo "$target" | sed 's/[[:space:]]*$//')
            deps=$(echo "$deps" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//')

            targets+=("$target:$deps")
            log_debug "Found target: $target with deps: $deps"
        fi
    done <<< "$content"

    printf '%s\n' "${targets[@]}"
}

# Function to output results
output_results() {
    local includes=("$@")
    shift $#
    local defines=("$@")
    shift $#
    local flags=("$@")
    shift $#
    local targets=("$@")

    if [[ "$OUTPUT_FORMAT" == "json" ]]; then
        cat << EOF
{
    "makefile": "$MAKEFILE",
    "parser_version": "$SCRIPT_VERSION",
    "timestamp": "$(date -Iseconds)",
    "include_paths": [
$(printf '        "%s",\n' "${includes[@]}" | sed '$s/,$//')
    ],
    "defines": [
$(printf '        "%s",\n' "${defines[@]}" | sed '$s/,$//')
    ],
    "compiler_flags": [
$(printf '        "%s",\n' "${flags[@]}" | sed '$s/,$//')
    ],
    "targets": [
$(printf '        "%s",\n' "${targets[@]}" | sed '$s/,$//')
    ]
}
EOF
    else
        echo "Makefile: $MAKEFILE"
        echo "Parser Version: $SCRIPT_VERSION"
        echo "Timestamp: $(date)"
        echo
        echo "Include Paths:"
        printf '  %s\n' "${includes[@]}"
        echo
        echo "Defines:"
        printf '  %s\n' "${defines[@]}"
        echo
        echo "Compiler Flags:"
        printf '  %s\n' "${flags[@]}"
        echo
        echo "Targets:"
        printf '  %s\n' "${targets[@]}"
    fi
}

# Main function
main() {
    log_info "Parsing Makefile: $MAKEFILE"

    # Read the entire Makefile
    local content
    content=$(cat "$MAKEFILE")

    # Process multi-line definitions
    content=$(handle_multiline "$content")

    # Resolve variables
    content=$(resolve_variables "$content")

    # Process included files
    mapfile -t included_files < <(find_includes "$content")
    for include_file in "${included_files[@]}"; do
        log_info "Processing included file: $include_file"
        local include_content
        include_content=$(cat "$include_file")
        include_content=$(handle_multiline "$include_content")
        content+=$'\n'"$include_content"
    done

    # Extract information
    mapfile -t includes < <(extract_includes "$content")
    mapfile -t defines < <(extract_defines "$content")
    mapfile -t flags < <(extract_flags "$content")
    mapfile -t targets < <(extract_targets "$content")

    log_info "Found ${#includes[@]} include paths, ${#defines[@]} defines, ${#flags[@]} flag vars, ${#targets[@]} targets"

    # Output results
    output_results "${includes[@]}" "${defines[@]}" "${flags[@]}" "${targets[@]}"
}

# Script entry point
if [[ "${BASH_SOURCE[0]:-}" == "${0}" ]]; then
    parse_arguments "$@"
    main
fi
