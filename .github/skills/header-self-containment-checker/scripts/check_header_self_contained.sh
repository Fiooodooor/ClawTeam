#!/bin/bash

# Script to check if header files are self-contained (can compile standalone)
# Uses build configuration to determine appropriate include paths and compiler flags

set -euo pipefail

SCRIPT_VERSION="1.0.0"
BUILD_CONFIG_FILE=""
DIRECTORY=""
OUTPUT_FILE=""
PARALLEL_JOBS=1
LOG_LEVEL="INFO"
HEADER_FILES=()
COMPILER="gcc"

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
Header Self-Containment Checker v$SCRIPT_VERSION

USAGE:
    $0 [OPTIONS] HEADER_FILES...

DESCRIPTION:
    Checks if header files are self-contained by attempting to compile
    them standalone using build configuration extracted from Makefiles and CMake files.

OPTIONS:
    --build-config FILE     Build configuration JSON file
    --directory DIR         Base directory for the headers
    --output FILE           Output JSON file for results
    --parallel N            Number of parallel jobs (default: 1)
    --compiler COMPILER     Compiler to use: gcc, clang (default: gcc)
    --log-level LEVEL       Log level: QUIET, INFO, VERBOSE, DEBUG (default: INFO)
    -h, --help              Show this help message

EXAMPLES:
    $0 --build-config config.json --output results.json header1.h header2.h
    $0 --parallel 4 --directory /path/to/src --compiler clang *.h

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
            --build-config)
                BUILD_CONFIG_FILE="$2"
                shift 2
                ;;
            --directory)
                DIRECTORY="$2"
                shift 2
                ;;
            --output)
                OUTPUT_FILE="$2"
                shift 2
                ;;
            --parallel)
                PARALLEL_JOBS="$2"
                shift 2
                ;;
            --compiler)
                COMPILER="$2"
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
                HEADER_FILES+=("$1")
                shift
                ;;
        esac
    done

    if [[ ${#HEADER_FILES[@]} -eq 0 ]]; then
        log_error "At least one header file must be specified"
        exit 1
    fi

    if [[ -z "$OUTPUT_FILE" ]]; then
        log_error "Output file must be specified with --output"
        exit 1
    fi
}

# Function to extract compiler configuration for a directory
extract_compiler_config() {
    local target_dir="$1"
    local config_file="$2"
    local includes=()
    local defines=()

    log_debug "Extracting compiler config for: $target_dir"

    # If build config file is provided, extract includes from it
    if [[ -n "$config_file" && -f "$config_file" ]]; then
        log_debug "Reading build configuration from: $config_file"

    # Try new format first (flat format from collect_build_config.sh)
    local all_includes
    # Do not sort here; preserve order from collector (precedence matters)
    all_includes=$(jq -r '.include_directories[]?' "$config_file" 2>/dev/null)

        if [[ -n "$all_includes" ]]; then
            log_debug "Found includes from build config (new format)"
            while IFS= read -r include_path; do
                # Skip empty or root-only includes
                if [[ -n "$include_path" && "$include_path" != "null" && "$include_path" != "/" && -d "$include_path" ]]; then
                    includes+=("$include_path")
                fi
            done <<< "$all_includes"
        else
            # Try old format as fallback
            all_includes=$(jq -r '.directories[].build_files[].includes[]?' "$config_file" 2>/dev/null)

            if [[ -n "$all_includes" ]]; then
                log_debug "Found includes from build config (old format)"
                while IFS= read -r include_path; do
                    if [[ -n "$include_path" && "$include_path" != "null" && "$include_path" != "/" && -d "$include_path" ]]; then
                        includes+=("$include_path")
                    fi
                done <<< "$all_includes"
            else
                log_debug "No includes found in build config, falling back to discovery"
            fi
        fi

        # Extract compile definitions (try new format first)
        local all_defines
        all_defines=$(jq -r '.compile_definitions[]?' "$config_file" 2>/dev/null | sort -u)

        if [[ -z "$all_defines" ]]; then
            # Try old format as fallback
            all_defines=$(jq -r '.directories[].build_files[].defines[]?' "$config_file" 2>/dev/null | sort -u)
        fi

        if [[ -n "$all_defines" ]]; then
            while IFS= read -r define; do
                if [[ -n "$define" && "$define" != "null" ]]; then
                    defines+=("$define")
                fi
            done <<< "$all_defines"
        fi
    fi

    # If we still don't have includes, use discovery-based approach as fallback
    if [[ ${#includes[@]} -eq 0 ]]; then
        log_debug "Using discovery-based include path detection"

        # Add the target directory itself
        includes+=("$target_dir")

        # Find common include directory patterns
        while IFS= read -r dir; do
            includes+=("$dir")
        done < <(find "$target_dir" -type d -name "include" -o -name "inc" -o -name "src" 2>/dev/null | head -20)

        # Add parent directories that might contain headers
        local current_dir="$target_dir"
        while [[ "$current_dir" != "/" && "$current_dir" != "$WORKSPACE" ]]; do
            if [[ -d "$current_dir/include" ]]; then
                includes+=("$current_dir/include")
            fi
            if [[ -d "$current_dir/inc" ]]; then
                includes+=("$current_dir/inc")
            fi
            current_dir=$(dirname "$current_dir")
        done

        # Add workspace-level common include directories
        if [[ -n "${WORKSPACE:-}" ]]; then
            includes+=("$IMC_SHARED_DIR")
            # Add common public include roots explicitly
            if [[ -d "$HIF_SHARED_DIR/common/inc" ]]; then
                includes+=("$HIF_SHARED_DIR/common/inc")
            fi
            if [[ -d "$IMC_SHARED_DIR/csr_headers" ]]; then
                includes+=("$IMC_SHARED_DIR/csr_headers")
            fi
            if [[ -d "$IMC_INFRA_COMMON_LINUX_DIR/inc" ]]; then
                includes+=("$IMC_INFRA_COMMON_LINUX_DIR/inc")
            fi
            includes+=("$WORKSPACE/sources/imc/hwconfig")
        fi
    fi

    # Add critical include roots for userspace that may be missing from collected JSON
    if [[ -n "${WORKSPACE:-}" ]]; then
        if [[ "$target_dir" == *"/sources/imc/userspace"* || "$target_dir" == *"/userspace"* ]]; then
            local extra_paths=(
                "$WORKSPACE/sources/lan/nsl/nsl/include"
                "$WORKSPACE/sources/imc/infra_common/boot_reports_drv/include"
                "$WORKSPACE/sources/imc/mev_infra/lib_mmio_access/include"
                "$WORKSPACE/sources/imc/mev_utest/datapath/nsl_validation/libs/libcpf"
                "$WORKSPACE/sources/imc/mev_infra/lib_em/include"
                "$WORKSPACE/sources/imc/userspace/mev_imc_lm/lm_dnl_lib/inc"
                "$WORKSPACE/sources/imc/userspace/mev_imc_resets_handler/mmg/src/ifs/acc"
#                "$WORKSPACE/sources/kernel/6.12.8/drivers/infiniband/hw/irdma"
#                "$WORKSPACE/sources/kernel/6.12.8/tools/include"
#                "$WORKSPACE/sources/kernel/6.12.8/include"
#                "$WORKSPACE/sources/kernel/6.12.8/arch/arm/include"
#                "$WORKSPACE/sources/kernel/6.12.8/arch/arm64/include"
#                "$WORKSPACE/sources/imc/tools/ceedling/ut_mocks/nsc/infra/include"
            )
            for p in "${extra_paths[@]}"; do
                if [[ -d "$p" ]]; then
                    includes+=("$p")
                    log_debug "Added fallback include path: $p"
                fi
            done

            # GLib headers (host and cross)
            if [[ -d "/usr/include/glib-2.0" ]]; then
                includes+=("/usr/include/glib-2.0")
            fi
            if [[ -d "/usr/lib/x86_64-linux-gnu/glib-2.0/include" ]]; then
                includes+=("/usr/lib/x86_64-linux-gnu/glib-2.0/include")
            fi
            if [[ -d "/usr/aarch64-linux-gnu/include/glib-2.0" ]]; then
                includes+=("/usr/aarch64-linux-gnu/include/glib-2.0")
            fi
            if [[ -d "/usr/lib/aarch64-linux-gnu/glib-2.0/include" ]]; then
                includes+=("/usr/lib/aarch64-linux-gnu/glib-2.0/include")
            fi
        fi
    fi

    # Standard system includes
    includes+=(
        "/usr/include"
        "/usr/local/include"
    )
    # Cross sysroot includes commonly used by aarch64 toolchains
    if command -v aarch64-linux-gnu-gcc >/dev/null 2>&1; then
            if [[ -d "/usr/aarch64-linux-gnu/include" ]]; then
                includes+=("/usr/aarch64-linux-gnu/include")
            fi
        fi

        # Zephyr minimal libc headers for timespec/_timespec when Zephyr POSIX pulls them in
        if [[ -n "${WORKSPACE:-}" ]]; then
            local z_min="$WORKSPACE/sources/imc/zephyr/lib/libc/minimal/include"
            if [[ -d "$z_min" ]]; then
                includes+=("$z_min")
                log_debug "Added Zephyr minimal libc include path: $z_min"
            fi
    fi

    # Resilient TF-A (arm-tf) fallbacks: ensure key include roots are present
    if [[ "$target_dir" == *"/arm-tf"* ]]; then
        local atf_roots=(
            "$target_dir/include"
            "$target_dir/include/common"
            "$target_dir/include/arch/aarch64"
            "$target_dir/include/arch/aarch32"
            # Core TF-A lib headers (e.g. context.h)
            "$target_dir/include/lib"
            "$target_dir/include/lib/el3_runtime"
            "$target_dir/include/lib/el3_runtime/aarch64"
            "$target_dir/include/lib/el3_runtime/aarch32"
            "$target_dir/include/plat/common"
            "$target_dir/include/plat/arm/common"
            "$target_dir/include/plat/arm/common/aarch64"
            "$target_dir/include/drivers"
            # TBBR headers are under include/common/tbbr when included as <tbbr_img_def.h>
            "$target_dir/include/common/tbbr"
            # Intel LAN ft_logger headers (for ft_modules.h)
            "$target_dir/include/drivers/intel/lan/common/ft_logger"
        )
        for p in "${atf_roots[@]}"; do
            [[ -d "$p" ]] && includes+=("$p")
        done

        # Add platform include dirs (intel LAN variants and SoC trees)
        local pat
        for pat in \
            "$target_dir/plat/intel"/*/*/include \
            "$target_dir/plat/intel"/*/include \
            "$target_dir/include/plat/intel"/*/* \
            "$target_dir/include/plat/intel"/* \
            "$target_dir/plat/arm"/*/include \
            "$target_dir/plat/arm"/*/*/include; do
            if [[ -d $pat ]]; then
                includes+=("$pat")
            fi
        done

        # Add TF-A internal libc headers (cdefs.h, stddef_.h, limits_.h, inttypes_.h, setjmp_.h)
        local atf_libc=(
            "$target_dir/include/lib/libc"
            "$target_dir/include/lib/libc/sys"
            "$target_dir/include/lib/libc/aarch64"
            "$target_dir/include/lib/libc/aarch32"
        )
        for p in "${atf_libc[@]}"; do
            [[ -d "$p" ]] && includes+=("$p")
        done

        # Add TF-A services include roots used by SPMC/SPMD (spm_common.h, etc.)
        local atf_services=(
            "$target_dir/services"
            "$target_dir/services/std_svc"
            "$target_dir/services/std_svc/spm"
            "$target_dir/services/std_svc/spm/common/include"
            "$target_dir/services/std_svc/spm/el3_spmc"
            "$target_dir/services/std_svc/spm/spm_mm"
        )
        for p in "${atf_services[@]}"; do
            [[ -d "$p" ]] && includes+=("$p")
        done
        # Some TF-A forks place SPM dispatcher under el3_spmd; include if exists
        local spmd_dir="$target_dir/services/std_svc/spm/el3_spmd"
        [[ -d "$spmd_dir" ]] && includes+=("$spmd_dir")

        # libfdt headers are sometimes included as <libfdt/libfdt_env.h>
        local libfdt_paths=(
            "$target_dir/include/lib/libfdt"
            "$target_dir/lib/libfdt"
        )
        for p in "${libfdt_paths[@]}"; do
            [[ -d "$p" ]] && includes+=("$p")
        done

    # Add vendor/platform-specific includes that surface in failures
    # 1) Infra Common boot reports driver headers (boot_reports_drv.h)
    local boot_reports_inc="$WORKSPACE/sources/imc/infra_common/boot_reports_drv/include"
    [[ -d "$boot_reports_inc" ]] && includes+=("$boot_reports_inc")

    # 2) Socionext Synquacer common header (sq_common.h)
    local sq_inc="$target_dir/plat/socionext/synquacer/include"
    [[ -d "$sq_inc" ]] && includes+=("$sq_inc")

    # 3) TBBR cert_create public headers (e.g., <tbbr/tbb_ext.h>)
    local tbbr_tools_inc="$target_dir/tools/cert_create/include"
    [[ -d "$tbbr_tools_inc" ]] && includes+=("$tbbr_tools_inc")
    fi

    # Build compiler command arguments
    local compiler_args=()

    # Add include paths (only existing directories and skip root '/')
    for include in "${includes[@]}"; do
        if [[ -n "$include" && "$include" != "/" && -d "$include" ]]; then
            compiler_args+=("-I$include")
            log_debug "Added include path: $include"
        fi
    done

    # Add common defines for compilation
    compiler_args+=(
        "-DLINUX"
        "-D_GNU_SOURCE"
        "-D__STDC_LIMIT_MACROS"
        "-D__STDC_FORMAT_MACROS"
    )

    # Add compile definitions from build config (if any)
    if [[ ${#defines[@]} -gt 0 ]]; then
        for def in "${defines[@]}"; do
            # Skip empty/null
            [[ -z "$def" || "$def" == "null" ]] && continue
            compiler_args+=("-D$def")
            log_debug "Added compile definition: -D$def"
        done
    fi

    # Targeted safe default defines for TF-A header-only checks
    if [[ "$target_dir" == *"/arm-tf"* ]]; then
        # Avoid failures in RSS comms headers expecting platform-size macros
        compiler_args+=("-DPLAT_RSS_COMMS_PAYLOAD_MAX_SIZE=256")
        # Prefer TF-A bundled MbedTLS configs to avoid requiring external mbedtls/check_config.h
        if [[ -f "$target_dir/include/drivers/auth/mbedtls/mbedtls_config-3.h" ]]; then
            compiler_args+=("-DMBEDTLS_CONFIG_FILE=\"drivers/auth/mbedtls/mbedtls_config-3.h\"")
            log_debug "ATF define added: MBEDTLS_CONFIG_FILE=drivers/auth/mbedtls/mbedtls_config-3.h"
        elif [[ -f "$target_dir/include/drivers/auth/mbedtls/mbedtls_config-2.h" ]]; then
            compiler_args+=("-DMBEDTLS_CONFIG_FILE=\"drivers/auth/mbedtls/mbedtls_config-2.h\"")
            log_debug "ATF define added: MBEDTLS_CONFIG_FILE=drivers/auth/mbedtls/mbedtls_config-2.h"
        fi

        # If system PSA or mbedtls headers are present, add them as include roots
        # (helps find psa/crypto_types.h if libpsa or mbedtls3-dev is installed)
        for sys_psa in \
            "/usr/include/psa" \
            "/usr/local/include/psa"; do
            [[ -d "$sys_psa" ]] && compiler_args+=("-I$sys_psa")
        done
        for sys_mbed in \
            "/usr/include/mbedtls" \
            "/usr/local/include/mbedtls"; do
            [[ -d "$sys_mbed" ]] && compiler_args+=("-I$sys_mbed")
        done
    fi

    # Add standard flags for header checking
    compiler_args+=(
        "-fsyntax-only"  # Only check syntax, don't generate code
        "-Wall"          # Enable warnings
        "-std=c99"       # C99 standard
        "-x" "c"         # Treat as C source
        "-Wno-unused-variable"     # Ignore unused variable warnings in test
        "-Wno-unused-function"     # Ignore unused function warnings in test
    )

    log_debug "Generated ${#compiler_args[@]} compiler arguments"
    printf '%s\n' "${compiler_args[@]}"
}

# Function to check a single header file
check_header() {
    local header_file="$1"
    shift
    local compiler_args=("$@")
    local temp_dir="${compiler_args[-2]}"
    local header_index="${compiler_args[-1]}"

    # Remove temp_dir and header_index from compiler_args
    unset 'compiler_args[-1]'
    unset 'compiler_args[-1]'

    local result_file="$temp_dir/result_$header_index.json"
    local output_file="$temp_dir/output_$header_index.log"
    local temp_c_file="$temp_dir/test_$header_index.c"

    log_debug "Checking header: $header_file"

    # Convert absolute header path to relative path for #include
    local relative_header=""
    local header_basename=$(basename "$header_file")

    # Try to find the header relative to the directory we're checking
    if [[ -n "$DIRECTORY" ]]; then
        # Calculate relative path from the base directory
        relative_header=$(realpath --relative-to="$DIRECTORY" "$header_file" 2>/dev/null || echo "$header_basename")
    else
        relative_header="$header_basename"
    fi

    log_debug "Using relative header path: $relative_header"

    # Create a minimal C file that includes the header
    cat > "$temp_c_file" << EOF
/* Auto-generated test file for header self-containment check */
#include "$relative_header"

/* Empty main function to satisfy linker requirements */
int main(void) {
    return 0;
}
EOF

    # Try to compile the test file
    local compile_start=$(date +%s.%N)
    local compile_result=0
    local compile_output=""

    # Add the base directory as an include path if not already present
    local final_compiler_args=()
    final_compiler_args+=("${compiler_args[@]}")

    if [[ -n "$DIRECTORY" ]]; then
        # Add the base directory and common subdirectories as include paths
        final_compiler_args+=("-I$DIRECTORY")
        final_compiler_args+=("-I$(dirname "$header_file")")

        # Add common include directories
        for subdir in include inc src; do
            if [[ -d "$DIRECTORY/$subdir" ]]; then
                final_compiler_args+=("-I$DIRECTORY/$subdir")
            fi
        done
    fi

    log_debug "Compiler command: $COMPILER ${final_compiler_args[*]} $temp_c_file -o $temp_dir/test_$header_index"

    if compile_output=$("$COMPILER" "${final_compiler_args[@]}" "$temp_c_file" -o "$temp_dir/test_$header_index" 2>&1); then
        compile_result=0
        local status="PASSED"
        log_debug "✅ Header $header_file is self-contained"
    else
        compile_result=1
        local status="FAILED"
        log_debug "❌ Header $header_file failed self-containment check"
    fi

    local compile_end=$(date +%s.%N)
    local compile_time=$(echo "$compile_end - $compile_start" | bc -l 2>/dev/null || echo "0")

    # Save detailed output
    echo "$compile_output" > "$output_file"

    # Create result JSON (record the actual final compiler args used)
    # Build JSON safely: escape compiler args and output via jq
    local compiler_args_json
    compiler_args_json=$(printf '%s\n' "${final_compiler_args[@]}" | jq -R . | jq -s .)

    cat > "$result_file" << EOF
{
    "header_file": "$header_file",
    "status": "$status",
    "compile_time": $compile_time,
    "compiler": "$COMPILER",
    "compiler_args": $compiler_args_json,
    "compile_output": $(echo "$compile_output" | jq -Rs .),
    "timestamp": "$(date -Iseconds)"
}
EOF

    # Clean up temporary files
    rm -f "$temp_c_file" "$temp_dir/test_$header_index"

    return $compile_result
}

# Function to process headers in parallel
process_headers_parallel() {
    local compiler_args=("$@")
    local temp_dir=$(mktemp -d /tmp/header_check_XXXXXX)
    local results=()
    local job_pids=()
    local active_jobs=0
    local completed_jobs=0

    log_info "Processing ${#HEADER_FILES[@]} headers with $PARALLEL_JOBS parallel jobs"

    # Process headers in batches
    for i in "${!HEADER_FILES[@]}"; do
        local header_file="${HEADER_FILES[$i]}"

        # Wait if we've reached the maximum number of parallel jobs
        while [[ $active_jobs -ge $PARALLEL_JOBS ]]; do
            # Check for completed jobs
            local new_job_pids=()
            for pid in "${job_pids[@]}"; do
                if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
                    # Job still running
                    new_job_pids+=("$pid")
                else
                    # Job completed
                    if [[ -n "$pid" ]]; then
                        wait "$pid" 2>/dev/null || true
                        completed_jobs=$((completed_jobs + 1))
                        active_jobs=$((active_jobs - 1))
                    fi
                fi
            done
            job_pids=("${new_job_pids[@]}")

            # If still at max capacity, wait a bit
            if [[ $active_jobs -ge $PARALLEL_JOBS ]]; then
                sleep 0.1
            fi
        done

        # Start new job
        log_debug "Starting job for header $i: $header_file"
        check_header "$header_file" "${compiler_args[@]}" "$temp_dir" "$i" &
        local new_pid=$!
        job_pids+=("$new_pid")
        active_jobs=$((active_jobs + 1))

        # Progress reporting
        if [[ $((i % 10)) -eq 0 ]] || [[ $i -eq 0 ]]; then
            log_debug "Started $((i + 1))/${#HEADER_FILES[@]} jobs, $active_jobs active, $completed_jobs completed"
        fi
    done

    # Wait for all remaining jobs to complete
    log_info "Waiting for all jobs to complete..."
    for pid in "${job_pids[@]}"; do
        if [[ -n "$pid" ]]; then
            wait "$pid" 2>/dev/null || true
        fi
    done

    log_debug "All jobs completed, collecting results..."

    # Collect results
    local total_headers=${#HEADER_FILES[@]}
    local passed_count=0
    local failed_count=0

    for i in "${!HEADER_FILES[@]}"; do
        local result_file="$temp_dir/result_$i.json"
        if [[ -f "$result_file" ]]; then
            local result_content
            result_content=$(cat "$result_file")
            results+=("$result_content")

            # Count results using jq if available, fallback to grep
            if command -v jq >/dev/null 2>&1; then
                local status=$(jq -r '.status' "$result_file" 2>/dev/null || echo "UNKNOWN")
            else
                local status=$(grep -o '"status":[[:space:]]*"[^"]*"' "$result_file" | cut -d'"' -f4 || echo "UNKNOWN")
            fi

            if [[ "$status" == "PASSED" ]]; then
                passed_count=$((passed_count + 1))
            else
                failed_count=$((failed_count + 1))
            fi
        else
            log_warn "Missing result file for header $i: ${HEADER_FILES[$i]}"
            failed_count=$((failed_count + 1))
        fi
    done

    # Generate final results with proper JSON formatting
    local results_json=""
    if [[ ${#results[@]} -gt 0 ]]; then
        # Join results with commas
        results_json=$(printf '%s,\n' "${results[@]}" | sed '$s/,$//')
    fi

    cat > "$OUTPUT_FILE" << EOF
{
    "checker_version": "$SCRIPT_VERSION",
    "timestamp": "$(date -Iseconds)",
    "directory": "$DIRECTORY",
    "compiler": "$COMPILER",
    "parallel_jobs": $PARALLEL_JOBS,
    "summary": {
        "total": $total_headers,
        "passed": $passed_count,
        "failed": $failed_count,
        "skipped": 0,
        "success_rate": $(( total_headers > 0 ? (passed_count * 100) / total_headers : 0 ))
    },
    "results": [
$results_json
    ]
}
EOF

    # Clean up
    rm -rf "$temp_dir"

    log_info "Results: $passed_count passed, $failed_count failed out of $total_headers headers"

    # Always return success - we generated results successfully
    # The caller can check the results file for pass/fail statistics
    return 0
}

# Main function
main() {
    log_info "Header Self-Containment Checker v$SCRIPT_VERSION"
    log_info "Checking ${#HEADER_FILES[@]} header files"
    log_info "Using compiler: $COMPILER"

    # Check if compiler is available
    if ! command -v "$COMPILER" >/dev/null 2>&1; then
        log_error "Compiler not found: $COMPILER"
        exit 1
    fi

    # Extract compiler configuration
    local compiler_args=()
    if [[ -n "$BUILD_CONFIG_FILE" && -f "$BUILD_CONFIG_FILE" ]]; then
        log_info "Using build configuration: $BUILD_CONFIG_FILE"
        mapfile -t compiler_args < <(extract_compiler_config "$DIRECTORY" "$BUILD_CONFIG_FILE")

        # Fallback: if build-config extraction produced no args, synthesize sane defaults
        if [[ ${#compiler_args[@]} -eq 0 ]]; then
            log_warn "Build config produced no compiler args, using fallback include set"
            # Basic flags and defines
            compiler_args=(
                "-fsyntax-only"
                "-Wall"
                "-std=c99"
                "-x" "c"
                "-Wno-unused-variable"
                "-Wno-unused-function"
                "-DLINUX"
                "-D_GNU_SOURCE"
                "-D__STDC_LIMIT_MACROS"
                "-D__STDC_FORMAT_MACROS"
            )

            # Add base directory and common subdirs
            if [[ -n "$DIRECTORY" && -d "$DIRECTORY" ]]; then
                compiler_args+=("-I$DIRECTORY")
                for sub in include inc src; do
                    [[ -d "$DIRECTORY/$sub" ]] && compiler_args+=("-I$DIRECTORY/$sub")
                done
            fi

            # Module-specific safe fallbacks
            if [[ -n "${WORKSPACE:-}" ]]; then
                case "$DIRECTORY" in
                    */sources/imc/hif-shared*)
                        for p in \
                            "$WORKSPACE/sources/imc/hif-shared/common/inc" \
                            "$WORKSPACE/sources/imc/hif-shared/lib_hifmcdb/inc" \
                            "$WORKSPACE/sources/imc/hif-shared/lib_pci_reset/inc" \
                            "$WORKSPACE/sources/imc/infra_common/lib_mbx/include" \
                            "$WORKSPACE/sources/imc/hif-shared/common/inc" \
                            "$WORKSPACE/sources/imc/hif-shared/lib_hifmcdb/include"; do
                            [[ -d "$p" ]] && compiler_args+=("-I$p")
                        done
                        ;;
                    */sources/imc/infra_common*)
                        for p in \
                            "$WORKSPACE/sources/imc/infra_common/include" \
                            "$WORKSPACE/sources/imc/infra_common/json_utils/include" \
                            "$WORKSPACE/sources/imc/infra_common/string_utils/include" \
                            "$WORKSPACE/sources/imc/infra_common/xt_common/include" \
                            "$WORKSPACE/sources/imc/infra_common/boot_reports_drv/include" \
                            "$WORKSPACE/sources/imc/infra_common/lib_mbx/include" \
                            "$WORKSPACE/sources/imc/infra_common/lib_anvm/include" \
                            "$WORKSPACE/sources/imc/infra_common/lib_anvm/include/common" \
                            "$WORKSPACE/sources/imc/infra_common/lib_anvm/src/common" \
                            "$WORKSPACE/sources/imc/infra_common/lib_dmac/include" \
                            "$WORKSPACE/sources/imc/infra_common/lib_flash/include" \
                            "$WORKSPACE/sources/imc/infra_common/lib_flash_mtd/include" \
                            "$WORKSPACE/sources/imc/infra_common/lib_i2c_dw_drv/include" \
                            "$WORKSPACE/sources/imc/infra_common/lib_jedec_sfdp/include" \
                            "$WORKSPACE/sources/imc/infra_common/lib_nvm/include" \
                            "$WORKSPACE/sources/imc/infra_common/lib_nvm/src" \
                            "$WORKSPACE/sources/imc/infra_common/lib_pfuse_drv/include" \
                            "$WORKSPACE/sources/imc/infra_common/lib_spi_drv/include" \
                            "$WORKSPACE/sources/imc/infra_common/lib_spi_drv/src/v1" \
                            "$WORKSPACE/sources/imc/infra_common/lib_spi_drv/src/v2" \
                            "$WORKSPACE/sources/imc/infra_common/lib_tap_access/include" \
                            "$WORKSPACE/sources/imc/infra_common/lib_xft/include" \
                            "$WORKSPACE/sources/imc/hif-shared/common/inc" \
                            "$WORKSPACE/sources/imc/mev_hw" \
                            "$WORKSPACE/sources/imc/mev_infra/lib_ic/include" \
                            "$WORKSPACE/sources/imc/mev_infra/lib_ft/include" \
                            "$WORKSPACE/sources/imc/mev_infra/lib_xft/include" \
                            "$WORKSPACE/sources/imc/mev_infra/lib_osal/include" \
                            "$WORKSPACE/sources/imc/mev_infra/lib_mmio_access/include"; do
                            [[ -d "$p" ]] && compiler_args+=("-I$p")
                        done
                        ;;
                    */sources/imc/hifmc/hifmc_rom*)
                        for p in \
                            "$WORKSPACE/sources/imc/imc_shared/csr_headers"; do
                            [[ -d "$p" ]] && compiler_args+=("-I$p")
                        done
                        ;;
                    */sources/imc/mev_hw*)
                        for p in \
                            "$WORKSPACE/sources/imc/mev_hw" \
                            "$WORKSPACE/sources/imc/mev_hw/mmg" \
                            "$WORKSPACE/sources/imc/mev_hw/mmg/rdma" \
                            "$WORKSPACE/sources/imc/mev_hw/mmg/ecm2" \
                            "$WORKSPACE/sources/imc/mev_hw/nsssip"; do
                            [[ -d "$p" ]] && compiler_args+=("-I$p")
                        done
                        ;;
                    */sources/imc/mev_infra*)
                        for p in \
                            "$WORKSPACE/sources/imc/mev_infra/lib_osal/include"; do
                            [[ -d "$p" ]] && compiler_args+=("-I$p")
                        done
                        ;;
                    */sources/imc/mmg_pmu*)
                        for p in \
                            "$WORKSPACE/sources/imc/mmg_pmu/drivers/pmbus_drv"; do
                            [[ -d "$p" ]] && compiler_args+=("-I$p")
                        done
                        ;;
                esac
            fi
        fi

        # Module-specific safe fallbacks
        if [[ -n "${WORKSPACE:-}" ]]; then
            case "$DIRECTORY" in
                */sources/imc/mev_infra*)
                    for p in \
                        "$WORKSPACE/sources/imc/mev_infra/lib_ecm2/include" \
                        "$WORKSPACE/sources/imc/mev_infra/lib_mmio_access/include" \
                        "$WORKSPACE/sources/imc/mev_infra/lib_ic/include" \
                        "$WORKSPACE/sources/imc/mev_infra/lib_ft/include" \
                        "$WORKSPACE/sources/imc/mev_infra/lib_xft/include" \
                        "$WORKSPACE/sources/imc/mev_hw/mev/otp" \
                        "$WORKSPACE/sources/imc/zephyr/include" \
                        "$WORKSPACE/sources/imc/zephyr/build_config/kernel_build_config/zephyr/include/generated" \
                        "$WORKSPACE/sources/imc/zephyr/lib/libc/minimal/include" \
                        "$WORKSPACE/sources/imc/mev_infra/lib_sw_timer/include" \
                        "$WORKSPACE/sources/imc/mev_infra/lib_smc/include" \
                        "$WORKSPACE/sources/imc/mev_infra/lib_otp/include/" \
                        "$WORKSPACE/sources/imc/zephyr/include/drivers/intel/" \
                        "$WORKSPACE/sources/imc/zephyr/include/zephyr/" \
                        "$WORKSPACE/sources/imc/mev_hw" \
                        "$WORKSPACE/sources/imc/mev_hw/mmg/otp" \
                        "$WORKSPACE/sources/imc/mev_infra/lib_osal/include"; do
                        [[ -d "$p" ]] && compiler_args+=("-I$p")
                    done
                    ;;
                */sources/imc/hifmc/hifmc_rom*)
                    for p in \
                        "$WORKSPACE/sources/imc/hifmc/hifmc_rom/src/debug/include" \
                        "$WORKSPACE/sources/imc/hifmc/hifmc_rom/src/include" \
                        "$WORKSPACE/sources/imc/hifmc/hifmc_rom/src/tlp/include" \
                        "$WORKSPACE/sources/imc/hifmc/hifmc_rom/src/hal/csr_drv/include" \
                        "$WORKSPACE/sources/imc/hifmc/hifmc_rom/src/hal/fabric/include" \
                        "$WORKSPACE/sources/imc/hifmc/hifmc_rom/src/hal/util/include" \
                        "$WORKSPACE/sources/imc/hifmc/hifmc_rom/src/lib_hifmcdb/include" \
                        "$WORKSPACE/sources/imc/hifmc/hifmc_rom/external_include/hif-shared/common/inc" \
                        "$WORKSPACE/sources/imc/hifmc/hifmc_rom/external_include/mev_hw/nsssip/hif" \
                        "$WORKSPACE/sources/imc/hifmc/hifmc_rom/external_include/mev_hw/nsssip/rdma" \
                        "$WORKSPACE/sources/imc/hifmc/hifmc_rom/external_include/mev_hw/nsssip/sep" \
                        "$WORKSPACE/sources/imc/hifmc/hifmc_rom/external_include/mev_hw/nsssip/lanpe" \
                        "$WORKSPACE/sources/imc/hifmc/hifmc_rom/external_include/mev_hw/nsssip/ate" \
                        "$WORKSPACE/sources/imc/hifmc/hifmc_rom/external_include/mev_hw/nsssip/pkb" \
                        "$WORKSPACE/sources/imc/hif-shared/common/inc" \
                        "$WORKSPACE/sources/imc/mev_infra/lib_xft/include/" \
                        "$WORKSPACE/sources/imc/mev_infra/lib_ft/include/" \
                        "$WORKSPACE/sources/imc/hifmc/hifmc_rom/external_include/mev_hw/mmg" \
                        "$WORKSPACE/sources/imc/hifmc/hifmc_rom/external_include/mev_hw/mmg/snps" \
                        "$WORKSPACE/sources/imc/hifmc/hifmc_rom/external_include/mev_hw/mmg/cpm" \
                        "$WORKSPACE/sources/imc/hifmc/hifmc_rom/external_include/mev_hw/mmg/nvme" \
                        "/opt/Xtensa_Explorer/XtDevTools/install/tools/RI-2022.10-linux/XtensaTools/xtensa-elf/include" \
                        "/opt/Xtensa_Explorer/XtDevTools/install/tools/RI-2022.10-linux/XtensaTools/xtensa-elf/include/xtensa" \
                        "/opt/Xtensa_Explorer/XtDevTools/install/builds/RI-2022.10-linux/hifmc/xtensa-elf/arch/include" \
                        "/opt/Xtensa_Explorer/XtDevTools/install/builds/RI-2022.10-linux/hifmc/xtensa-elf/arch/include/xtensa/config" \
                        "/opt/Xtensa_Explorer/XtDevTools/install/builds/RI-2022.10-linux/hifmc/xtensa-elf/include" \
                        "$WORKSPACE/sources/imc/imc_shared/csr_headers"; do
                        [[ -d "$p" ]] && compiler_args+=("-I$p")
                    done
                    ;;
                */sources/imc/mmg_pmu*)
                    for p in \
                        "/opt/Xtensa_Explorer/XtDevTools/install/tools/RI-2022.10-linux/XtensaTools/xtensa-elf/include" \
                        "/opt/Xtensa_Explorer/XtDevTools/install/tools/RI-2022.10-linux/XtensaTools/xtensa-elf/include/xtensa" \
                        "/opt/Xtensa_Explorer/XtDevTools/install/builds/RI-2022.10-linux/pmu_core/xtensa-elf/arch/include" \
                        "/opt/Xtensa_Explorer/XtDevTools/install/builds/RI-2022.10-linux/pmu_core/xtensa-elf/arch/include/xtensa/config" \
                        "/opt/Xtensa_Explorer/XtDevTools/install/builds/RI-2022.10-linux/pmu_core/xtensa-elf/include" \
                        "$WORKSPACE/sources/imc/tools/ceedling/ceed_ws/vendor/ceedling/vendor/unity/src" \
                        "$WORKSPACE/sources/imc/imc_shared/csr_headers/mmg/acc" \
                        "$WORKSPACE/sources/imc/mmg_pmu/libs" \
                        "$WORKSPACE/sources/imc/mmg_pmu/ptm_flows" \
                        "$WORKSPACE/sources/imc/mmg_pmu/common/include" \
                        "$WORKSPACE/sources/imc/imc_shared/csr_headers/mmg/imc" \
                        "$WORKSPACE/sources/imc/mmg_pmu/libs/dac_lib" \
                        "$WORKSPACE/sources/imc/mmg_pmu/libs/dac_lib/include" \
                        "$WORKSPACE/sources/imc/mmg_pmu/drivers/pvt_drv" \
                        "$WORKSPACE/sources/imc/mmg_pmu/drivers/vr_drv" \
                        "$WORKSPACE/sources/imc/mmg_pmu/plat/mmg/pvt" \
                        "$WORKSPACE/sources/imc/mmg_pmu/bins" \
                        "$WORKSPACE/sources/imc/mmg_pmu/drivers/pmbus_drv"; do
                        [[ -d "$p" ]] && compiler_args+=("-I$p")
                    done
                    ;;
                */sources/lan/nsl*)
                    for p in \
                        "/opt/Xtensa_Explorer/XtDevTools/install/tools/RI-2022.10-linux/XtensaTools/xtensa-elf/include" \
                        "/opt/Xtensa_Explorer/XtDevTools/install/tools/RI-2022.10-linux/XtensaTools/xtensa-elf/include/xtensa" \
                        "/opt/Xtensa_Explorer/XtDevTools/install/builds/RI-2022.10-linux/hifmc/xtensa-elf/arch/include" \
                        "/opt/Xtensa_Explorer/XtDevTools/install/builds/RI-2022.10-linux/hifmc/xtensa-elf/arch/include/xtensa/config" \
                        "/opt/Xtensa_Explorer/XtDevTools/install/builds/RI-2022.10-linux/hifmc/xtensa-elf/include" \
                        "$WORKSPACE/sources/imc/mev_infra/lib_sw_timer/include" \
                        "$WORKSPACE/sources/imc/mev_infra/lib_ft/include" \
                        "$WORKSPACE/sources/imc/hif-shared/common/inc" \
                        "$WORKSPACE/sources/imc/mev_hw/nsssip/ts" \
                        "$WORKSPACE/sources/imc/mev_hw/nsssip/ice" \
                        "$WORKSPACE/sources/imc/mev_hw/nsssip/cxp" \
                        "$WORKSPACE/sources/imc/mev_hw/nsssip/hif" \
                        "$WORKSPACE/sources/imc/mev_hw/nsssip/bsr" \
                        "$WORKSPACE/sources/imc/mev_hw/nsssip/rdma" \
                        "$WORKSPACE/sources/imc/mev_hw/nsssip/fxp" \
                        "$WORKSPACE/sources/imc/mev_hw/mmg/bsr" \
                        "$WORKSPACE/sources/imc/mev_hw/nsssip/hif-nocss" \
                        "$WORKSPACE/sources/imc/mev_hw/mmg/lanpe" \
                        "$WORKSPACE/sources/imc/mev_hw/mmg/cosq" \
                        "$WORKSPACE/sources/imc/mev_hw/mmg/ice" \
                        "$WORKSPACE/sources/imc/mev_hw/mmg/hif" \
                        "$WORKSPACE/sources/imc/mev_hw/mmg/cxp" \
                        "$WORKSPACE/sources/imc/mev_hw/mmg/ate" \
                        "$WORKSPACE/sources/imc/mev_hw/mmg/snps" \
                        "$WORKSPACE/sources/imc/mev_hw/mmg/rdma" \
                        "$WORKSPACE/sources/imc/mev_hw/mmg/fxp" \
                        "$WORKSPACE/sources/imc/mev_hw/nsssip/cosq" \
                        "$WORKSPACE/sources/imc/mev_hw/nsssip/lanpe" \
                        "$WORKSPACE/sources/imc/mev_hw/nsssip/pkb" \
                        "$WORKSPACE/sources/imc/tools/ceedling/ut_mocks/nsc/infra/include/generated" \
                        "$WORKSPACE/sources/imc/tools/ceedling/ut_mocks/nsc/infra/include" \
                        "$WORKSPACE/sources/imc/zephyr/include" \
                        "$WORKSPACE/sources/imc/mev_hw/mmg/pkb" \
                        "$WORKSPACE/sources/imc/hif-shared/lib_mbx/inc" \
                        "$WORKSPACE/sources/imc/mev_hw/mmg/ts" \
                        "$WORKSPACE/sources/imc/mev_infra/lib_osal/include"; do
                        [[ -d "$p" ]] && compiler_args+=("-I$p")
                    done
                    ;;
                */sources/imc/imc_shared*)
                    for p in \
                        "$WORKSPACE/sources/imc/imc_shared/nvm_headers/mev_ts/veloce/"; do
                        [[ -d "$p" ]] && compiler_args+=("-I$p")
                    done
                    ;;
                */sources/imc/physs*)
                    for p in \
                        "$WORKSPACE/sources/imc/physs/mev/include" \
                        "$WORKSPACE/sources/imc/physs/mev/include/xos" \
                        "$WORKSPACE/sources/imc/physs/mmg/include/serdes_ip/production_sdk" \
                        "$WORKSPACE/sources/imc/physs/mmg/include/serdes_ip/production_sdk/regblk" \
                        "/opt/Xtensa_Explorer/XtDevTools/install/tools/RI-2022.10-linux/XtensaTools/xtensa-elf/include" \
                        "/opt/Xtensa_Explorer/XtDevTools/install/tools/RI-2022.10-linux/XtensaTools/xtensa-elf/include/xtensa" \
                        "/opt/Xtensa_Explorer/XtDevTools/install/builds/RI-2022.10-linux/physs_core/xtensa-elf/arch/include" \
                        "/opt/Xtensa_Explorer/XtDevTools/install/builds/RI-2022.10-linux/physs_core/xtensa-elf/arch/include/xtensa/config" \
                        "/opt/Xtensa_Explorer/XtDevTools/install/builds/RI-2022.10-linux/physs_core/xtensa-elf/include" \
                        "$WORKSPACE/sources/imc/physs/mev/include/inphi"; do
                        [[ -d "$p" ]] && compiler_args+=("-I$p")
                    done
                    ;;
            esac
        fi

        # Always-on TF-A safety net: ensure critical include roots are present for ATF
        if [[ "$DIRECTORY" == *"/arm-tf"* ]]; then
            local atf_root="$DIRECTORY"
            # Map existing -I paths
            declare -A seen_inc
            local a
            for a in "${compiler_args[@]}"; do
                if [[ "$a" == -I* ]]; then
                    seen_inc["${a#-I}"]=1
                fi
            done
            # Inject essential TF-A include roots unconditionally (when present on disk)
            # Cover: el3_runtime (context.h), arch helpers, internal libc (cdefs.h, stddef_.h, limits_.h, inttypes_.h, setjmp_.h),
            #        TBBR, Intel ft_logger, SPM services, and a default platform selection to satisfy <platform_def.h>.
            local must_have=(
                # External
                "/usr/aarch64-linux-gnu/include"
                # "/usr/include/x86_64-linux-gnu"
                # Core
                "$atf_root/include"
                "$atf_root/include/common"
                "$atf_root/include/arch/aarch64"
                "$atf_root/include/arch/aarch32"
                "$atf_root/include/lib/el3_runtime"
                "$atf_root/include/lib/el3_runtime/aarch64"
                "$atf_root/include/lib/el3_runtime/aarch32"
                # Core TF-A lib (for <lib/mmio.h> and similar)
                "$atf_root/include/lib"
                # TF-A internal libc
                "$atf_root/include/lib/libc"
                "$atf_root/include/lib/libc/sys"
                "$atf_root/include/lib/libc/aarch64"
                "$atf_root/include/lib/libc/aarch32"
                # PSA API headers (for <psa/client.h>)
                "$atf_root/include/lib/psa"
                # libfdt headers
                "$atf_root/include/lib/libfdt"
                "$atf_root/lib/libfdt"
                # TBBR and ft_logger
                "$atf_root/include/common/tbbr"
                "$atf_root/tools/cert_create/include"
                "$atf_root/include/drivers/intel/lan/common/ft_logger"
                "$atf_root/include/drivers/intel/lan/common/xft_logger"
                # SPM services (spm_common.h, SPMC/SPMD helpers)
                "$atf_root/services"
                "$atf_root/services/std_svc"
                "$atf_root/services/std_svc/spm"
                "$atf_root/services/std_svc/spm/common/include"
                "$atf_root/services/std_svc/spm/el3_spmc"
                "$atf_root/services/std_svc/spm/spm_mm"
                # Default Intel platform includes (for <platform_def.h>)
                "$atf_root/plat/intel/lan/mmg_imc/include"
                "$atf_root/plat/intel/lan/mev_imc/include"
                "$atf_root/plat/intel/lan/common/include"
                "$atf_root/plat/intel/soc/common/include"
                # Intel include/plat short-form headers (e.g., <board_imc_def.h>)
                "$atf_root/include/plat/intel/lan/mmg_imc"
                "$atf_root/include/plat/intel/lan/mev_imc"
                "$atf_root/include/plat/intel/lan/nsc"
                # Arm CSS SGI platforms (<sgi_sdei.h>)
                "$atf_root/plat/arm/css/sgi/include"
                # SBB driver public headers
                "$atf_root/drivers/intel/lan/mmg_imc/sbb_drv/include"
                "$atf_root/drivers/intel/lan/nsc/sbb_drv/include"
                # Intel LAN qch/mss subtrees commonly included directly
                "$atf_root/include/drivers/intel/lan/mmg_imc/qch"
                "$atf_root/include/drivers/intel/lan/nsc/qch"
                "$atf_root/include/drivers/intel/lan/mev_imc/mss_shared"
                # HIFMC defs live under platform directories
                "$atf_root/plat/intel/lan/mmg_imc"
                "$atf_root/plat/intel/lan/nsc"
                # SoCFPGA platform include dirs (resolve socfpga_plat_def.h used broadly)
                "$atf_root/plat/intel/soc/common/include"
                "$atf_root/plat/intel/soc/stratix10/include"
                "$atf_root/plat/intel/soc/agilex/include"
                "$atf_root/plat/intel/soc/n5x/include"
                "$atf_root/plat/intel/soc/agilex5/include"
                # Others
                "$atf_root/bl32/tsp/tsp_private.h"
            )
            local p
            for p in "${must_have[@]}"; do
                if [[ -d "$p" && -z "${seen_inc[$p]:-}" ]]; then
                    compiler_args+=("-I$p")
                    seen_inc["$p"]=1
                    log_debug "ATF must-have include added: $p"
                fi
            done

            # Add SPMD directory if present
            local spmd_dir="$atf_root/services/std_svc/spm/el3_spmd"
            if [[ -d "$spmd_dir" && -z "${seen_inc[$spmd_dir]:-}" ]]; then
                compiler_args+=("-I$spmd_dir")
                seen_inc["$spmd_dir"]=1
                log_debug "ATF SPMD include added: $spmd_dir"
            fi

            # Add a few external-but-in-repo roots commonly referenced by TF-A platforms
            if [[ -n "${WORKSPACE:-}" ]]; then
                local extra_roots=(
                    "$WORKSPACE/sources/imc/imc_shared/csr_headers"
                    "$WORKSPACE/sources/imc/infra_common/include"
                    # Boot reports driver headers used by infra_common ipu_lsm_* headers
                    "$WORKSPACE/sources/imc/infra_common/boot_reports_drv/include"
                    "$WORKSPACE/sources/imc/hif-shared/common/inc"
                    "$WORKSPACE/sources/imc/hif-shared/lib_hifmcdb/inc"
                    "$WORKSPACE/sources/imc/hif-shared/lib_pci_reset/inc"
                    # Generated NVM headers (if present)
                    "$WORKSPACE/sources/imc/imc_shared/nvm_headers"
                    "$WORKSPACE/sources/imc/imc_shared/nvm_headers/mev"
                    "$WORKSPACE/sources/imc/imc_shared/nvm_headers/mmg"
                    "$WORKSPACE/sources/imc/imc_shared/nvm_headers/nsc"
                    # External shared headers used by TF-A platforms/drivers
                    "$WORKSPACE/sources/imc/mev_infra/lib_ecm2/include"
                    "$WORKSPACE/sources/imc/mev_hw/mmg/ecm2"
                    "$WORKSPACE/sources/imc/mev_hw/mmg/rdma"
                    "$WORKSPACE/sources/imc/mev_hw/mmg"
                )
                for p in "${extra_roots[@]}"; do
                    if [[ -d "$p" && -z "${seen_inc[$p]:-}" ]]; then
                        compiler_args+=("-I$p")
                        seen_inc["$p"]=1
                        log_debug "ATF external include added: $p"
                    fi
                done

                # Targeted CSR and platform roots commonly required by Intel LAN drivers
                # Ensure headers like syscon_mmg_nmf.h, DWC_ddrctl_mmg_nmf.h, csr_syscon_nsssip_nmf.h are discoverable
                local targeted_roots=(
                    "$WORKSPACE/sources/imc/imc_shared/csr_headers/mmg/imc"
                    "$WORKSPACE/sources/imc/imc_shared/csr_headers/mmg/mss"
                    "$WORKSPACE/sources/imc/imc_shared/csr_headers/nsssip/nmc"
                    "$WORKSPACE/sources/imc/mev_hw/nsssip/hif-nocss"
                )
                for p in "${targeted_roots[@]}"; do
                    if [[ -d "$p" && -z "${seen_inc[$p]:-}" ]]; then
                        compiler_args+=("-I$p")
                        seen_inc["$p"]=1
                        log_debug "ATF targeted include added: $p"
                    fi
                done
            fi

            # Also add vendor platform-specific roots not covered by build-config
            # 1) Socionext Synquacer common headers (for <sq_common.h>)
            local sq_inc="$atf_root/plat/socionext/synquacer/include"
            if [[ -d "$sq_inc" && -z "${seen_inc[$sq_inc]:-}" ]]; then
                compiler_args+=("-I$sq_inc")
                seen_inc["$sq_inc"]=1
                log_debug "ATF vendor include added: $sq_inc"
            fi

            # 2) Intel LAN common driver subtrees that are included as bare headers (e.g., "dw_spi.h")
            local lan_common_subs=(
                "$atf_root/include/drivers/intel/lan/common/dw_spi"
                "$atf_root/include/drivers/intel/lan/common/dw_dmac"
            )
            for p in "${lan_common_subs[@]}"; do
                if [[ -d "$p" && -z "${seen_inc[$p]:-}" ]]; then
                    compiler_args+=("-I$p")
                    seen_inc["$p"]=1
                    log_debug "ATF LAN include added: $p"
                fi
            done
        fi
    else
        log_warn "No build configuration provided, using default settings"
        compiler_args=(
            "-fsyntax-only"
            "-Wall"
            "-Wextra"
            "-std=c99"
            "-x" "c"
        )
        if [[ -n "$DIRECTORY" && -d "$DIRECTORY" ]]; then
            compiler_args+=("-I$DIRECTORY")
        fi
    fi

    # Final guarantee: ensure critical TF-A defines are present in the final compiler args
    if [[ "$DIRECTORY" == *"/arm-tf"* ]]; then
        # Helper to check if an arg exists
        has_arg() {
            local needle="$1"; shift
            local a
            for a in "$@"; do
                if [[ "$a" == "$needle"* ]]; then
                    return 0
                fi
            done
            return 1
        }

        # Ensure PLAT_RSS_COMMS_PAYLOAD_MAX_SIZE define is present
        if ! has_arg "-DPLAT_RSS_COMMS_PAYLOAD_MAX_SIZE" "${compiler_args[@]}"; then
            compiler_args+=("-DPLAT_RSS_COMMS_PAYLOAD_MAX_SIZE=256")
            log_debug "ATF define appended: PLAT_RSS_COMMS_PAYLOAD_MAX_SIZE=256"
        fi

        # Ensure MBEDTLS_CONFIG_FILE define is present, prefer in-tree TF-A configs
        if ! has_arg "-DMBEDTLS_CONFIG_FILE" "${compiler_args[@]}"; then
            if [[ -f "$DIRECTORY/include/drivers/auth/mbedtls/mbedtls_config-3.h" ]]; then
                compiler_args+=("-DMBEDTLS_CONFIG_FILE=\"drivers/auth/mbedtls/mbedtls_config-3.h\"")
                log_debug "ATF define appended: MBEDTLS_CONFIG_FILE=drivers/auth/mbedtls/mbedtls_config-3.h"
            elif [[ -f "$DIRECTORY/include/drivers/auth/mbedtls/mbedtls_config-2.h" ]]; then
                compiler_args+=("-DMBEDTLS_CONFIG_FILE=\"drivers/auth/mbedtls/mbedtls_config-2.h\"")
                log_debug "ATF define appended: MBEDTLS_CONFIG_FILE=drivers/auth/mbedtls/mbedtls_config-2.h"
            fi
        fi

        # Optionally ensure system PSA/mbedtls include roots if installed
        # Add only if paths exist and not already included
        for sys_psa in \
            "/usr/include/psa" \
            "/usr/local/include/psa"; do
            if [[ -d "$sys_psa" ]] && ! has_arg "-I$sys_psa" "${compiler_args[@]}"; then
                compiler_args+=("-I$sys_psa")
                log_debug "ATF sys include appended: $sys_psa"
            fi
        done
        for sys_mbed in \
            "/usr/include/mbedtls" \
            "/usr/local/include/mbedtls"; do
            if [[ -d "$sys_mbed" ]] && ! has_arg "-I$sys_mbed" "${compiler_args[@]}"; then
                compiler_args+=("-I$sys_mbed")
                log_debug "ATF sys include appended: $sys_mbed"
            fi
        done
    fi

    log_debug "Compiler arguments (final): ${compiler_args[*]}"

    # Process headers
    process_headers_parallel "${compiler_args[@]}" || true

    # Post-process: print accurate summary based on OUTPUT_FILE
    if [[ -f "$OUTPUT_FILE" ]]; then
        if command -v jq >/dev/null 2>&1; then
            local p=$(jq -r '.summary.passed // 0' "$OUTPUT_FILE" 2>/dev/null || echo 0)
            local f=$(jq -r '.summary.failed // 0' "$OUTPUT_FILE" 2>/dev/null || echo 0)
        else
            local p=$(grep -o '"passed"[[:space:]]*:[[:space:]]*[0-9]\+' "$OUTPUT_FILE" | head -1 | grep -o '[0-9]\+' || echo 0)
            local f=$(grep -o '"failed"[[:space:]]*:[[:space:]]*[0-9]\+' "$OUTPUT_FILE" | head -1 | grep -o '[0-9]\+' || echo 0)
        fi
        if [[ "$f" -gt 0 ]]; then
            log_warn "Some headers failed self-containment check ($p passed, $f failed)"
        else
            log_info "All headers passed self-containment check"
        fi
    fi

    # Always exit successfully since we generated results
    exit 0
}

# Script entry point
if [[ "${BASH_SOURCE[0]:-}" == "${0}" ]]; then
    parse_arguments "$@"
    main
fi
