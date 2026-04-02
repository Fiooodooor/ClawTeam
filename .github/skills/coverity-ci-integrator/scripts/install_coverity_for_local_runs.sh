#!/bin/bash
#===================================================================
# Copyright(c) 2023 Intel Corporation
#
# For licensing information, see the file 'LICENSE' in the root folder
# ====================================================================

# Check if the script is sourced
if [ -n "$BASH_SOURCE" ]; then
    THIS_SCRIPT=$BASH_SOURCE
elif [ -n "$ZSH_NAME" ]; then
    THIS_SCRIPT=$0
fi

if [ -z "$ZSH_NAME" ] && [ "$0" = "$THIS_SCRIPT" ]; then
    echo "Error: This script needs to be sourced. Please run as '. $THIS_SCRIPT'"
    exit 1
fi

PWD=`pwd`
echo $PWD
# Define vars of remote server paths
COVERITY_DIR_PATH="https://ubit-artifactory-or.intel.com/artifactory/coverity-or-local/Archive"
COVERITY_VERSION="2022.12.2"
COVERITY_LICENSE_VERSION="2022.3.1"
COVERITY_PLATFORM=linux64
COVERITY_KIND=cov-analysis
COVERITY_DIR_NAME="$COVERITY_KIND-$COVERITY_PLATFORM-$COVERITY_VERSION"
COVERITY_SCRIPT_NAME="$COVERITY_DIR_NAME.sh"
COVERITY_SCRIPT_ARGS="-q --license.region=0 --license.agreement=agree  --license.cov.path=$PWD"
COVERITY_LICENSE_NAME="license.dat"
COVERITY_INSTALL_BASE_PATH="$COVERITY_DIR_PATH/$COVERITY_VERSION"
COVERITY_LICENSE_BASE_PATH="$COVERITY_DIR_PATH/$COVERITY_LICENSE_VERSION"
COVERITY_INSTALL_FILE_PATH="$COVERITY_INSTALL_BASE_PATH/$COVERITY_SCRIPT_NAME"
COVERITY_INSTALL_LICENSE_PATH="$COVERITY_LICENSE_BASE_PATH/$COVERITY_LICENSE_NAME"
# Extract the username of the user running the script
USER_NAME=$(whoami)
# Define vars of local coverity paths
COVERITY_LOCAL_DIR=/home/$USER_NAME/$COVERITY_DIR_NAME
COVERITY_LOCAL_BIN=$COVERITY_LOCAL_DIR/bin
COVERITY_CONFIG_FILE=/home/$USER_NAME/.coverity/mmg-coverity-config.xml

# Prompt for password securely
read -s -p "Enter your password: " PASSWORD
echo

# Download the license using wget
if [ ! -f "$COVERITY_LICENSE_NAME" ]; then
	wget --user="$USER_NAME" --password="$PASSWORD" --progress=bar:force "$COVERITY_INSTALL_LICENSE_PATH"
fi
# Download the script using wget
if [ ! -f "$COVERITY_SCRIPT_NAME" ]; then
	wget --user="$USER_NAME" --password="$PASSWORD" --progress=bar:force "$COVERITY_INSTALL_FILE_PATH"
fi


# Set execute permissions for the downloaded script
chmod +x ./$COVERITY_SCRIPT_NAME

# Executing $COVERITY_SCRIPT_NAME script
./$COVERITY_SCRIPT_NAME $COVERITY_SCRIPT_ARGS

# Copy license to bin dir
cp $COVERITY_LICENSE_NAME $COVERITY_LOCAL_BIN

# Deleting Coveritiy install script
# rm ./$COVERITY_SCRIPT_NAME

# Define the content of the coverity.conf file

GENERAL_CONF_CONTENT='{
	"format_version": 1,
	"settings": {
		"server": {
			"url": "https://coverity.devtools.intel.com/prod8",
			"auth_key_file": "/home/'"$USER_NAME"'/.coverity/authkeys/ak-coverityent.devtools.intel.com-443"
		},
		"scm": {
			"scm": "git"
		},
		"known_installations": [
			{
				"platform": "'"$COVERITY_PLATFORM"'",
				"directory": "'"$COVERITY_LOCAL_DIR"'",
				"kind": "'"$COVERITY_KIND"'",
				"version": "'"$COVERITY_VERSION"'"
			}
		],
		"cov_run_desktop": {
			"reference_snapshot": "latest"
		},
		"compiler_config_file": "'"$COVERITY_CONFIG_FILE"'"
	},
	"type": "Coverity configuration",
	"format_minor_version": 7
}'

# Create the coverity.conf file
echo "$GENERAL_CONF_CONTENT" > /home/$USER_NAME/.coverity/coverity.conf

# Set no proxy for coverity server.
echo "Setup no_proxy for coverity server"
echo "export no_proxy=\$no_proxy,coverity-precloud.devtools.intel.com"
export no_proxy=$no_proxy,coverity-precloud.devtools.intel.com

# Setup PATH to have coverity bin dir
echo "Add Coverity bin dir to PATH"
echo "export PATH=\$PATH:/home/\$USER_NAME/\$COVERITY_DIR_NAME/bin/"
export PATH=$PATH:/home/$USER_NAME/$COVERITY_DIR_NAME/bin/

# Setup cov-run-desktop
echo "Configuring compilers"
cov-configure --template --config $COVERITY_CONFIG_FILE --compiler arm --comptype armcc
cov-configure --template --config $COVERITY_CONFIG_FILE --compiler aarch64-intel-linux-gcc --comptype gcc
cov-configure --template --config $COVERITY_CONFIG_FILE --compiler aarch64-intel-linux-cpp --comptype g++

echo "Installation and setup are completed!"
