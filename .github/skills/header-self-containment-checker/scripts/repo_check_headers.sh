#!/bin/bash

# Main script to check if header files are self-contained
# This script analyzes Makefiles and CMakeFiles to determine include paths and dependencies
# then tests each header file for self-containment (can compile standalone)

set -euo pipefail

# Script version and info
SCRIPT_VERSION="1.0.0"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Check if WORKSPACE is set
if [[ -z "${WORKSPACE:-}" ]]; then
    echo "❌ ERROR: WORKSPACE environment variable is not set." >&2
    echo "Please run 'source imc_setenv nsc' first to set up the environment." >&2
    exit 1
fi

# Default configuration
DEFAULT_PARALLEL_JOBS=4
DEFAULT_LOG_LEVEL="INFO"
DEFAULT_QUIET=false
DEFAULT_LOG_FILE=""
DEFAULT_OUTPUT_DIR="$SCRIPT_DIR/header_check_output"
DEFAULT_NO_CLEANUP=true  # Changed default to preserve existing data

# Global configuration variables
PARALLEL_JOBS=$DEFAULT_PARALLEL_JOBS
LOG_LEVEL=$DEFAULT_LOG_LEVEL
QUIET=$DEFAULT_QUIET
LOG_FILE=$DEFAULT_LOG_FILE
OUTPUT_DIR=$DEFAULT_OUTPUT_DIR
SELECTED_DIRECTORIES=()
CHECK_ALL_DIRS=false
NO_CLEANUP=$DEFAULT_NO_CLEANUP
REPORT_MISSING_HEADERS=false
# When enabled, present analysis using analyze_header_failures.sh per module
PRESENT_ANALYSIS=false

# Define all available directories with their environment variables
declare -A AVAILABLE_DIRECTORIES=(
    ["atf"]="${IMC_ATF_DIR:-$WORKSPACE/sources/imc/arm-tf}"
    ["boot"]="${IMC_BOOT_DIR:-$WORKSPACE/sources/imc/boot}"
    ["infra-common"]="${IMC_INFRA_COMMON_DIR:-$WORKSPACE/sources/imc/infra_common}"
    ["nsl"]="${IMC_NSL_DIR:-$WORKSPACE/sources/lan/nsl}"
    ["physs-mmg"]="${IMC_PHYSS_DIR_MMG:-$WORKSPACE/sources/imc/physs/mmg}"
    ["physs-mev"]="${IMC_PHYSS_DIR_MEV:-$WORKSPACE/sources/imc/physs/mev}"
    ["shared"]="${IMC_SHARED_DIR:-$WORKSPACE/sources/imc/imc_shared}"
    ["userspace"]="${IMC_USERSPACE_DIR:-$WORKSPACE/sources/imc/userspace}"
    ["uboot"]="${IMC_UBOOT_DIR:-$WORKSPACE/sources/imc/u-boot}"
    ["hifmc"]="${HIFMC_SRC_DIR:-$WORKSPACE/sources/imc/hifmc}"
    ["hifmc_rom"]="${HIFMC_ROM_DIR:-$WORKSPACE/sources/imc/hifmc_rom}"
    ["hif-shared"]="${HIF_SHARED_DIR:-$WORKSPACE/sources/imc/hif-shared}"
    ["mmg-pmu"]="${MMG_PMU_DIR:-$WORKSPACE/sources/imc/mmg_pmu}"
    ["mev_hw"]="${MEV_HW_DIR:-$WORKSPACE/sources/imc/mev_hw}"
    ["mev_infra"]="${MEV_INFRA_DIR:-$WORKSPACE/sources/imc/mev_infra}"
)

# Define default compiler per directory
# ARM-TF typically uses ARM cross-compiler, others use GCC by default
declare -A DIRECTORY_DEFAULT_COMPILER=(
    ["atf"]="aarch64-linux-gnu-gcc"
    ["boot"]="gcc"
    ["infra-common"]="gcc"
    ["nsl"]="gcc"
    ["physs-mmg"]="gcc"
    ["physs-mev"]="gcc"
    ["shared"]="gcc"
    ["userspace"]="aarch64-linux-gnu-gcc"
    ["uboot"]="aarch64-linux-gnu-gcc"
    ["hifmc"]="gcc"
    ["hifmc_rom"]="gcc"
    ["hif-shared"]="gcc"
    ["mmg-pmu"]="gcc"
    ["mev_hw"]="gcc"
    ["mev_infra"]="gcc"
)

# Expected subpath (relative to $WORKSPACE) for each module; used to sanity-check env overrides
declare -A DIRECTORY_EXPECTED_SUBPATH=(
    ["atf"]="/sources/imc/arm-tf"
    ["boot"]="/sources/imc/boot"
    ["infra-common"]="/sources/imc/infra_common"
    ["nsl"]="/sources/lan/nsl"
    ["physs-mmg"]="/sources/imc/physs/mmg"
    ["physs-mev"]="/sources/imc/physs/mev"
    ["shared"]="/sources/imc/imc_shared"
    ["userspace"]="/sources/imc/userspace"
    ["uboot"]="/sources/imc/u-boot"
    ["hifmc"]="/sources/imc/hifmc/hifmc400"
    ["hifmc_rom"]="/sources/imc/hifmc/hifmc_rom"
    ["hif-shared"]="/sources/imc/hif-shared"
    ["mmg-pmu"]="/sources/imc/mmg_pmu"
    ["mev_hw"]="/sources/imc/mev_hw"
    ["mev_infra"]="/sources/imc/mev_infra"
)

# Define exclude patterns per directory for header file filtering
# Supports both simple patterns and regex (prefix with 'regex:')
# These patterns apply to header files that should be excluded from self-containment checks
# For ATF: exclude all plat directories except intel and arm using regex
declare -A DIRECTORY_EXCLUDE_PATTERNS=(
    ["atf"]="*/tests/* */tools/* */tools/cert_create/* */tools/fiptool/*
        regex:.*/plat/(?!(intel)/).*
        regex:.*/include/drivers/(?!(intel)/).*
        regex:.*/atm-tf/drivers/(?!(intel)/).*"
    ["boot"]="*/tests/*"
    ["infra-common"]="*/tests/* */utest/* */third_party/* */vendor/* */unity/* */ceedling/*"
    ["nsl"]="*/test/* */tests/* */sources/lan/nsl/shared/mev_hw/*"
    ["physs-mmg"]="*/test/* */tests/* */utests/*"
    ["physs-mev"]="*/test/* */tests/* */utests/*"
    ["shared"]="*/test/* */tests/*"
    ["userspace"]="*/test/* */tests/* */utest/* */mev_imc_mctp_stack/utest/* */mev_imc_mctp_hw_config/utest/* */tdd_tests/* */mev_imc_dpcp_src/src/libcpf/src/NSL/shared/mev_hw/* *kernel/6.12.8/*"
    ["uboot"]="*/test/* */tests/*"
    ["hifmc"]="*/test/* */tests/*"
    ["hifmc_rom"]="*/test/* */tests/* */utest/*"
    ["hif-shared"]="*/test/* */tests/*"
    ["mmg-pmu"]="*/test/* */tests/*"
    ["mev_hw"]="*/test/* */tests/*"
    ["mev_infra"]="*/test/* */tests/* */utest/*"
)

# Helper scripts
MAKEFILE_PARSER="$SCRIPT_DIR/parse_makefiles.sh"
CMAKE_PARSER="$SCRIPT_DIR/parse_cmake.sh"
HEADER_CHECKER="$SCRIPT_DIR/check_header_self_contained.sh"
BUILD_CONFIG_COLLECTOR="$SCRIPT_DIR/collect_build_config.sh"

# Logging functions
log_error() {
    [[ "$LOG_LEVEL" != "QUIET" ]] && echo "❌ ERROR: $*" >&2
    if [[ -n "${LOG_FILE:-}" ]]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: $*" >> "$LOG_FILE"
    fi
}

log_warn() {
    [[ "$LOG_LEVEL" != "QUIET" ]] && echo "⚠️  WARN: $*" >&2
    if [[ -n "${LOG_FILE:-}" ]]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] WARN: $*" >> "$LOG_FILE"
    fi
}

log_info() {
    [[ "$LOG_LEVEL" != "QUIET" && ! "$QUIET" == "true" ]] && echo "ℹ️  INFO: $*" >&2
    if [[ -n "${LOG_FILE:-}" ]]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] INFO: $*" >> "$LOG_FILE"
    fi
}

log_debug() {
    [[ "$LOG_LEVEL" == "DEBUG" ]] && echo "🔍 DEBUG: $*" >&2
    if [[ -n "${LOG_FILE:-}" ]]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] DEBUG: $*" >> "$LOG_FILE"
    fi
}

log_verbose() {
    [[ "$LOG_LEVEL" == "VERBOSE" || "$LOG_LEVEL" == "DEBUG" ]] && echo "📝 VERBOSE: $*" >&2
    if [[ -n "${LOG_FILE:-}" ]]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] VERBOSE: $*" >> "$LOG_FILE"
    fi
}

# Function to show available directories
show_directories() {
    echo "Available directories:"
    for dir_key in $(printf '%s\n' "${!AVAILABLE_DIRECTORIES[@]}" | sort); do
        dir_path="${AVAILABLE_DIRECTORIES[$dir_key]}"
        default_compiler="${DIRECTORY_DEFAULT_COMPILER[$dir_key]}"
        if [[ -d "$dir_path" ]]; then
            # Check if compiler is available
            if command -v "$default_compiler" >/dev/null 2>&1; then
                echo "   ✅ $dir_key: $dir_path (compiler: $default_compiler ✅)"
            else
                echo "   ⚠️  $dir_key: $dir_path (compiler: $default_compiler ❌ not found)"
            fi
        else
            echo "   ❌ $dir_key: $dir_path (not found)"
        fi
    done
}

# Function to create helper scripts
create_helper_scripts() {
    local scripts_dir="$SCRIPT_DIR/scripts"
    mkdir -p "$scripts_dir"

    log_info "Verifying helper scripts in $scripts_dir"

    # Check if all required helper scripts exist
    local required_scripts=(
        "$MAKEFILE_PARSER"
        "$CMAKE_PARSER"
        "$HEADER_CHECKER"
        "$BUILD_CONFIG_COLLECTOR"
    )

    local missing_scripts=()
    for script in "${required_scripts[@]}"; do
        if [[ ! -f "$script" ]]; then
            missing_scripts+=("$script")
        else
            # Make sure it's executable
            chmod +x "$script"
        fi
    done

    if [[ ${#missing_scripts[@]} -gt 0 ]]; then
        log_error "Missing required helper scripts:"
        for script in "${missing_scripts[@]}"; do
            log_error "  - $script"
        done
        log_error "Please ensure all helper scripts are present in the scripts/ directory"
        exit 1
    fi

    log_info "All helper scripts are available and executable"
}

# Function to show help
show_help() {
    cat << EOF
Header Self-Containment Checker v$SCRIPT_VERSION

USAGE:
    $0 [OPTIONS] [DIRECTORIES...]

DESCRIPTION:
    This script checks if header files are self-contained (can compile standalone)
    by analyzing Makefiles and CMakeFiles to determine include paths and dependencies.
    Each directory uses its appropriate default compiler (e.g., ARM cross-compiler for ATF).

DIRECTORIES:
    If no directories are specified, defaults to 'userspace'
    Multiple directories can be specified as arguments
    Each directory has a default compiler assigned based on its build requirements

EOF
    show_directories
    cat << EOF

OPTIONS:
    -p, --parallel N        Run N jobs in parallel (default: $DEFAULT_PARALLEL_JOBS)
    -l, --log FILE          Save detailed log to FILE
    -o, --output DIR        Output directory for results (default: $DEFAULT_OUTPUT_DIR)
    -q, --quiet             Quiet mode - minimal output
    -v, --verbose           Verbose output
    -d, --debug             Debug output
    -a, --all               Check all available directories
    --cleanup               Clean up existing module data before starting (default: preserve)
    --no-cleanup            Preserve existing results (default behavior)
    --list                  List available directories and exit
    --report-missing-headers  Print end-of-run stats for missing headers and a sorted list
    --present-analysis        Run analyzer on results: ./analyze_header_failures.sh header_check_output/<DIRECTORY>_results.json
    -h, --help              Show this help message

EXAMPLES:
    $0                              # Check userspace only (default)
    $0 atf userspace                # Check ARM-TF and userspace
    $0 -a                           # Check all available directories
    $0 --list                       # List available directories
    $0 -p 8 -v atf boot hifmc       # Check 3 directories with 8 parallel jobs, verbose
    $0 -q -l results.log userspace  # Check userspace quietly, log to file

WORKFLOW:
    1. Parse Makefiles and CMakeFiles to extract include paths and dependencies
    2. Collect build configuration for each directory
    3. Find all header files in the directories
    4. Test each header file for self-containment
    5. Generate summary report

REQUIREMENTS:
    - WORKSPACE environment variable must be set (run 'source imc_setenv nsc')
    - Appropriate compilers available (gcc for most modules, aarch64-linux-gnu-gcc for ARM modules)
    - Standard build tools (make, cmake if applicable)
    - Use --list to see which compilers are required and available

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
            --list)
                show_directories
                exit 0
                ;;
            -a|--all)
                CHECK_ALL_DIRS=true
                shift
                ;;
            -p|--parallel)
                PARALLEL_JOBS="$2"
                if ! [[ "$PARALLEL_JOBS" =~ ^[0-9]+$ ]] || [[ "$PARALLEL_JOBS" -lt 1 ]]; then
                    log_error "Invalid parallel jobs count: $PARALLEL_JOBS"
                    exit 1
                fi
                shift 2
                ;;
            -l|--log)
                LOG_FILE="$2"
                shift 2
                ;;
            -o|--output)
                OUTPUT_DIR="$2"
                shift 2
                ;;
            -q|--quiet)
                QUIET=true
                LOG_LEVEL="QUIET"
                shift
                ;;
            -v|--verbose)
                LOG_LEVEL="VERBOSE"
                shift
                ;;
            -d|--debug)
                LOG_LEVEL="DEBUG"
                shift
                ;;
            --cleanup)
                NO_CLEANUP=false
                shift
                ;;
            --no-cleanup)
                NO_CLEANUP=true
                shift
                ;;
            --report-missing-headers)
                REPORT_MISSING_HEADERS=true
                shift
                ;;
            --present-analysis)
                PRESENT_ANALYSIS=true
                shift
                ;;
            -*)
                log_error "Unknown option: $1"
                echo "Use -h or --help for usage information"
                exit 1
                ;;
            *)
                # This is a directory name
                if [[ -n "${AVAILABLE_DIRECTORIES[$1]:-}" ]]; then
                    SELECTED_DIRECTORIES+=("$1")
                else
                    log_error "Unknown directory: $1"
                    echo "Use --list to see available directories"
                    exit 1
                fi
                shift
                ;;
        esac
    done

    # Set default directory if no directories are selected
    if [[ ${#SELECTED_DIRECTORIES[@]} -eq 0 && "$CHECK_ALL_DIRS" == "false" ]]; then
        SELECTED_DIRECTORIES=("userspace")
    fi

    # If --all flag is used, select all directories
    if [[ "$CHECK_ALL_DIRS" == "true" ]]; then
        SELECTED_DIRECTORIES=($(printf '%s\n' "${!AVAILABLE_DIRECTORIES[@]}" | sort))
    fi
}

# Initialize output directory and logging
initialize_output() {
    local original_args="$1"

    # Create output directory first
    mkdir -p "$OUTPUT_DIR"

    # Clean up only specific module data if not preserving everything
    if [[ "$NO_CLEANUP" == false ]] && [[ -d "$OUTPUT_DIR" ]] && [[ -n "$(ls -A "$OUTPUT_DIR" 2>/dev/null)" ]]; then
        log_info "🧹 Cleaning up existing results in $OUTPUT_DIR"
        rm -rf "$OUTPUT_DIR"/*
        mkdir -p "$OUTPUT_DIR"
    elif [[ "$NO_CLEANUP" == true ]] && [[ -d "$OUTPUT_DIR" ]] && [[ -n "$(ls -A "$OUTPUT_DIR" 2>/dev/null)" ]]; then
        # Clean up only the files for modules we're about to process
        for dir_name in "${SELECTED_DIRECTORIES[@]}"; do
            # Clean up module-specific files
            rm -f "$OUTPUT_DIR/${dir_name}_build_config.json" 2>/dev/null || true
            rm -f "$OUTPUT_DIR/${dir_name}_results.json" 2>/dev/null || true
            rm -f "$OUTPUT_DIR/${dir_name}_summary.json" 2>/dev/null || true
            log_debug "Cleaned up existing data for module: ${dir_name}"
        done
        log_info "📁 Preserving existing results in $OUTPUT_DIR (--no-cleanup specified)"
    fi

    # Initialize log file if specified
    if [[ -n "$LOG_FILE" ]]; then
        # Make log file path absolute if it's relative
        if [[ "$LOG_FILE" != /* ]]; then
            LOG_FILE="$OUTPUT_DIR/$LOG_FILE"
        fi

        # Create log file directory if needed
        mkdir -p "$(dirname "$LOG_FILE")"

        # Initialize log file
        cat > "$LOG_FILE" << EOF
# Header Self-Containment Check Log
# Generated on: $(date)
# Script version: $SCRIPT_VERSION
# Command: $0 $original_args
# Workspace: $WORKSPACE
# Output directory: $OUTPUT_DIR
# Parallel jobs: $PARALLEL_JOBS
# Selected directories: ${SELECTED_DIRECTORIES[*]:-none}

EOF
        log_info "Logging to: $LOG_FILE"
    fi

    log_info "Output directory: $OUTPUT_DIR"
}

# Function to check if a header file should be excluded based on patterns
should_exclude_header() {
    local path="$1"
    local patterns="$2"  # Space-separated patterns

    [[ "$LOG_LEVEL" == "DEBUG" ]] && log_debug "Checking exclude for header file: $path"

    # Check if patterns is empty
    if [[ -z "$patterns" ]]; then
        [[ "$LOG_LEVEL" == "DEBUG" ]] && log_debug "  ✅ NOT EXCLUDED (no patterns)"
        return 1  # Should not exclude
    fi

    # Convert space-separated patterns to array
    local pattern_array=()
    read -ra pattern_array <<< "$patterns"

    # Check against exclude patterns
    for pattern in "${pattern_array[@]}"; do
        [[ "$LOG_LEVEL" == "DEBUG" ]] && log_debug "  Testing against pattern: $pattern"
        if check_header_pattern_match "$path" "$pattern"; then
            [[ "$LOG_LEVEL" == "DEBUG" ]] && log_debug "  ✅ EXCLUDED by pattern: $pattern"
            return 0  # Should exclude
        fi
    done

    [[ "$LOG_LEVEL" == "DEBUG" ]] && log_debug "  ✅ NOT EXCLUDED"
    return 1  # Should not exclude
}

# Function to check if a path matches a pattern (supports glob, regex, and exceptions)
check_header_pattern_match() {
    local path="$1"
    local pattern="$2"

    [[ "$LOG_LEVEL" == "DEBUG" ]] && log_debug "    Matching '$path' against '$pattern'"

    # Handle regex patterns (prefix with 'regex:')
    if [[ "$pattern" == regex:* ]]; then
        local regex_pattern="${pattern#regex:}"
        [[ "$LOG_LEVEL" == "DEBUG" ]] && log_debug "    Using regex: $regex_pattern"
        # Use perl-compatible regex if available, otherwise use bash regex
        if command -v grep >/dev/null 2>&1; then
            if echo "$path" | grep -qP "$regex_pattern" 2>/dev/null; then
                [[ "$LOG_LEVEL" == "DEBUG" ]] && log_debug "    ✅ Regex match with grep -P"
                return 0  # Match
            else
                [[ "$LOG_LEVEL" == "DEBUG" ]] && log_debug "    ❌ No regex match with grep -P"
            fi
        else
            # Fallback to bash regex (more limited)
            if [[ "$path" =~ $regex_pattern ]]; then
                [[ "$LOG_LEVEL" == "DEBUG" ]] && log_debug "    ✅ Regex match with bash"
                return 0  # Match
            else
                [[ "$LOG_LEVEL" == "DEBUG" ]] && log_debug "    ❌ No regex match with bash"
            fi
        fi
    # Handle glob patterns and substring matching
    else
        # Support glob patterns with extglob (try both raw and with leading */ for absolute paths)
        shopt -s extglob nullglob
        if [[ "$path" == $pattern ]]; then
            [[ "$LOG_LEVEL" == "DEBUG" ]] && log_debug "    ✅ Glob match"
            shopt -u extglob nullglob
            return 0  # Match
        fi
        # If the pattern is relative-like, try matching with a leading */ to align with absolute paths
        if [[ "$pattern" != /* ]]; then
            local alt_pattern="*/$pattern"
            if [[ "$path" == $alt_pattern ]]; then
                [[ "$LOG_LEVEL" == "DEBUG" ]] && log_debug "    ✅ Glob match (alt */ prefix)"
                shopt -u extglob nullglob
                return 0
            fi
        fi
        shopt -u extglob nullglob

        # Support substring matching for folders
        if [[ "$path" == *"$pattern"* ]]; then
            [[ "$LOG_LEVEL" == "DEBUG" ]] && log_debug "    ✅ Substring match"
            return 0  # Match
        else
            [[ "$LOG_LEVEL" == "DEBUG" ]] && log_debug "    ❌ No glob/substring match"
        fi
    fi

    return 1  # No match
}

# Main execution function
main() {
    log_info "Header Self-Containment Checker v$SCRIPT_VERSION"
    log_info "Workspace: $WORKSPACE"

    # Create helper scripts
    create_helper_scripts

    # Validate selected directories
    local directories_to_check=()
    local directories_to_check_names=()
    for dir_name in "${SELECTED_DIRECTORIES[@]}"; do
        dir_path="${AVAILABLE_DIRECTORIES[$dir_name]}"
        default_compiler="${DIRECTORY_DEFAULT_COMPILER[$dir_name]}"

        if [[ -d "$dir_path" ]]; then
            # Sanity-check env-provided paths: ensure they point to the expected module folder
            local expected_subpath="${DIRECTORY_EXPECTED_SUBPATH[$dir_name]:-}"
            if [[ -n "$expected_subpath" && "$dir_path" != *"$expected_subpath"* ]]; then
                local expected_abs="$WORKSPACE$expected_subpath"
                if [[ -d "$expected_abs" ]]; then
                    log_warn "⚠️  Path for $dir_name points to '$dir_path' (unexpected); using '$expected_abs' instead"
                    dir_path="$expected_abs"
                else
                    log_warn "⚠️  Path for $dir_name ('$dir_path') does not match expected subpath '$expected_subpath', and fallback '$expected_abs' not found; continuing with provided path"
                fi
            fi

            # Check if the default compiler is available
            if command -v "$default_compiler" >/dev/null 2>&1; then
                directories_to_check+=("$dir_path")
                directories_to_check_names+=("$dir_name")
                log_info "✅ Will check: $dir_name ($dir_path) with compiler: $default_compiler"
            else
                log_warn "⚠️  Directory $dir_name found but compiler not available: $default_compiler"
                log_warn "   Attempting to use fallback compiler 'gcc' for $dir_name"
                if command -v "gcc" >/dev/null 2>&1; then
                    directories_to_check+=("$dir_path")
                    directories_to_check_names+=("$dir_name")
                    log_info "✅ Will check: $dir_name ($dir_path) with fallback compiler: gcc"
                else
                    log_error "❌ Neither default compiler ($default_compiler) nor fallback (gcc) available for $dir_name"
                fi
            fi
        else
            log_warn "❌ Directory not found: $dir_name ($dir_path) - skipping"
        fi
    done

    if [[ ${#directories_to_check[@]} -eq 0 ]]; then
        log_error "No valid directories to check"
        exit 1
    fi

    log_info "Starting header self-containment check for ${#directories_to_check[@]} directories"
    log_info "Using $PARALLEL_JOBS parallel jobs"

    # Phase 1: Collect build configuration for each module separately
    log_info "Phase 1: Collecting build configuration..."

    # Generate build config for each module separately
    for i in "${!directories_to_check[@]}"; do
        local dir_path="${directories_to_check[$i]}"
        local dir_name="${directories_to_check_names[$i]}"
        local build_config_file="$OUTPUT_DIR/${dir_name}_build_config.json"

        log_info "Generating build config for module: $dir_name"

        # Get exclude patterns for this directory
        local exclude_patterns="${DIRECTORY_EXCLUDE_PATTERNS[$dir_name]:-}"
        local exclude_args=()

        if [[ -n "$exclude_patterns" ]]; then
            log_info "Using exclude patterns for $dir_name: $exclude_patterns"
            # Convert space-separated patterns to array and build exclude args
            for pattern in $exclude_patterns; do
                exclude_args+=(--exclude "$pattern")
            done
        fi

        if ! "$BUILD_CONFIG_COLLECTOR" \
            --output "$build_config_file" \
            --parallel "$PARALLEL_JOBS" \
            --log-level "DEBUG" \
            --module "$dir_name" \
            "${exclude_args[@]}" \
            "$dir_path"; then
            log_error "Failed to collect build configuration for $dir_name"
            exit 1
        fi

        log_info "Build config saved: $build_config_file"
    done

    # Phase 2: Find and check all header files
    log_info "Phase 2: Finding and checking header files..."

    local total_headers=0
    local passed_headers=0
    local failed_headers=0
    local skipped_headers=0

    # Process each directory
    for i in "${!directories_to_check[@]}"; do
        local dir_path="${directories_to_check[$i]}"
        local dir_name="${directories_to_check_names[$i]}"

        log_info "Processing directory: $dir_name ($dir_path)"

        # Get exclude patterns for this directory
        local exclude_patterns="${DIRECTORY_EXCLUDE_PATTERNS[$dir_name]:-}"

        # Find all header files in this directory
        local all_header_files=()
        mapfile -t all_header_files < <(
            find "$dir_path" -type f \( -name "*.h" -o -name "*.hpp" -o -name "*.hxx" \) 2>/dev/null | sort
        )

        if [[ ${#all_header_files[@]} -eq 0 ]]; then
            log_warn "No header files found in $dir_name"
            continue
        fi

        log_info "Found ${#all_header_files[@]} total header files in $dir_name"

        # Filter header files based on exclude patterns
        local header_files=()
        local excluded_count=0

        if [[ -n "$exclude_patterns" ]]; then
            log_info "Applying exclude patterns for $dir_name: $exclude_patterns"
            local progress_counter=0
            for header_file in "${all_header_files[@]}"; do
                # Use safer arithmetic - avoid issues with set -e
                ((progress_counter++)) || true

                # Show progress every 100 files processed
                if [[ $((progress_counter % 100)) -eq 0 ]]; then
                    log_info "Progress: processed $progress_counter/${#all_header_files[@]} files, excluded $excluded_count so far"
                fi

                if should_exclude_header "$header_file" "$exclude_patterns"; then
                    log_verbose "Excluding header file: $header_file"
                    ((excluded_count++)) || true
                else
                    header_files+=("$header_file")
                fi
            done
            log_info "Excluded $excluded_count header files, checking ${#header_files[@]} remaining"
        else
            header_files=("${all_header_files[@]}")
            log_info "No exclude patterns specified, checking all ${#header_files[@]} header files"
        fi

        if [[ ${#header_files[@]} -eq 0 ]]; then
            log_warn "No header files remaining after filtering in $dir_name"
            continue
        fi
        total_headers=$((total_headers + ${#header_files[@]}))

        # Check headers in parallel using module-specific build config
        local dir_results_file="$OUTPUT_DIR/${dir_name}_results.json"
        local module_build_config="$OUTPUT_DIR/${dir_name}_build_config.json"

        # Determine which compiler to use for this module
        local module_compiler="${DIRECTORY_DEFAULT_COMPILER[$dir_name]}"
        if ! command -v "$module_compiler" >/dev/null 2>&1; then
            log_warn "Default compiler $module_compiler not found for $dir_name, falling back to gcc"
            module_compiler="gcc"
            if ! command -v "$module_compiler" >/dev/null 2>&1; then
                log_error "Fallback compiler gcc also not available for $dir_name"
                continue
            fi
        fi

        # Always try to run header checker and then check for results file
        log_info "Starting header checker for $dir_name with ${#header_files[@]} files using compiler: $module_compiler..."
        if "$HEADER_CHECKER" \
            --build-config "$module_build_config" \
            --directory "$dir_path" \
            --output "$dir_results_file" \
            --parallel "$PARALLEL_JOBS" \
            --compiler "$module_compiler" \
            --log-level "DEBUG" \
            "${header_files[@]}"; then
            log_info "Header checker completed successfully for $dir_name"
        else
            log_warn "Header checker finished with errors for $dir_name"
        fi

        # Check if results were generated, regardless of exit code
        if command -v jq >/dev/null 2>&1 && [[ -f "$dir_results_file" ]]; then
            local dir_passed=$(jq -r '.summary.passed // 0' "$dir_results_file")
            local dir_failed=$(jq -r '.summary.failed // 0' "$dir_results_file")
            local dir_skipped=$(jq -r '.summary.skipped // 0' "$dir_results_file")

            passed_headers=$((passed_headers + dir_passed))
            failed_headers=$((failed_headers + dir_failed))
            skipped_headers=$((skipped_headers + dir_skipped))

            # Generate module-specific summary
            local module_summary_file="$OUTPUT_DIR/${dir_name}_summary.json"
            cat > "$module_summary_file" << EOF
{
    "script_version": "$SCRIPT_VERSION",
    "timestamp": "$(date -Iseconds)",
    "workspace": "$WORKSPACE",
    "module": "$dir_name",
    "directory_path": "$dir_path",
    "compiler": "$module_compiler",
    "parallel_jobs": $PARALLEL_JOBS,
    "summary": {
        "total_headers": ${#header_files[@]},
        "passed": $dir_passed,
        "failed": $dir_failed,
        "skipped": $dir_skipped,
        "success_rate": $(( ${#header_files[@]} > 0 ? (dir_passed * 100) / ${#header_files[@]} : 0 ))
    }
}
EOF

            log_info "Directory $dir_name: $dir_passed passed, $dir_failed failed, $dir_skipped skipped"
            log_info "Module summary saved: $module_summary_file"

            # Optionally present analysis for this module
            if [[ "$PRESENT_ANALYSIS" == true ]]; then
                # Analyzer expects path relative to script dir: header_check_output/<DIRECTORY>_results.json
                local rel_results_path="header_check_output/${dir_name}_results.json"
                if [[ -x "$SCRIPT_DIR/analyze_header_failures.sh" ]]; then
                    log_info "Running analyzer for module: $dir_name ($rel_results_path)"
                    (cd "$SCRIPT_DIR" && ./analyze_header_failures.sh "$rel_results_path") || \
                        log_warn "Analyzer returned non-zero for $dir_name"
                else
                    log_warn "Analyzer script not found or not executable: $SCRIPT_DIR/analyze_header_failures.sh"
                fi
            fi
        else
            log_warn "No results file generated for $dir_name, assuming all headers failed"
            failed_headers=$((failed_headers + ${#header_files[@]}))

            # Generate module-specific summary for failed case
            local module_summary_file="$OUTPUT_DIR/${dir_name}_summary.json"
            cat > "$module_summary_file" << EOF
{
    "script_version": "$SCRIPT_VERSION",
    "timestamp": "$(date -Iseconds)",
    "workspace": "$WORKSPACE",
    "module": "$dir_name",
    "directory_path": "$dir_path",
    "compiler": "$module_compiler",
    "parallel_jobs": $PARALLEL_JOBS,
    "summary": {
        "total_headers": ${#header_files[@]},
        "passed": 0,
        "failed": ${#header_files[@]},
        "skipped": 0,
        "success_rate": 0
    }
}
EOF
        fi
    done

    # Phase 3: Generate combined summary report
    log_info "Phase 3: Generating combined summary report..."

    local combined_summary_file="$OUTPUT_DIR/combined_summary.json"

    # Build module summaries array for JSON
    local module_summaries=""
    for dir_name in "${SELECTED_DIRECTORIES[@]}"; do
        local module_summary_file="$OUTPUT_DIR/${dir_name}_summary.json"
        if [[ -f "$module_summary_file" ]]; then
            if [[ -n "$module_summaries" ]]; then
                module_summaries="$module_summaries,"
            fi
            module_summaries="$module_summaries$(cat "$module_summary_file")"
        fi
    done

    cat > "$combined_summary_file" << EOF
{
    "script_version": "$SCRIPT_VERSION",
    "timestamp": "$(date -Iseconds)",
    "workspace": "$WORKSPACE",
    "directories_checked": $(printf '"%s",' "${SELECTED_DIRECTORIES[@]}" | sed 's/,$//; s/^/[/; s/$/]/'),
    "parallel_jobs": $PARALLEL_JOBS,
    "combined_summary": {
        "total_headers": $total_headers,
        "passed": $passed_headers,
        "failed": $failed_headers,
        "skipped": $skipped_headers,
        "success_rate": $(( total_headers > 0 ? (passed_headers * 100) / total_headers : 0 ))
    },
    "module_summaries": [$module_summaries]
}
EOF

    log_info "Combined summary saved: $combined_summary_file"

    # Display final summary

    # Try to get accurate statistics from combined summary file
    if command -v jq >/dev/null 2>&1 && [[ -f "$combined_summary_file" ]]; then
        local file_passed=$(jq -r '.combined_summary.passed // 0' "$combined_summary_file")
        local file_failed=$(jq -r '.combined_summary.failed // 0' "$combined_summary_file")
        local file_skipped=$(jq -r '.combined_summary.skipped // 0' "$combined_summary_file")
        local file_total=$(jq -r '.combined_summary.total_headers // 0' "$combined_summary_file")

        # Update variables if file has valid data
        if [[ $file_total -gt 0 ]]; then
            passed_headers=$file_passed
            failed_headers=$file_failed
            skipped_headers=$file_skipped
            total_headers=$file_total
        fi
    fi

    echo
    echo "=" $(printf '=%.0s' {1..80})
    echo "📊 HEADER SELF-CONTAINMENT CHECK SUMMARY"
    echo "=" $(printf '=%.0s' {1..80})
    echo "📁 Directories checked: ${#directories_to_check[@]} (${SELECTED_DIRECTORIES[*]})"
    echo "📄 Total headers found: $total_headers"
    echo "✅ Passed: $passed_headers"
    echo "❌ Failed: $failed_headers"
    echo "⚠️  Skipped: $skipped_headers"
    if [[ $total_headers -gt 0 ]]; then
        local success_rate=$(( (passed_headers * 100) / total_headers ))
        echo "📊 Success rate: $success_rate%"
    fi
    echo
    echo "📂 Results saved to: $OUTPUT_DIR"
    echo "📋 Combined summary: $combined_summary_file"
    echo "📄 Individual summaries: ${SELECTED_DIRECTORIES[@]/%/_summary.json}"

    if [[ -n "$LOG_FILE" ]]; then
        echo "📝 Detailed log: $LOG_FILE"
    fi

    # Optionally print missing header statistics
    if [[ "$REPORT_MISSING_HEADERS" == true ]]; then
        print_missing_header_stats
    fi

    log_info "Header self-containment check completed"
    echo "💡 Note: This is the main framework. Helper scripts will be created to perform actual analysis."

    # Exit with appropriate code
    if [[ $failed_headers -eq 0 ]]; then
        echo "🎉 Setup completed successfully!"
        exit 0
    else
        echo "⚠️  Some issues were found during processing"
        exit 1
    fi
}

# Helper to print end-of-run statistics for missing headers
print_missing_header_stats() {
    if ! command -v jq >/dev/null 2>&1; then
        log_warn "jq not found; cannot compute missing-headers statistics"
        return 0
    fi

    local tmp_all_outputs
    tmp_all_outputs=$(mktemp)
    local missing_fail_files=0
    local total_failed_files=0

    for dir_name in "${SELECTED_DIRECTORIES[@]}"; do
        local dir_results_file="$OUTPUT_DIR/${dir_name}_results.json"
        if [[ -f "$dir_results_file" ]]; then
            # Count total failed files in this module
            local df
            df=$(jq -r '.summary.failed // 0' "$dir_results_file" 2>/dev/null || echo 0)
            total_failed_files=$(( total_failed_files + df ))

            # Count files that failed due to missing headers (pattern-based)
            local mf
            mf=$(jq '[.results[] | select(.status=="FAILED" and (.compile_output | test("fatal error: .+: No such file or directory|[Ff]ile not found|cannot open source file"))) ] | length' "$dir_results_file" 2>/dev/null || echo 0)
            missing_fail_files=$(( missing_fail_files + mf ))

            # Collect header names from error messages for frequency analysis
            jq -r '.results[] | select(.status=="FAILED") | .compile_output' "$dir_results_file" 2>/dev/null |
            sed -n -E 's/.*fatal error: ([^:[:space:]]+): No such file or directory.*/\1/p' >> "$tmp_all_outputs"
            jq -r '.results[] | select(.status=="FAILED") | .compile_output' "$dir_results_file" 2>/dev/null |
            sed -n -E "s/.*'([^']+)' file not found.*/\1/p" >> "$tmp_all_outputs"
            jq -r '.results[] | select(.status=="FAILED") | .compile_output' "$dir_results_file" 2>/dev/null |
            sed -n -E 's/.*cannot open source file[[:space:]]+"([^"]+)".*/\1/p' >> "$tmp_all_outputs"
        fi
    done

    local distinct_missing=0
    local total_missing_occurrences=0

    if [[ -s "$tmp_all_outputs" ]]; then
        total_missing_occurrences=$(wc -l < "$tmp_all_outputs" | tr -d ' ')
        distinct_missing=$(sort "$tmp_all_outputs" | uniq | wc -l | tr -d ' ')

        echo
        echo "-" $(printf -- '-%.0s' {1..80})
        echo "FINAL STATISTICS: Missing .h includes"
        echo "-" $(printf -- '-%.0s' {1..80})
        echo "Failed files due to missing headers: $missing_fail_files (out of $total_failed_files failures)"
        echo "Distinct missing headers: $distinct_missing"
        echo "Total missing header occurrences: $total_missing_occurrences"
        echo
        echo "Top missing headers (count desc):"
        sort "$tmp_all_outputs" | uniq -c | sort -nr | awk '{printf("  %5d  %s\n", $1, $2)}'
        echo "-" $(printf -- '-%.0s' {1..80})
        echo
    else
        echo
        echo "FINAL STATISTICS: No missing-header patterns detected"
        echo
    fi

    rm -f "$tmp_all_outputs" 2>/dev/null || true
}

# Script entry point
if [[ "${BASH_SOURCE[0]:-}" == "${0}" ]]; then
    # Parse command line arguments
    parse_arguments "$@"

    # Initialize output and logging
    initialize_output "$*"

    # Run main function
    main
fi
