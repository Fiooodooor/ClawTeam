#!/bin/bash

# Build Configuration Collector - Fixed Version
# Based on working parse logic

set -euo pipefail

SCRIPT_VERSION="1.0.0"
LOG_LEVEL="${LOG_LEVEL:-INFO}"
EXCLUDE_PATTERNS=()

# Logging functions
log_info() {
    echo "ℹ️  INFO: $*" >&2
}

log_debug() {
    [[ "$LOG_LEVEL" == "DEBUG" ]] && echo "🐛 DEBUG: $*" >&2
}

log_error() {
    echo "❌ ERROR: $*" >&2
}

# Helper: fix workspace-relative absolute paths that lost the workspace prefix
fix_workspace_root() {
    local path="$1"
    local makefile_dir="$2"

    # Determine workspace root from makefile location or env
    local workspace_root="${WORKSPACE:-}"
    if [[ -z "$workspace_root" ]]; then
        if [[ "$makefile_dir" == *"/sources/imc/"* ]]; then
            workspace_root="${makefile_dir%/sources/imc/*}"
        elif [[ "$makefile_dir" == *"/sources/lan/"* ]]; then
            workspace_root="${makefile_dir%/sources/lan/*}"
        else
            workspace_root="$(cd "$makefile_dir"/../../.. 2>/dev/null && pwd || echo /)"
        fi
    fi

    # Map known anchors back into the workspace
    if [[ "$path" == /sources/* ]]; then
        echo "$workspace_root$path"
        return 0
    fi
    case "$path" in
        /nsl/*)
            echo "$workspace_root/sources/lan$path"
            return 0
            ;;
        /boot_reports_drv/*)
            echo "$workspace_root/sources/imc/infra_common$path"
            return 0
            ;;
        /lib_mmio_access/*)
            echo "$workspace_root/sources/imc/mev_infra$path"
            return 0
            ;;
        /mev_infra/*|/infra_common/*|/imc_shared/*|/userspace/*)
            echo "$workspace_root/sources/imc$path"
            ;;
    esac
    echo "$path"
}

# Define manual include directories per module name
# These are additional include directories that should be added for specific modules
# Format: space-separated list of relative paths from workspace root
declare -A MANUAL_INCLUDE_DIRS_BY_MODULE=(
    ["userspace"]="userspace/common/inc
                    userspace/mev_imc_resets_handler/mmg/src/resets
                    mev_infra/lib_osal/include
                    userspace/mev_imc_pvt/pvt_shared/include
                    userspace/mev_imc_pvt/pvt_manager/include
                    userspace/mev_imc_pvt/pvt_manager/include/mev_1
                    userspace/mev_imc_pvt/pvt_manager/include/mev_ts
                    userspace/mev_imc_mng_lib/include/
                    mev_infra/lib_ic/include/
                    mev_infra/lib_vfio/include/
                    mev_infra/lib_em/include/
                    mev_infra/lib_smc/include
                    userspace/mev_imc_dpcp_src/src/libcpf/src/CORE/
                    mev_infra/lib_xft/include/
                    userspace/mev_imc_dpcp_src/src/log/
                    userspace/mev_imc_dpcp_src/src/libdpcp/include/
                    mev_infra/lib_dev_info/include/
                    mev_infra/lib_ft/include
                    userspace/mev_imc_lm/export/
                    userspace/libs/lib_bmd/
                    userspace/mev_imc_pvt/pvt_lib/include/common
                    userspace/mev_imc_pvt/pvt_lib/src/common/include
                    userspace/mev_imc_mng_ncsi_lib/include
                    infra_common/lib_anvm/include
                    userspace/mev_imc_resets_handler/mmg/src
                    userspace/mev_imc_resets_handler/mev/inc
                    userspace/mev_imc_dpcp_src/src/libcpf/src/SHARED/virtchnl
                    userspace/common/inc/mev
                    userspace/mev_imc_resets_handler/mmg/src/drivers
                    userspace/mev_imc_resets_handler/mmg/src/drivers/acc
                    infra_common/include
                    infra_common/lib_anvm/include/common
                    userspace/mev_imc_pvt/pvt_manager/src/include
                    userspace/mev_imc_lm/inc
                    userspace/mev_imc_mng_ncsi/sources/inc
                    userspace/mev_imc_mng_ncsi/include
                    userspace/mev_imc_mng_ncsi/include/ncsi_app_config
                    userspace/mev_imc_ncsi_handler/rx_filters/inc
                    userspace/mev_imc_ncsi_handler/rx_filters/mev/inc
                    userspace/mev_imc_ncsi_handler/rx_filters/mmg/inc
                    ../lan/nsl/nsl/include
                    infra_common/boot_reports_drv/include
                    mev_infra/lib_mmio_access/include
                    userspace/apps/nvm_app/include
                    userspace/apps/nvm_app/src
                    userspace/mev_imc_mng_ncsi/sources/dphma_stub/inc
                    userspace/mev_imc_dpcp_src/src/libdpcp/src
                    userspace/mev_imc_dpcp_src/src/libdpcp/src/state_machine
                    userspace/mev_imc_dpcp_src/src/libdpcp/src/policy
                    userspace/mev_imc_dpcp_src/src/libdpcp/src/chnl
                    userspace/mev_imc_dpcp_src/src/libdpcp/src/hma
                    userspace/mev_imc_dpcp_src/src/libdpcp/src/cpchnl
                    userspace/common/inc/mmg
                    userspace/mev_imc_pvt/drivers/include
                    userspace/mev_imc_pvt/drivers/include/pa_drv
                    userspace/mev_imc_pvt/drivers/include/pvt_drv
                    userspace/mev_imc_pvt/drivers/include/io_drv
                    userspace/mev_imc_pvt/drivers/include/sensors
                    userspace/mev_imc_pvt/drivers/include/vr_drv
                    userspace/mev_imc_pvt/pvt_manager/include
                    userspace/mev_imc_mng_drv/include
                    userspace/mev_imc_mng_pt_mgmt/include
                    userspace/mev_imc_ncsi_handler/inc
                    infra_common/json_utils/include
                    infra_common/lib_mbx/include
                    userspace/mev_imc_resets_handler/mmg/src/ifs
                    userspace/libs/lib_icqh/inc
                    userspace/mev_imc_mctp_lib/inc
                    userspace/mev_imc_dpcp_src/src/cli/include
                    hif-shared/common/inc
                    hif-shared/lib_mbx/inc
                    userspace/mev_imc_dpcp_src/src/libcpmalloc/include
                    userspace/mev_imc_dpcp_src/src/libdpcp/src/fsm
                    userspace/mev_imc_mng_pt_mgmt/sources/inc
                    userspace/mev_imc_mng_pt_mgmt/sources/nl_lib/inc
                    userspace/mev_imc_mng/mng_ismp_app/include
                    userspace/mev_imc_mng/mng_ts_app/include
                    userspace/mev_imc_mng_rmii/include
                    userspace/mev_imc_mctp_hw_config/include
                    userspace/mev_imc_mctp_stack/driver/inc
                    userspace/libs/lib_infra_hi/inc
                    userspace/libs/lib_elastic_handler/inc
                    userspace/libs/lib_elastic_handler/src
                    mev_infra/lib_sw_timer/include
                    imc_shared
                    imc_shared/csr_headers
                    imc_shared/cpchnl
                    mev_hw
                    # Explicit system include roots (host + cross) to find std headers and libnl/glib dev headers FIRST
                    /usr/include
                    /usr/include/libnl3
                    /usr/local/include
                    /usr/aarch64-linux-gnu/include
                    # Zephyr libc minimal provides sys/timespec.h and sys/_timespec.h used by Zephyr POSIX
                    zephyr/lib/libc/minimal/include
                    # Zephyr POSIX headers (for eventfd.h under posix/sys and others)
                    zephyr/include/zephyr/posix
                    zephyr/include/zephyr/posix/sys
                    # Zephyr logging (to satisfy bare "log.h") and linux compat (for libconfig.h)
                    zephyr/include/zephyr/logging
                    zephyr/include/zephyr/linux_compat
                    # Zephyr generated headers (syscall list, devicetree, and syscall stubs)
                    zephyr/build_config/kernel_build_config/zephyr/include/generated
                    zephyr/build_config/kernel_build_config/zephyr/misc/generated/syscalls_links/include
                    # Zephyr POSIX arch expects a SoC-provided soc_irq.h; use native POSIX SoC + board
                    zephyr/soc/native/inf_clock
                    zephyr/boards/native/native_posix
                    # Use Zephyr include root for remaining Zephyr headers
                    zephyr/include
                    zephyr/soc/intel/intel_cnic/bts
                    ../ixd/tools/include
                    ../ixd/drivers
                    "
    ["atf"]="
                    arm-tf/include
                    arm-tf/include/common
                    arm-tf/include/arch/aarch64
                    arm-tf/include/arch/aarch32
                    # EL3 runtime context headers are included as <context.h>
                    # so the arch-specific directories themselves must be in -I
                    arm-tf/include/lib/el3_runtime
                    arm-tf/include/lib/el3_runtime/aarch64
                    arm-tf/include/lib/el3_runtime/aarch32
                    arm-tf/include/plat/common
                    arm-tf/include/plat/arm/common
                    arm-tf/include/plat/arm/common/aarch64
                    arm-tf/include/drivers
                    arm-tf/include/tools_share
                    # TBBR common headers used by many platforms
                    arm-tf/include/common/tbbr
                    # TF-A internal libc headers (provide cdefs.h, stddef_.h, limits_.h, inttypes_.h, setjmp_.h)
                    arm-tf/include/lib/libc
                    arm-tf/include/lib/libc/sys
                    arm-tf/include/lib/libc/aarch64
                    arm-tf/include/lib/libc/aarch32
                    # Intel LAN shared headers referenced by TF-A platforms (for hif_defs.h and related)
                    hif-shared/common/inc
                    # Intel FT logger (for ft_modules.h and friends)
                    arm-tf/include/drivers/intel/lan/common/ft_logger
                    hif-shared/lib_hifmcdb/inc
                    hif-shared/lib_pci_reset/inc
                    arm-tf/plat/intel
                    arm-tf/plat/intel/lan/common/include
                    arm-tf/plat/intel/lan/mev_imc/include
                    arm-tf/plat/intel/lan/mmg_imc/include
                    arm-tf/plat/intel/lan/nsc/include
                    arm-tf/plat/intel/lan/mmg_acc/include
                    arm-tf/plat/intel/soc/common/include
                    arm-tf/plat/intel/soc/stratix10/include
                    arm-tf/plat/intel/soc/agilex/include
                    arm-tf/plat/intel/soc/agilex5/include
                    arm-tf/plat/intel/soc/n5x/include
                    imc_shared/csr_headers
                    mev_hw
                    infra_common/include
                    infra_common/lib_mbx/include
                    infra_common/lib_nvm/include
                    infra_common/lib_pfuse_drv/include
                    infra_common/lib_spi_drv/include
                    infra_common/lib_flash/include
                    infra_common/lib_jedec_sfdp/include
                    imc_shared/nvm_headers
                    "
    ["hifmc"]="hif-shared/lib_hifmcdb/inc mev_hw"
    ["shared"]="mev_hw zephyr/include"
    ["infra-common"]="
                    infra_common/include
                    infra_common/json_utils/include
                    infra_common/string_utils/include
                    infra_common/xt_common/include
                    infra_common/boot_reports_drv/include
                    infra_common/lib_mbx/include
                    infra_common/lib_anvm/include
                    infra_common/lib_anvm/include/common
                    infra_common/lib_anvm/src/common
                    infra_common/lib_dmac/include
                    infra_common/lib_flash/include
                    infra_common/lib_flash_mtd/include
                    infra_common/lib_i2c_dw_drv/include
                    infra_common/lib_jedec_sfdp/include
                    infra_common/lib_nvm/include
                    infra_common/lib_nvm/src
                    infra_common/lib_pfuse_drv/include
                    infra_common/lib_spi_drv/include
                    infra_common/lib_spi_drv/src/v1
                    infra_common/lib_spi_drv/src/v2
                    infra_common/lib_tap_access/include
                    infra_common/lib_xft/include
                    hif-shared/common/inc
                    mev_hw
                    mev_infra/lib_ic/include
                    mev_infra/lib_ft/include
                    mev_infra/lib_xft/include
                    mev_infra/lib_osal/include
                    mev_infra/lib_mmio_access/include
                    "
    ["boot"]="imc_shared/csr_headers
                    imc_shared/csr_headers/mmg/imc
                    imc_shared/csr_headers/nsssip/imc
                    mev_hw
                    boot/shared/include
                    boot/BootROM/include
                    infra_common/lib_spi_drv/src/v1
                    infra_common/lib_spi_drv/src/v2"
    ["nsl"]="mev_hw imc_shared"
    ["physs-mmg"]="mev_hw imc_shared"
    ["physs-mev"]="mev_hw imc_shared"
    ["uboot"]="imc_shared/csr_headers mev_hw"
    ["hif-shared"]="
                    mev_hw
                    hif-shared/common/inc
                    hif-shared/lib_hifmcdb/inc
                    hif-shared/lib_pci_reset/inc
                    infra_common/lib_mbx/include
                    hifmc_rom/external_include/hif-shared/common/inc
                    hifmc_rom/src/lib_hifmcdb/include
                    "
    ["mmg-pmu"]="mev_hw imc_shared"
)

# Optional: manual compile definitions per module
declare -A MANUAL_DEFINES_BY_MODULE=(
    # Userspace logging selects user-mode path to avoid kernel-only linux/bitops.h
    ["userspace"]="USE_LOG_USER __ZEPHYR__ CONFIG_ARCH_POSIX CONFIG_EXTERNAL_LIBC"
)

# Global associative array for actual directory paths (populated at runtime)
declare -A MANUAL_INCLUDE_DIRS
declare -A MANUAL_COMPILE_DEFINITIONS

process_directory() {
    local dir="$1"
    local parallel_jobs="${2:-1}"
    local all_includes=()
    local all_defines=()

    log_info "Processing directory: $dir"

    # Get build files
    local build_files=($(scan_directory "$dir"))

    log_info "Found ${#build_files[@]} build files in $dir"

    if [[ ${#build_files[@]} -eq 0 ]]; then
        # No build files found - return empty result
        echo '{"include_directories":[],"compile_definitions":[]}'
        return
    fi

    # Always use parallel processing for multiple build files
    if [[ ${#build_files[@]} -gt 1 && $parallel_jobs -gt 1 ]]; then
        # Multiple files - process in parallel
        local temp_dir=$(mktemp -d)
        local job_pids=()
        local active_jobs=0

        log_debug "Processing ${#build_files[@]} build files with $parallel_jobs parallel jobs"

        # Process each build file in parallel
        for i in "${!build_files[@]}"; do
            local build_file="${build_files[$i]}"

            # Wait if we've reached max parallel jobs
            while [[ $active_jobs -ge $parallel_jobs ]]; do
                for ((j=0; j<${#job_pids[@]}; j++)); do
                    local pid="${job_pids[$j]}"
                    if [[ -n "$pid" ]] && ! kill -0 "$pid" 2>/dev/null; then
                        wait "$pid" 2>/dev/null || true
                        unset 'job_pids[$j]'
                        ((active_jobs--))
                    fi
                done
                # Compact array
                local new_pids=()
                for pid in "${job_pids[@]}"; do
                    [[ -n "$pid" ]] && new_pids+=("$pid")
                done
                job_pids=("${new_pids[@]}")

                [[ $active_jobs -ge $parallel_jobs ]] && sleep 0.001
            done

            # Start background job for this build file
            if [[ "$build_file" == *"Makefile"* || "$build_file" == *".mk" ]]; then
                (
                    local config=$(parse_makefile "$build_file")
                    echo "$config" > "$temp_dir/buildfile_$i.json"
                ) &

                job_pids+=($!)
                ((active_jobs++)) || true
            elif [[ "$build_file" == *".cmake" || "$build_file" == *"CMakeLists.txt"* ]]; then
                (
                    # Use the CMake parser for CMake files
                    local cmake_parser="$(dirname "$0")/parse_cmake.sh"
                    if [[ -f "$cmake_parser" ]]; then
                        export WORKSPACE="${WORKSPACE:-}"
                        local config=$("$cmake_parser" "$build_file" 2>/dev/null || echo '{"include_directories":[],"compile_definitions":[]}')
                        echo "$config" > "$temp_dir/buildfile_$i.json"
                    else
                        echo '{"include_directories":[],"compile_definitions":[]}' > "$temp_dir/buildfile_$i.json"
                    fi
                ) &

                job_pids+=($!)
                ((active_jobs++)) || true
            fi
        done

        # Wait for all jobs to complete (fast version)
        wait

        log_debug "All parallel jobs completed, collecting results..."

        # Merge results from all build files
        for i in "${!build_files[@]}"; do
            local result_file="$temp_dir/buildfile_$i.json"
            if [[ -f "$result_file" ]]; then
                while IFS= read -r include_dir; do
                    [[ -n "$include_dir" ]] && all_includes+=("$include_dir")
                done < <(jq -r '.include_directories[]?' "$result_file" 2>/dev/null || true)

                while IFS= read -r define; do
                    [[ -n "$define" ]] && all_defines+=("$define")
                done < <(jq -r '.compile_definitions[]?' "$result_file" 2>/dev/null || true)
            fi
        done

        # Clean up
        rm -rf "$temp_dir"
    else
        # Single file or sequential processing
        for build_file in "${build_files[@]}"; do
            if [[ "$build_file" == *"Makefile"* || "$build_file" == *".mk" ]]; then
                log_debug "Processing Makefile: $build_file"
                local config=$(parse_makefile "$build_file")

                log_debug "Config JSON length: ${#config}"
                log_debug "Config preview: ${config:0:200}..."

                # Extract includes and defines from JSON
                while IFS= read -r include_dir; do
                    [[ -n "$include_dir" ]] && all_includes+=("$include_dir")
                done < <(echo "$config" | jq -r '.include_directories[]?' 2>/dev/null || true)

                while IFS= read -r define; do
                    [[ -n "$define" ]] && all_defines+=("$define")
                done < <(echo "$config" | jq -r '.compile_definitions[]?' 2>/dev/null || true)
            elif [[ "$build_file" == *".cmake" || "$build_file" == *"CMakeLists.txt"* ]]; then
                log_debug "Processing CMake file: $build_file"
                # Use the CMake parser for CMake files
                local cmake_parser="$(dirname "$0")/parse_cmake.sh"
                if [[ -f "$cmake_parser" ]]; then
                    export WORKSPACE="${WORKSPACE:-}"
                    local config=$("$cmake_parser" "$build_file" 2>/dev/null || echo '{"include_directories":[],"compile_definitions":[]}')

                    log_debug "CMake config JSON length: ${#config}"
                    log_debug "CMake config preview: ${config:0:200}..."

                    # Extract includes and defines from JSON
                    while IFS= read -r include_dir; do
                        [[ -n "$include_dir" ]] && all_includes+=("$include_dir")
                    done < <(echo "$config" | jq -r '.include_directories[]?' 2>/dev/null || true)

                    while IFS= read -r define; do
                        [[ -n "$define" ]] && all_defines+=("$define")
                    done < <(echo "$config" | jq -r '.compile_definitions[]?' 2>/dev/null || true)
                else
                    log_debug "CMake parser not found: $cmake_parser"
                fi
            fi
        done
    fi

    # Add per-directory manual include dirs if specified
    if [[ -n "${MANUAL_INCLUDE_DIRS[$dir]:-}" ]]; then
        log_info "Adding manual include dirs for $dir: ${MANUAL_INCLUDE_DIRS[$dir]}"
        for manual_dir in ${MANUAL_INCLUDE_DIRS[$dir]}; do
            # Normalize the path
            manual_dir="${manual_dir//\/\./\/}"
            while [[ "$manual_dir" =~ /[^/]+/\.\./ ]]; do
                manual_dir=$(echo "$manual_dir" | sed 's|/[^/]*/\./\./|/|; s|/[^/]*/\.\./|/|')
            done
            if [[ -d "$manual_dir" ]] && ! should_exclude_path "$manual_dir"; then
                # Avoid Zephyr toolchain/libc include roots that overshadow system libc
                if [[ "$manual_dir" == *"/zephyr/include/arch/"* || "$manual_dir" == *"/zephyr/include/toolchain"* ]]; then
                    log_debug "Skipping toolchain/libc include root: $manual_dir"
                else
                    all_includes+=("$manual_dir")
                fi
            fi
        done
    fi

    # Add per-directory manual compile definitions if specified
    if [[ -n "${MANUAL_COMPILE_DEFINITIONS[$dir]:-}" ]]; then
        log_info "Adding manual compile definitions for $dir: ${MANUAL_COMPILE_DEFINITIONS[$dir]}"
        for def in ${MANUAL_COMPILE_DEFINITIONS[$dir]}; do
            all_defines+=("$def")
        done
    fi

    # Note: Do NOT auto-inject Zephyr include directories for userspace here.
    # They can overshadow system headers (e.g., assert.h), causing toolchain conflicts.

    # Remove duplicates while preserving order (do not sort to keep include precedence)
    local unique_includes=()
    declare -A _seen_inc=()
    for inc in "${all_includes[@]}"; do
        [[ -z "$inc" ]] && continue
        # Drop stray root-like include entries
        if [[ "$inc" == "/" || "$inc" == "/include" || "$inc" == "include" ]]; then
            continue
        fi
        if [[ -z "${_seen_inc[$inc]:-}" ]]; then
            unique_includes+=("$inc")
            _seen_inc[$inc]=1
        fi
    done

    local unique_defines=()
    declare -A _seen_def=()
    for def in "${all_defines[@]}"; do
        [[ -z "$def" ]] && continue
        if [[ -z "${_seen_def[$def]:-}" ]]; then
            unique_defines+=("$def")
            _seen_def[$def]=1
        fi
    done

    log_debug "Directory $dir: ${#unique_includes[@]} unique includes, ${#unique_defines[@]} unique defines"

    # Output final JSON
    echo "{"
    echo "  \"include_directories\": ["
    for i in "${!unique_includes[@]}"; do
        echo -n "    \"${unique_includes[$i]}\""
        [[ $i -lt $((${#unique_includes[@]} - 1)) ]] && echo ","
    done
    echo ""
    echo "  ],"
    echo "  \"compile_definitions\": ["
    for i in "${!unique_defines[@]}"; do
        echo -n "    \"${unique_defines[$i]}\""
        [[ $i -lt $((${#unique_defines[@]} - 1)) ]] && echo ","
    done
    echo ""
    echo "  ]"
    echo "}"
}

# ARM-TF variable expansion function
expand_atf_variables() {
    local path="$1"
    local makefile_dir="$2"  # Pass makefile directory for context

    # ARM-TF defaults from make_helpers/defaults.mk
    # Handle both ${ARCH} and $(ARCH) syntax
    path="${path//\$\{ARCH\}/aarch64}"
    path="${path//\$(ARCH)/aarch64}"
    path="${path//\$\{ARM_ARCH_MAJOR\}/8}"
    path="${path//\$(ARM_ARCH_MAJOR)/8}"
    path="${path//\$\{ARM_ARCH_MINOR\}/0}"
    path="${path//\$(ARM_ARCH_MINOR)/0}"
    path="${path//\$\{VERSION_MAJOR\}/2}"
    path="${path//\$(VERSION_MAJOR)/2}"
    path="${path//\$\{VERSION_MINOR\}/10}"
    path="${path//\$(VERSION_MINOR)/10}"
    path="${path//\$\{VERSION_PATCH\}/0}"
    path="${path//\$(VERSION_PATCH)/0}"

    # Common ATF platform variables (expand to empty or common defaults)
    path="${path//\$\{PLAT\}/}"
    path="${path//\$(PLAT)/}"
    path="${path//\$\{TARGET_BOARD\}/}"
    path="${path//\$(TARGET_BOARD)/}"
    path="${path//\$\{AW_PLAT\}/}"
    path="${path//\$(AW_PLAT)/}"

    # Intel-specific ATF variables - resolve relative to workspace structure
    # Find the workspace root relative to the makefile
    local workspace_root=""
    if [[ "$makefile_dir" == *"/arm-tf/"* ]]; then
        # Extract path before /arm-tf/
        workspace_root="${makefile_dir%/arm-tf/*}"
        local sources_root="$workspace_root"

        # Intel workspace variables
        path="${path//\$\{IMC_SHARED_DIR\}/$sources_root/imc_shared}"
        path="${path//\$(IMC_SHARED_DIR)/$sources_root/imc_shared}"
        path="${path//\$\{NSS_HW_PATH\}/$sources_root/mev_hw}"
        path="${path//\$(NSS_HW_PATH)/$sources_root/mev_hw}"
        path="${path//\$\{IMC_INFRA_COMMON_LINUX_DIR\}/$sources_root/infra_common}"
        path="${path//\$(IMC_INFRA_COMMON_LINUX_DIR)/$sources_root/infra_common}"
    fi

    # Remove other complex variables that have no reasonable defaults
    path="${path//\$\{MEV_NVM_LIB_INCLUDE\}/}"
    path="${path//\$(MEV_NVM_LIB_INCLUDE)/}"
    path="${path//\$\{MEV_IMC_CMN_INCLUDE\}/}"
    path="${path//\$(MEV_IMC_CMN_INCLUDE)/}"
    path="${path//\$\{MEV_IMC_IPC_INCLUDE\}/}"
    path="${path//\$(MEV_IMC_IPC_INCLUDE)/}"
    path="${path//\$\{BOOT_REPORTS_DRV_INCLUDE\}/}"
    path="${path//\$(BOOT_REPORTS_DRV_INCLUDE)/}"
    path="${path//\$\{LIB_SECURITY_INCLUDE\}/}"
    path="${path//\$(LIB_SECURITY_INCLUDE)/}"
    path="${path//\$\{SBB_DRV_INCLUDE\}/}"
    path="${path//\$(SBB_DRV_INCLUDE)/}"
    path="${path//\$\{MEV_UTILS_LIB_INCLUDE\}/}"
    path="${path//\$(MEV_UTILS_LIB_INCLUDE)/}"
    path="${path//\$\{LIB_PFUSE_DRV_INCLUDE\}/}"
    path="${path//\$(LIB_PFUSE_DRV_INCLUDE)/}"
    path="${path//\$\{MMG_I2C_DW_DRV_LIB_INC\}/}"
    path="${path//\$(MMG_I2C_DW_DRV_LIB_INC)/}"
    path="${path//\$\{PLAT_INCLUDE\}/}"
    path="${path//\$(PLAT_INCLUDE)/}"
    path="${path//\$\{OPENSSL_DIR\}/}"
    path="${path//\$(OPENSSL_DIR)/}"

    # Final cleanup - remove any remaining variable patterns to prevent malformed paths
    path=$(echo "$path" | sed 's/\$([^)]*)//g')  # Remove $(VAR) patterns
    path=$(echo "$path" | sed 's/\${[^}]*}//g')  # Remove ${VAR} patterns

    echo "$path"
}

# Function to expand userspace makefile variables to actual paths
expand_userspace_variables() {
    local path="$1"
    local makefile_dir="$2"  # Pass makefile directory for context

    # Find the workspace root relative to the makefile
    local workspace_root=""
    if [[ "$makefile_dir" == *"/userspace/"* ]]; then
        # Extract path before /userspace/
        workspace_root="${makefile_dir%/userspace/*}"
        local userspace_root="${workspace_root}/userspace"
        local sources_root="$workspace_root"

        # Core userspace path variables from module_paths.mak (exact mappings)
        path="${path//\$\{USERSPACE_ROOT\}/$userspace_root}"
        path="${path//\$(USERSPACE_ROOT)/$userspace_root}"
        path="${path//\$\{SHARED_PATH\}/$userspace_root/..}"
        path="${path//\$(SHARED_PATH)/$userspace_root/..}"
        path="${path//\$\{IMC_SHARED_PATH\}/$userspace_root/../imc_shared}"
        path="${path//\$(IMC_SHARED_PATH)/$userspace_root/../imc_shared}"
        path="${path//\$\{NSS_HW_PATH\}/$userspace_root/../mev_hw}"
        path="${path//\$(NSS_HW_PATH)/$userspace_root/../mev_hw}"

        # Remove other complex variables
        path=$(echo "$path" | sed 's/\$([^)]*)//g')  # Remove $(VAR) patterns
        path=$(echo "$path" | sed 's/\${[^}]*}//g')  # Remove ${VAR} patterns
    fi

    echo "$path"
}

# Enhanced parse_makefile function with multi-line variable support
parse_makefile() {
    local makefile="$1"
    local includes=()
    local defines=()

    # Check if this is an ARM-TF Makefile
    local is_atf_makefile=false
    [[ "$makefile" == *"arm-tf"* ]] && is_atf_makefile=true

    local makefile_dir="$(dirname "$makefile")"

    # Read the entire makefile and handle line continuations
    local makefile_content=""
    local current_line=""
    local in_continuation=false

    while IFS= read -r line || [[ -n "$line" ]]; do
        # Skip comments
        [[ "$line" =~ ^[[:space:]]*# ]] && continue
        [[ -z "$line" ]] && continue

        # Handle line continuations
        if [[ "$line" =~ \\[[:space:]]*$ ]]; then
            # Line continues - remove trailing backslash and whitespace
            current_line+="${line%\\*}"
            in_continuation=true
            continue
        else
            # Line ends
            if [[ "$in_continuation" == true ]]; then
                current_line+="$line"
                in_continuation=false
            else
                current_line="$line"
            fi

            # Process the complete line
            makefile_content+="$current_line"$'\n'
            current_line=""
        fi
    done < "$makefile"

    # Add any remaining line
    [[ -n "$current_line" ]] && makefile_content+="$current_line"$'\n'    # Process the content line by line
    while IFS= read -r line; do
        [[ -z "$line" ]] && continue

        # Handle include statements (e.g., include $(VAR)/file.mak)
        if [[ "$line" =~ ^[[:space:]]*include[[:space:]]+([^[:space:]]+.*) ]]; then
            local include_path="${BASH_REMATCH[1]}"

            # Expand variables in the include path
            if [[ "$is_atf_makefile" == true ]]; then
                include_path=$(expand_atf_variables "$include_path" "$makefile_dir")
            elif [[ "$makefile_dir" == *"/userspace/"* ]]; then
                include_path=$(expand_userspace_variables "$include_path" "$makefile_dir")
            fi

            # Resolve relative paths
            if [[ "$include_path" != /* ]]; then
                include_path="$makefile_dir/$include_path"
            fi

            # Normalize path
            include_path="${include_path//\/\./\/}"  # Remove /./
            while [[ "$include_path" =~ /[^/]+/\.\./ ]]; do
                include_path=$(echo "$include_path" | sed 's|/[^/]*/\./\./|/|')
            done

            # Recursively parse the included file if it exists
            if [[ -f "$include_path" ]]; then
                local included_config=$(parse_makefile "$include_path")
                local included_includes=($(echo "$included_config" | jq -r '.include_directories[]?' 2>/dev/null || true))
                local included_defines=($(echo "$included_config" | jq -r '.compile_definitions[]?' 2>/dev/null || true))
                includes+=("${included_includes[@]}")
                defines+=("${included_defines[@]}")
            fi
        fi

        # Handle INCLUDES and INCLUDE_DIRS variable assignments (e.g., INCLUDES += -Ipath, INCLUDE_DIRS += path)
        if [[ "$line" =~ ^[[:space:]]*INCLUDE(_DIRS|S)?[[:space:]]*[:+]?=[[:space:]]*(.*) ]]; then
            local includes_content="${BASH_REMATCH[2]}"
            local var_name="${BASH_REMATCH[1]}"

            # For INCLUDE_DIRS, handle plain paths (no -I prefix)
            if [[ "$var_name" == "_DIRS" ]]; then
                # Split by whitespace and process each path
                local temp_includes="$includes_content"
                for include_path in $temp_includes; do
                    # Skip empty entries
                    [[ -z "$include_path" ]] && continue

                    # For userspace Makefiles, expand variables
                    if [[ "$makefile_dir" == *"/userspace/"* ]]; then
                        include_path=$(expand_userspace_variables "$include_path" "$makefile_dir")
                    fi

                    # Resolve relative paths
                    if [[ "$include_path" != /* ]]; then
                        # For other makefiles, paths are relative to makefile directory
                        include_path="$makefile_dir/$include_path"
                    fi

                    # Normalize path: collapse '/./' segments
                    include_path="${include_path//\/\.\//\/}"
                    while [[ "$include_path" =~ /[^/]+/\.\./ ]]; do
                        # Fix the regex - need to use proper substitution syntax
                        include_path=$(echo "$include_path" | sed 's|/[^/]*/\./\./|/|; s|/[^/]*/\.\./|/|')
                    done

                    # Fix lost workspace root if needed
                    include_path=$(fix_workspace_root "$include_path" "$makefile_dir")

                    # Only add if not excluded
                    if ! should_exclude_path "$include_path"; then
                        includes+=("$include_path")
                    fi
                done
            else
                # For INCLUDES, extract -I flags from INCLUDES variable
                local temp_includes="$includes_content"
                while [[ "$temp_includes" =~ -I[[:space:]]*([^[:space:]]+)(.*) ]]; do
                    local include_path="${BASH_REMATCH[1]}"
                    local remaining="${BASH_REMATCH[2]}"

                    # Skip if it looks like a malformed path
                    [[ "$include_path" =~ dentifier: ]] && { temp_includes="$remaining"; continue; }

                    # For ARM-TF Makefiles, expand variables
                    if [[ "$is_atf_makefile" == true ]]; then
                        include_path=$(expand_atf_variables "$include_path" "$makefile_dir")
                    # For userspace Makefiles, expand variables
                    elif [[ "$makefile_dir" == *"/userspace/"* ]]; then
                        include_path=$(expand_userspace_variables "$include_path" "$makefile_dir")
                    fi

                    # Resolve relative paths
                    if [[ "$include_path" != /* ]]; then
                        if [[ "$is_atf_makefile" == true ]]; then
                            # For ATF makefiles, paths are relative to the ATF root directory
                            local atf_root=""
                            if [[ "$makefile_dir" == *"/arm-tf/"* ]]; then
                                atf_root="${makefile_dir%%/arm-tf/*}/arm-tf"
                            else
                                atf_root="$makefile_dir"
                            fi
                            include_path="$atf_root/$include_path"
                        else
                            # For other makefiles, paths are relative to makefile directory
                            include_path="$makefile_dir/$include_path"
                        fi
                    fi

                    # Normalize path: collapse '/./' segments
                    include_path="${include_path//\/\.\//\/}"
                    while [[ "$include_path" =~ /[^/]+/\.\./ ]]; do
                        include_path=$(echo "$include_path" | sed 's|/[^/]*/\./\./|/|; s|/[^/]*/\.\./|/|')
                    done

                    # Fix lost workspace root if needed
                    include_path=$(fix_workspace_root "$include_path" "$makefile_dir")

                    # Only add if not excluded
                    if ! should_exclude_path "$include_path"; then
                        includes+=("$include_path")
                    fi
                    temp_includes="$remaining"
                done
            fi
        fi

        # Extract -I flags from the line (existing logic)
        local temp_line="$line"
        while [[ "$temp_line" =~ -I[[:space:]]*([^[:space:]]+)(.*) ]]; do
            local include_path="${BASH_REMATCH[1]}"
            local remaining="${BASH_REMATCH[2]}"

            # Skip if it looks like a malformed path
            [[ "$include_path" =~ dentifier: ]] && { temp_line="$remaining"; continue; }

            # For ARM-TF Makefiles, expand variables
            if [[ "$is_atf_makefile" == true ]]; then
                include_path=$(expand_atf_variables "$include_path" "$makefile_dir")
            # For userspace Makefiles, expand variables
            elif [[ "$makefile_dir" == *"/userspace/"* ]]; then
                include_path=$(expand_userspace_variables "$include_path" "$makefile_dir")
            fi

            # Resolve relative paths
            if [[ "$include_path" != /* ]]; then
                if [[ "$is_atf_makefile" == true ]]; then
                    # For ATF makefiles, paths are relative to the ATF root directory
                    local atf_root=""
                    if [[ "$makefile_dir" == *"/arm-tf/"* ]]; then
                        atf_root="${makefile_dir%%/arm-tf/*}/arm-tf"
                    else
                        atf_root="$makefile_dir"
                    fi
                    include_path="$atf_root/$include_path"
                else
                    # For other makefiles, paths are relative to makefile directory
                    include_path="$makefile_dir/$include_path"
                fi
            fi

            # Normalize path: collapse '/./' segments
            include_path="${include_path//\/\.\//\/}"
            while [[ "$include_path" =~ /[^/]+/\.\./ ]]; do
                include_path=$(echo "$include_path" | sed 's|/[^/]*/\./\./|/|; s|/[^/]*/\.\./|/|')
            done

            # Fix lost workspace root if needed
            include_path=$(fix_workspace_root "$include_path" "$makefile_dir")

            # Only add if not excluded
            if ! should_exclude_path "$include_path"; then
                includes+=("$include_path")
            fi
            temp_line="$remaining"
        done

        # Extract defines from the line
        local temp_line_defines="$line"
        while [[ "$temp_line_defines" =~ -D[[:space:]]*([^[:space:]]+)(.*) ]]; do
            defines+=("${BASH_REMATCH[1]}")
            temp_line_defines="${BASH_REMATCH[2]}"
        done
    done <<< "$makefile_content"

    # Fast JSON generation (no debug logging to avoid overhead)
    printf '{"file":"%s","type":"makefile","include_directories":[' "$makefile"
    for i in "${!includes[@]}"; do
        printf '"%s"' "${includes[$i]//\"/\\\"}"
        [[ $i -lt $((${#includes[@]} - 1)) ]] && printf ','
    done
    printf '],"compile_definitions":['
    local simple_defines=()
    for define in "${defines[@]}"; do
        [[ "$define" =~ ^[A-Za-z0-9_=]+$ ]] && simple_defines+=("$define")
    done
    for i in "${!simple_defines[@]}"; do
        printf '"%s"' "${simple_defines[$i]}"
        [[ $i -lt $((${#simple_defines[@]} - 1)) ]] && printf ','
    done
    printf '],"cflags":[]}\n'
}

# Simple function to scan for build files
scan_directory() {
    local dir="$1"
    local build_files=()

    log_debug "Scanning directory: $dir"

    # Find Makefiles, platform.mk, *.mk, *.src, and CMake files
    mapfile -t makefiles < <(find "$dir" -name "Makefile" -o -name "Makefile.*" -o -name "platform.mk" -o -name "*.mk" -type f 2>/dev/null | head -400)
    mapfile -t cmakefiles < <(find "$dir" -name "*.cmake" -o -name "CMakeLists.txt" -type f 2>/dev/null | head -100)

    build_files=("${makefiles[@]}" "${cmakefiles[@]}")

    echo "${build_files[@]}"
}

# Function to check if a path should be excluded
should_exclude_path() {
    local path="$1"

    [[ "$LOG_LEVEL" == "DEBUG" ]] && log_debug "Checking exclude for path: $path"

    # Check against external exclude patterns
    for pattern in "${EXCLUDE_PATTERNS[@]}"; do
        [[ "$LOG_LEVEL" == "DEBUG" ]] && log_debug "  Testing against pattern: $pattern"
        if check_pattern_match "$path" "$pattern"; then
            [[ "$LOG_LEVEL" == "DEBUG" ]] && log_debug "  ✅ EXCLUDED by pattern: $pattern"
            return 0  # Should exclude
        fi
    done

    [[ "$LOG_LEVEL" == "DEBUG" ]] && log_debug "  ✅ NOT EXCLUDED"
    return 1  # Should not exclude
}

# Function to check if a path matches a pattern (supports glob, regex, and exceptions)
check_pattern_match() {
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
        # Support glob patterns with extglob
        shopt -s extglob nullglob
        if [[ "$path" == $pattern ]]; then
            [[ "$LOG_LEVEL" == "DEBUG" ]] && log_debug "    ✅ Glob match"
            return 0  # Match
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

# Main function
main() {
    local output_file=""
    local directories=()
    local parallel_jobs=1
    local log_level="INFO"
    local module_name=""

    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --output)
                output_file="$2"
                shift 2
                ;;
            --parallel)
                parallel_jobs="$2"
                shift 2
                ;;
            --exclude)
                EXCLUDE_PATTERNS+=("$2")
                shift 2
                ;;
            # Map TF-A extracted hif-shared partial paths back into workspace
            /lib_pci_reset/*)
                echo "$workspace_root/sources/imc/hif-shared$path"
                return 0
                ;;
            /lib_hifmcdb/*)
                echo "$workspace_root/sources/imc/hif-shared$path"
                return 0
                ;;
        /common/inc)
                echo "$workspace_root/sources/imc/hif-shared/common/inc"
                return 0
                ;;
            --exclude-file)
                if [[ -f "$2" ]]; then
                    while IFS= read -r pattern; do
                        [[ -n "$pattern" && ! "$pattern" =~ ^[[:space:]]*# ]] && EXCLUDE_PATTERNS+=("$pattern")
                    done < "$2"
                else
                    log_error "Exclude file not found: $2"
                    exit 1
                fi
                shift 2
                ;;
            --module)
                module_name="$2"
                shift 2
                ;;
            --manual-include)
                # Legacy support: --manual-include "dir_path:include1:include2:include3"
                local manual_spec="$2"
                if [[ "$manual_spec" == *":"* ]]; then
                    local dir_path="${manual_spec%%:*}"
                    local include_dirs="${manual_spec#*:}"
                    include_dirs="${include_dirs//:/\ }"  # Replace : with spaces
                    MANUAL_INCLUDE_DIRS["$dir_path"]="$include_dirs"
                    log_info "Added manual include dirs for $dir_path: $include_dirs"
                else
                    log_error "Invalid manual include format. Use: --manual-include 'dir_path:include1:include2'"
                    exit 1
                fi
                shift 2
                ;;
            --log-level)
                log_level="$2"
                LOG_LEVEL="$2"
                shift 2
                ;;
            -*)
                log_debug "Ignoring unknown option: $1"
                shift
                ;;
            *)
                directories+=("$1")
                shift
                ;;
        esac
    done

    # If module name is provided, set up manual include directories
    if [[ -n "$module_name" ]]; then
        log_info "Processing module: $module_name"

        # Get workspace root from first directory argument
        if [[ ${#directories[@]} -gt 0 ]]; then
            local dir_path="${directories[0]}"
            local workspace_root=""

            # Try to find workspace root by looking for common patterns
            if [[ "$dir_path" == *"/sources/imc/"* ]]; then
                workspace_root="${dir_path%/sources/imc/*}"
            elif [[ "$dir_path" == *"/sources/lan/"* ]]; then
                workspace_root="${dir_path%/sources/lan/*}"
            elif [[ "$dir_path" == *"/sources/"* ]]; then
                workspace_root="${dir_path%/sources/*}"
            else
                # Fallback: assume workspace is 3 levels up from the directory
                workspace_root="$(dirname "$(dirname "$(dirname "$dir_path")")")"
            fi

            log_debug "Detected workspace root: $workspace_root"

            # Get manual include dirs for this module
            local manual_include_paths="${MANUAL_INCLUDE_DIRS_BY_MODULE[$module_name]:-}"
            if [[ -n "$manual_include_paths" ]]; then
                local resolved_paths=""
                for rel_path in $manual_include_paths; do
                    local abs_path=""
                    if [[ "$rel_path" = /* ]]; then
                        abs_path="$rel_path"
                    else
                        abs_path="$workspace_root/sources/imc/$rel_path"
                    fi
                    resolved_paths+="$abs_path "
                done
                resolved_paths="${resolved_paths% }"  # Remove trailing space
                MANUAL_INCLUDE_DIRS["$dir_path"]="$resolved_paths"
                log_info "Added manual include dirs for module $module_name: $resolved_paths"
            fi

            # Get manual compile definitions for this module
            local manual_defines="${MANUAL_DEFINES_BY_MODULE[$module_name]:-}"
            if [[ -n "$manual_defines" ]]; then
                MANUAL_COMPILE_DEFINITIONS["$dir_path"]="$manual_defines"
                log_info "Added manual compile definitions for module $module_name: $manual_defines"
            fi
        fi
    fi

    # Check required arguments
    if [[ ${#directories[@]} -eq 0 ]]; then
        log_error "Usage: $0 --output <file> <directory>..."
        exit 1
    fi

    if [[ -z "$output_file" ]]; then
        log_error "Output file required (--output)"
        exit 1
    fi

    log_info "Build Configuration Collector v$SCRIPT_VERSION"
    log_info "Processing ${#directories[@]} directories with $parallel_jobs parallel jobs"
    log_info "Log level: $log_level"
    log_info "Output file: $output_file"

    # Process directories in parallel if more than one
    local all_includes=()
    local all_defines=()

    if [[ ${#directories[@]} -eq 1 ]]; then
        # Single directory - process with parallel build file processing
        local result=$(process_directory "${directories[0]}" "$parallel_jobs")
        echo "$result" > "$output_file"
    else
        # Multiple directories - process in parallel
        local temp_dir=$(mktemp -d)
        local job_pids=()
        local active_jobs=0

        # Process each directory in parallel
        for i in "${!directories[@]}"; do
            local dir="${directories[$i]}"

            # Wait if we've reached max parallel jobs
            while [[ $active_jobs -ge $parallel_jobs ]]; do
                for ((j=0; j<${#job_pids[@]}; j++)); do
                    local pid="${job_pids[$j]}"
                    if [[ -n "$pid" ]] && ! kill -0 "$pid" 2>/dev/null; then
                        wait "$pid" 2>/dev/null || true
                        unset 'job_pids[$j]'
                        ((active_jobs--))
                    fi
                done
                # Compact array
                local new_pids=()
                for pid in "${job_pids[@]}"; do
                    [[ -n "$pid" ]] && new_pids+=("$pid")
                done
                job_pids=("${new_pids[@]}")

                [[ $active_jobs -ge $parallel_jobs ]] && sleep 0.001
            done

            # Start background job
            (
                local result=$(process_directory "$dir" "$parallel_jobs")
                echo "$result" > "$temp_dir/result_$i.json"
            ) &

            job_pids+=($!)
            ((active_jobs++)) || true
            log_debug "Started job for directory $((i+1))/${#directories[@]}: $dir"
        done

        # Wait for all jobs to complete
        for pid in "${job_pids[@]}"; do
            [[ -n "$pid" ]] && wait "$pid" 2>/dev/null || true
        done

        # Merge results from all directories
        for i in "${!directories[@]}"; do
            local result_file="$temp_dir/result_$i.json"
            if [[ -f "$result_file" ]]; then
                local includes=($(jq -r '.include_directories[]?' "$result_file" 2>/dev/null || true))
                local defines=($(jq -r '.compile_definitions[]?' "$result_file" 2>/dev/null || true))
                all_includes+=("${includes[@]}")
                all_defines+=("${defines[@]}")
            fi
        done

        # Remove duplicates and create final result
        local unique_includes=($(printf '%s\n' "${all_includes[@]}" | sort -u))
        local unique_defines=($(printf '%s\n' "${all_defines[@]}" | sort -u))

        # Generate final JSON
        local final_result="{"
        final_result+='"include_directories":['
        for i in "${!unique_includes[@]}"; do
            final_result+="\"${unique_includes[$i]}\""
            [[ $i -lt $((${#unique_includes[@]} - 1)) ]] && final_result+=","
        done
        final_result+='],"compile_definitions":['
        for i in "${!unique_defines[@]}"; do
            final_result+="\"${unique_defines[$i]}\""
            [[ $i -lt $((${#unique_defines[@]} - 1)) ]] && final_result+=","
        done
        final_result+=']}'

        echo "$final_result" > "$output_file"
        rm -rf "$temp_dir"
    fi

    # Extract final counts for reporting
    local include_count=$(jq '.include_directories | length' "$output_file" 2>/dev/null || echo "0")
    local define_count=$(jq '.compile_definitions | length' "$output_file" 2>/dev/null || echo "0")

    log_info "Final result: $include_count include directories, $define_count compile definitions"
    log_info "Build configuration saved to: $output_file"
}

# Run main function if script is executed directly
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
