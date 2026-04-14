# Header Self-Containment Checker

A comprehensive script system to check if header files are self-contained (can compile standalone) by analyzing Makefiles and CMakeFiles to extract include paths and dependencies.

# Usage Example:
./repo_check_headers.sh -p 32 --report-missing-headers --present-analysis uboot

## Overview

This tool performs the following workflow:

1. **Parse Build Files**: Analyzes Makefiles (`.mak`, `.mk`) and CMake files (`CMakeLists.txt`, `*.cmake`) to extract:
   - Include paths (`-I` flags, `include_directories()`)
   - Compiler definitions (`-D` flags, `add_definitions()`)
   - Compiler flags and options
   - Target dependencies

2. **Collect Build Configuration**: Aggregates build information from multiple directories into a unified configuration

3. **Header Discovery**: Finds all header files (`.h`, `.hpp`, `.hxx`) in specified directories

4. **Self-Containment Testing**: For each header file:
   - Creates a minimal C test file that includes only that header
   - Attempts to compile it using extracted build configuration
   - Reports success/failure with detailed error information

5. **Reporting**: Generates comprehensive reports in JSON format with statistics and failure details

## Files Structure

```
repo_check_headers.sh              # Main script
scripts/
├── collect_build_config.sh        # Collects build configuration from directories
├── parse_makefiles.sh             # Advanced Makefile parser
├── parse_cmake.sh                 # Advanced CMake parser
└── check_header_self_contained.sh # Header compilation tester
```

## Requirements

- **WORKSPACE environment variable** must be set (typically via `source imc_setenv nsc`)
- `gcc` or `clang` compiler available
- Standard build tools (`make`, `cmake` if applicable)
- `jq` for JSON processing (optional but recommended)
- `bc` for calculations

## Usage

### Basic Usage

```bash
# Check userspace directory (default)
./repo_check_headers.sh

# Check specific directories
./repo_check_headers.sh atf userspace shared

# Check all available directories
./repo_check_headers.sh -a

# List available directories
./repo_check_headers.sh --list
```

### Advanced Options

```bash
# Use parallel processing
./repo_check_headers.sh -p 8 userspace

# Save detailed log
./repo_check_headers.sh -l detailed.log userspace

# Quiet mode with custom output directory
./repo_check_headers.sh -q -o /tmp/header_results userspace

# Verbose debugging
./repo_check_headers.sh -v -d atf
```

### Available Directories

The script supports these predefined directories:

- `atf` - ARM Trusted Firmware
- `boot` - Boot components
- `hifmc` - HIF Memory Controller
- `hif-shared` - HIF shared components
- `infra-common` - Common infrastructure
- `mmg-pmu` - MMG Power Management Unit
- `nsl` - Network Services Layer
- `pci` - PCI firmware
- `physs-mev` - Physical layer (MEV)
- `physs-mmg` - Physical layer (MMG)
- `shared` - Shared components
- `uboot` - U-Boot
- `userspace` - User space components

## Output

The script generates:

- **Summary JSON**: Overall statistics and results
- **Per-directory results**: Detailed results for each directory
- **Build configuration**: Extracted build settings in JSON format
- **Detailed logs**: Compilation errors and warnings (if logging enabled)

### Example Output

```
📊 HEADER SELF-CONTAINMENT CHECK SUMMARY
================================================================
📁 Directories checked: 2 (atf userspace)
📄 Total headers: 1,250
✅ Passed: 1,180
❌ Failed: 65
⚠️  Skipped: 5
📊 Success rate: 94%
```

## Makefile Parser Features

Handles complex Makefile syntax:
- Multi-line definitions with backslash continuation
- Variable substitution (`$(VAR)` and `${VAR}`)
- Include files (`include`, `-include`)
- Complex flag patterns (`CFLAGS`, `CPPFLAGS`, etc.)
- Relative path resolution

## CMake Parser Features

Supports modern CMake syntax:
- `include_directories()`
- `target_include_directories()`
- `add_definitions()`
- `target_compile_definitions()`
- `add_compile_options()`
- `find_package()` dependencies
- Multi-line commands with proper parentheses matching

## Error Handling

The script provides detailed error reporting:
- Missing header dependencies
- Compilation errors with context
- Build configuration issues
- File system problems

## Troubleshooting

### Common Issues

1. **WORKSPACE not set**:
   ```bash
   source imc_setenv nsc
   ```

2. **No headers found**:
   - Verify directory paths
   - Check if directories contain actual header files

3. **Compilation failures**:
   - Review build configuration extraction
   - Check for missing system headers
   - Verify compiler availability

4. **Performance issues**:
   - Use parallel processing: `-p N`
   - Test on smaller directory subsets first

### Debug Mode

Use debug mode for troubleshooting:
```bash
./repo_check_headers.sh -d -v directory_name
```

This provides detailed information about:
- Build file discovery
- Include path resolution
- Compilation command construction
- Error analysis

## Integration

The script can be integrated into CI/CD pipelines:

```bash
# Example CI usage
./repo_check_headers.sh -q -l ci_results.log -o /tmp/header_check userspace
if [ $? -eq 0 ]; then
    echo "All headers are self-contained ✓"
else
    echo "Header containment issues found ✗"
    cat /tmp/header_check/ci_results.log
fi
```

## Contributing

When modifying the scripts:

1. Test with `set -euo pipefail` enabled for strict error handling
2. Handle edge cases in build file parsing
3. Ensure proper cleanup of temporary files
4. Update this documentation for new features

## Version History

- **v1.0.0**: Initial implementation with Makefile/CMake parsing and parallel processing
