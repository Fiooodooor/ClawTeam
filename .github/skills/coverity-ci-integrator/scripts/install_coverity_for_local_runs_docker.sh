#!/bin/bash
#===================================================================
# Copyright(c) 2023 Intel Corporation
#
# For licensing information, see the file 'LICENSE' in the root folder
# ====================================================================

# Prompt for password securely
read -s -p "Enter Intel user name: " USER_NAME
echo

# Prompt for password securely
read -s -p "Enter your password: " PASSWORD
echo

# Define vars of local coverity paths
COVERITY_LOCAL_DIR=/opt/coverity/analysis
COVERITY_XTENSA_CONFIG_FILE=~/.coverity/xtensa-coverity.xml

# Setup coverity config for Xtensa
cov-configure --template --config $COVERITY_XTENSA_CONFIG_FILE --compiler xt-clang --comptype xtclang
cov-configure --template --config $COVERITY_XTENSA_CONFIG_FILE --compiler aarch64-intel-linux-gcc --comptype gcc
cov-configure --template --config $COVERITY_XTENSA_CONFIG_FILE --compiler aarch64-intel-linux-cpp --comptype g++

# Define the content of the coverity.conf file
GENERAL_CONF_CONTENT='{
	"format_version": 1,
	"settings": {
		"server": {
			"url": "https://coverity.devtools.intel.com/prod8",
			"auth_key_file": "$(cov_user_dir)/authkeys/ak-coverityent.devtools.intel.com-443"
		},
		"scm": {
			"scm": "git"
		},
		"known_installations": [
			{
				"platform": "linux64",
				"directory": "'"$COVERITY_LOCAL_DIR"'",
				"kind": "cov-analysis",
				"version": "2022.12.2"
			}
		],
		"cov_run_desktop": {
			"reference_snapshot": "latest"
		},
		"compiler_config_file": "'"$COVERITY_XTENSA_CONFIG_FILE"'"
	},
	"type": "Coverity configuration",
	"format_minor_version": 7
}'

# Create the coverity.conf file
echo "$GENERAL_CONF_CONTENT" > ~/.coverity/coverity.conf

# Setup cov-run-desktop
echo "Configuring cov-run-desktop authentication key file"
cov-run-desktop --create-auth-key --user $USER_NAME --password $PASSWORD --stream ATF_MMG # can be any valid stream

echo "Installation and setup are completed, cd to your repo and run:"
echo "1. \`cov-run-desktop --build\`"
echo "2. \`cov-run-desktop <file path to analyze>\`"

