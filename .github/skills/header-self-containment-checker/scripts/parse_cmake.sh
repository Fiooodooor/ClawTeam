#!/bin/bash

# Enhanced CMake parser for extracting include paths and definitions
# Dynamically analyzes all CMake files to resolve dependencies

set -euo pipefail

CMAKE_FILE=""
OUTPUT_FORMAT="json"

# Global CMake variable declarations
CMAKE_INFRA_COMMON_HIF_DIR=""
CMAKE_MEV_INFRA_HIF_DIR=""
CMAKE_MEV_HW_HIF_DIR=""
CMAKE_HIF_SHARED_HIF_DIR=""
CMAKE_MEV_IMC_SHARED_DIR=""
CMAKE_XT_COMMON_HIF_DIR=""

# Function to show help
show_help() {
    cat << EOF
Enhanced CMake Parser

USAGE:
    $0 [OPTIONS] CMAKE_FILE

DESCRIPTION:
    Parses CMake files to extract include paths and compiler definitions.
    Resolves CMake variables and analyzes all related CMake files.

OPTIONS:
    --output-format FORMAT  Output format: json, text (default: json)
    -h, --help              Show this help message

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
            -*)
                echo "ERROR: Unknown option: $1" >&2
                exit 1
                ;;
            *)
                if [[ -z "$CMAKE_FILE" ]]; then
                    CMAKE_FILE="$1"
                else
                    echo "ERROR: Multiple CMake files specified" >&2
                    exit 1
                fi
                shift
                ;;
        esac
    done
}

# Function to recursively find and parse all CMakeLists.txt files
find_all_cmake_files() {
    local base_dir="$1"

    # If we're analyzing a specific file in hifmc, scan the entire hifmc directory
    if [[ "$base_dir" == *"hifmc"* ]]; then
        # Find the hifmc root directory
        local hifmc_root
        if [[ "$WORKSPACE" ]]; then
            hifmc_root="$WORKSPACE/sources/imc/hifmc/hifmc400"
        else
            # Fallback to finding hifmc directory relative to current location
            hifmc_root=$(echo "$base_dir" | sed 's|/hifmc/.*|/hifmc|')
        fi

        if [[ -d "$hifmc_root" ]]; then
            base_dir="$hifmc_root"
        fi
    fi

    # Find all CMakeLists.txt and *.cmake files
    find "$base_dir" -name "CMakeLists.txt" -o -name "*.cmake" 2>/dev/null | sort
}

# Function to resolve CMake variables to actual paths
resolve_cmake_variables() {
    local path="$1"
    local cmake_dir="${2:-$(pwd)}"

    # Check if WORKSPACE is set
    if [[ -z "$WORKSPACE" ]]; then
        echo "ERROR: WORKSPACE environment variable is not set" >&2
        exit 1
    fi

    # Basic variable resolution
    path="${path//\$\{CMAKE_CURRENT_LIST_DIR\}/$cmake_dir}"
    path="${path//\$\{CMAKE_CURRENT_SOURCE_DIR\}/$cmake_dir}"

    # HIF_SHARED variables
    if [[ "$path" =~ \$\{CMAKE_HIF_SHARED_HIF_DIR\} ]]; then
        path="${path//\$\{CMAKE_HIF_SHARED_HIF_DIR\}/$WORKSPACE/sources/imc/hif-shared}"
    fi

    # MEV_HW variables
    if [[ "$path" =~ \$\{CMAKE_MEV_HW_HIF_DIR\} ]]; then
        path="${path//\$\{CMAKE_MEV_HW_HIF_DIR\}/$WORKSPACE/sources/imc/mev_hw}"
    fi

    # Clean up path
    path=$(realpath -m "$path" 2>/dev/null || echo "$path")

    echo "$path"
}

# Function to extract library info from declare_library calls
extract_declare_library_includes() {
    local content="$1"
    local cmake_dir="$2"
    local includes=()

    # Extract declare_library calls and their PUBLICINCS
    local in_declare_library=false
    local in_pubincls=false

    while IFS= read -r line; do
        # Check for declare_library function call
        if [[ "$line" =~ declare_library\( ]]; then
            in_declare_library=true
            continue
        fi

        # Check for end of function call
        if [[ "$in_declare_library" == true && "$line" =~ ^\) ]]; then
            in_declare_library=false
            in_pubincls=false
            continue
        fi

        # Look for PUBLICINCS within declare_library
        if [[ "$in_declare_library" == true && "$line" =~ PUBLICINCS ]]; then
            in_pubincls=true
            continue
        fi

        # Extract paths when in PUBLICINCS section
        if [[ "$in_pubincls" == true && "$in_declare_library" == true ]]; then
            # Skip lines that contain other keywords
            if [[ "$line" =~ (SOURCES|PRIVATEDEPS|PUBLICDEPS|PRIVATEINCS) ]]; then
                in_pubincls=false
                continue
            fi

            # Extract include path
            local path
            path=$(echo "$line" | sed 's/^[[:space:]]*//' | sed 's/[[:space:]]*$//' | tr -d '"')

            if [[ -n "$path" && ! "$path" =~ ^\) ]]; then
                path=$(resolve_cmake_variables_with_defaults "$path" "$cmake_dir")
                if [[ -d "$path" ]]; then
                    includes+=("$path")
                fi
            fi
        fi
    done <<< "$content"

    # Also handle set(pubincls ...) patterns
    local in_pubincls_set=false
    while IFS= read -r line; do
        # Look for set(pubincls
        if [[ "$line" =~ set\(pubincls ]]; then
            in_pubincls_set=true
            continue
        fi

        # Look for closing parenthesis
        if [[ "$in_pubincls_set" == true && "$line" =~ ^\) ]]; then
            in_pubincls_set=false
            continue
        fi

        # Extract paths in pubincls set
        if [[ "$in_pubincls_set" == true ]]; then
            local path
            path=$(echo "$line" | sed 's/^[[:space:]]*//' | sed 's/[[:space:]]*$//' | tr -d '"')

            if [[ -n "$path" && ! "$path" =~ ^\) ]]; then
                path=$(resolve_cmake_variables_with_defaults "$path" "$cmake_dir")
                if [[ -d "$path" ]]; then
                    includes+=("$path")
                fi
            fi
        fi
    done <<< "$content"

    printf '%s\n' "${includes[@]}"
}

# Function to extract include directories from CMake content
extract_include_directories() {
    local content="$1"
    local cmake_dir="$2"
    local includes=()

    # Extract include_directories() commands
    while IFS= read -r line; do
        if [[ "$line" =~ include_directories\( ]]; then
            # Extract paths from parentheses
            local paths
            paths=$(echo "$line" | sed 's/.*include_directories[[:space:]]*([[:space:]]*//' | sed 's/[[:space:]]*).*//')

            # Process each path
            for path in $paths; do
                # Clean up path
                path=$(echo "$path" | tr -d '"' | tr -d "'" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//')

                if [[ -n "$path" ]]; then
                    # Resolve CMake variables
                    path=$(resolve_cmake_variables_with_defaults "$path" "$cmake_dir")

                    # Only include existing directories
                    if [[ -d "$path" ]]; then
                        includes+=("$path")
                    fi
                fi
            done
        fi

        # Extract target_include_directories() commands
        if [[ "$line" =~ target_include_directories\( ]]; then
            # Extract paths, skip target name and visibility specifiers
            local parts
            parts=$(echo "$line" | sed 's/.*target_include_directories[[:space:]]*([[:space:]]*//' | sed 's/[[:space:]]*).*//')
            # Remove first word (target name) and visibility keywords
            local paths
            paths=$(echo "$parts" | sed 's/^[^[:space:]]*[[:space:]]*//' | sed 's/PUBLIC//g' | sed 's/PRIVATE//g' | sed 's/INTERFACE//g')

            for path in $paths; do
                path=$(echo "$path" | tr -d '"' | tr -d "'" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//')

                if [[ -n "$path" ]]; then
                    path=$(resolve_cmake_variables_with_defaults "$path" "$cmake_dir")

                    if [[ -d "$path" ]]; then
                        includes+=("$path")
                    fi
                fi
            done
        fi
    done <<< "$content"

    # Also extract from declare_library calls
    local lib_includes
    readarray -t lib_includes < <(extract_declare_library_includes "$content" "$cmake_dir")
    includes+=("${lib_includes[@]}")

    printf '%s\n' "${includes[@]}"
}

# Function to extract compile definitions from CMake content
extract_compile_definitions() {
    local content="$1"
    local defines=()

    # Extract add_definitions() commands
    while IFS= read -r line; do
        if [[ "$line" =~ add_definitions\( ]]; then
            local defs
            defs=$(echo "$line" | sed 's/.*add_definitions[[:space:]]*([[:space:]]*//' | sed 's/[[:space:]]*).*//')

            for def in $defs; do
                def=$(echo "$def" | tr -d '"' | tr -d "'" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//')

                # Remove -D prefix if present
                if [[ "$def" == -D* ]]; then
                    def="${def#-D}"
                fi

                if [[ -n "$def" ]]; then
                    defines+=("$def")
                fi
            done
        fi
    done <<< "$content"

    # Extract add_compile_definitions() commands (handle multi-line)
    local in_compile_defs=false
    while IFS= read -r line; do
        # Start of add_compile_definitions
        if [[ "$line" =~ add_compile_definitions\( ]]; then
            in_compile_defs=true
            # Check if it's a single-line definition
            if [[ "$line" =~ \) ]]; then
                local defs
                defs=$(echo "$line" | sed 's/.*add_compile_definitions[[:space:]]*([[:space:]]*//' | sed 's/[[:space:]]*).*//')
                for def in $defs; do
                    def=$(echo "$def" | tr -d '"' | tr -d "'" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//')
                    [[ -n "$def" ]] && defines+=("$def")
                done
                in_compile_defs=false
            fi
            continue
        fi

        # Inside multi-line add_compile_definitions
        if [[ "$in_compile_defs" == true ]]; then
            # End of multi-line definition
            if [[ "$line" =~ \) ]]; then
                in_compile_defs=false
                # Process definitions on the closing line
                local remaining
                remaining=$(echo "$line" | sed 's/).*//')
                for def in $remaining; do
                    def=$(echo "$def" | tr -d '"' | tr -d "'" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//')
                    [[ -n "$def" ]] && defines+=("$def")
                done
                continue
            fi

            # Process definitions on this line
            for def in $line; do
                def=$(echo "$def" | tr -d '"' | tr -d "'" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//')
                [[ -n "$def" ]] && defines+=("$def")
            done
        fi
    done <<< "$content"

    # Extract target_compile_definitions() commands
    while IFS= read -r line; do
        if [[ "$line" =~ target_compile_definitions\( ]]; then
            local parts
            parts=$(echo "$line" | sed 's/.*target_compile_definitions[[:space:]]*([[:space:]]*//' | sed 's/[[:space:]]*).*//')
            # Remove first word (target name) and visibility keywords
            local defs
            defs=$(echo "$parts" | sed 's/^[^[:space:]]*[[:space:]]*//' | sed 's/PUBLIC//g' | sed 's/PRIVATE//g' | sed 's/INTERFACE//g')

            for def in $defs; do
                def=$(echo "$def" | tr -d '"' | tr -d "'" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//')

                if [[ -n "$def" ]]; then
                    defines+=("$def")
                fi
            done
        fi
    done <<< "$content"

    printf '%s\n' "${defines[@]}"
}


# Function to load CMake variable definitions from defaults.cmake
load_cmake_defaults() {
    # Check if WORKSPACE is set
    if [[ -z "$WORKSPACE" ]]; then
        echo "ERROR: WORKSPACE environment variable is not set" >&2
        exit 1
    fi

    local defaults_file="$WORKSPACE/sources/imc/hifmc/tools/cmake/config/defaults.cmake"

    if [[ ! -f "$defaults_file" ]]; then
        echo "Warning: defaults.cmake not found at $defaults_file, some variables may not resolve" >&2
        return 0
    fi

    echo "Loading CMake defaults from: $defaults_file" >&2

    # Extract variable definitions and resolve them to actual paths using WORKSPACE
    while IFS= read -r line; do
        if [[ "$line" =~ set\(([^[:space:]]+)[[:space:]]+\"([^\"]+)\"\) ]]; then
            local var_name="${BASH_REMATCH[1]}"
            local var_value="${BASH_REMATCH[2]}"

            # Resolve paths based on WORKSPACE/sources/imc structure
            case "$var_name" in
                "CMAKE_INFRA_COMMON_HIF_DIR")
                    CMAKE_INFRA_COMMON_HIF_DIR="$WORKSPACE/sources/imc/infra_common"
                    ;;
                "CMAKE_MEV_INFRA_HIF_DIR")
                    CMAKE_MEV_INFRA_HIF_DIR="$WORKSPACE/sources/imc/mev_infra"
                    ;;
                "CMAKE_MEV_HW_HIF_DIR")
                    CMAKE_MEV_HW_HIF_DIR="$WORKSPACE/sources/imc/mev_hw"
                    ;;
                "CMAKE_HIF_SHARED_HIF_DIR")
                    CMAKE_HIF_SHARED_HIF_DIR="$WORKSPACE/sources/imc/hif-shared"
                    ;;
                "CMAKE_MEV_IMC_SHARED_DIR")
                    CMAKE_MEV_IMC_SHARED_DIR="$WORKSPACE/sources/imc/imc_shared"
                    ;;
                "CMAKE_XT_COMMON_HIF_DIR")
                    CMAKE_XT_COMMON_HIF_DIR="$WORKSPACE/sources/imc/infra_common/xt_common"
                    ;;
            esac
        fi
    done < "$defaults_file"
}

# Function to resolve CMake variables using loaded defaults
resolve_cmake_variables_with_defaults() {
    local path="$1"
    local cmake_file_dir="${2:-}"

    # If cmake_file_dir is provided, resolve CMAKE_CURRENT_LIST_DIR relative to that file
    if [[ -n "$cmake_file_dir" ]]; then
        path="${path//\$\{CMAKE_CURRENT_LIST_DIR\}/$cmake_file_dir}"
        path="${path//\$\{CMAKE_CURRENT_SOURCE_DIR\}/$cmake_file_dir}"
    fi

    # Apply known variable mappings from defaults.cmake
    path="${path//\$\{CMAKE_INFRA_COMMON_HIF_DIR\}/$CMAKE_INFRA_COMMON_HIF_DIR}"
    path="${path//\$\{CMAKE_MEV_INFRA_HIF_DIR\}/$CMAKE_MEV_INFRA_HIF_DIR}"
    path="${path//\$\{CMAKE_MEV_HW_HIF_DIR\}/$CMAKE_MEV_HW_HIF_DIR}"
    path="${path//\$\{CMAKE_HIF_SHARED_HIF_DIR\}/$CMAKE_HIF_SHARED_HIF_DIR}"
    path="${path//\$\{CMAKE_MEV_IMC_SHARED_DIR\}/$CMAKE_MEV_IMC_SHARED_DIR}"
    path="${path//\$\{CMAKE_XT_COMMON_HIF_DIR\}/$CMAKE_XT_COMMON_HIF_DIR}"

    # Apply existing resolution logic for any remaining variables
    path=$(resolve_cmake_variables "$path" "$cmake_file_dir")

    echo "$path"
}

# Function to extract includes from set() variables like pubincls/privincls
extract_set_includes() {
    local content="$1"
    local cmake_dir="$2"
    local includes=()
    local in_set_block=false
    local current_var=""

    while IFS= read -r line; do
        # Detect set() calls for include variables
        if [[ "$line" =~ set\((pubincls|privincls|public_includes|private_includes) ]]; then
            in_set_block=true
            current_var="${BASH_REMATCH[1]}"
            continue
        fi

        # Detect end of set block
        if [[ "$in_set_block" == true && "$line" =~ ^\) ]]; then
            in_set_block=false
            current_var=""
            continue
        fi

        # Extract paths from set block
        if [[ "$in_set_block" == true ]]; then
            local path
            path=$(echo "$line" | sed 's/^[[:space:]]*//' | sed 's/[[:space:]]*$//' | tr -d '"')

            if [[ -n "$path" && ! "$path" =~ ^\) && ! "$path" =~ ^# ]]; then
                path=$(resolve_cmake_variables_with_defaults "$path" "$cmake_dir")
                if [[ -d "$path" ]]; then
                    includes+=("$path")
                fi
            fi
        fi
    done <<< "$content"

    printf '%s\n' "${includes[@]}"
}

# Main parsing function
parse_cmake_file() {
    local cmake_file="$1"
    local all_includes=()
    local all_definitions=()

    if [[ ! -f "$cmake_file" ]]; then
        echo "ERROR: CMake file not found: $cmake_file" >&2
        return 1
    fi

    # Load CMake defaults first
    load_cmake_defaults

    local file_dir
    file_dir=$(dirname "$cmake_file")

    # Process only the single CMake file (not scan entire directory)
    echo "Analyzing 1 CMake file..." >&2

    local content
    content=$(cat "$cmake_file")

    # Extract includes from this file
    local file_includes
    readarray -t file_includes < <(extract_include_directories "$content" "$file_dir")
    all_includes+=("${file_includes[@]}")

    # Extract includes from set() variables
    local set_includes
    readarray -t set_includes < <(extract_set_includes "$content" "$file_dir")
    all_includes+=("${set_includes[@]}")

    # Extract compile definitions from this file
    local file_definitions
    readarray -t file_definitions < <(extract_compile_definitions "$content")
    all_definitions+=("${file_definitions[@]}")

    # Remove duplicates and sort
    local unique_includes=()
    local unique_definitions=()

    # Sort and unique includes
    while IFS= read -r -d '' include; do
        if [[ -n "$include" && -d "$include" ]]; then
            unique_includes+=("$include")
        fi
    done < <(printf '%s\0' "${all_includes[@]}" | sort -uz)

    # Sort and unique definitions
    while IFS= read -r -d '' def; do
        if [[ -n "$def" ]]; then
            unique_definitions+=("$def")
        fi
    done < <(printf '%s\0' "${all_definitions[@]}" | sort -uz)

    echo "Found ${#unique_includes[@]} unique include paths and ${#unique_definitions[@]} definitions" >&2

    # Output in requested format
    if [[ "$OUTPUT_FORMAT" == "json" ]]; then
        printf '{\n'
        printf '  "include_directories": [\n'
        for i in "${!unique_includes[@]}"; do
            printf '    "%s"' "${unique_includes[$i]}"
            if [[ $i -lt $(( ${#unique_includes[@]} - 1 )) ]]; then
                printf ','
            fi
            printf '\n'
        done
        printf '  ],\n'
        printf '  "compile_definitions": [\n'
        for i in "${!unique_definitions[@]}"; do
            printf '    "%s"' "${unique_definitions[$i]}"
            if [[ $i -lt $(( ${#unique_definitions[@]} - 1 )) ]]; then
                printf ','
            fi
            printf '\n'
        done
        printf '  ]\n'
        printf '}\n'
    else
        printf 'Include directories:\n'
        printf '%s\n' "${unique_includes[@]}"
        printf '\nCompile definitions:\n'
        printf '%s\n' "${unique_definitions[@]}"
    fi
}

# Main execution
main() {
    parse_arguments "$@"

    if [[ -z "$CMAKE_FILE" ]]; then
        echo "ERROR: No CMake file specified" >&2
        show_help
        exit 1
    fi

    parse_cmake_file "$CMAKE_FILE"
}

# Run main function with all arguments
main "$@"
