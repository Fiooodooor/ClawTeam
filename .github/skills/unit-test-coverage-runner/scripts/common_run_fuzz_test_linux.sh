#!/bin/bash
# ====================================================================
# Compyright(c) 2018 - 2019 Intel Corporation
#
# For licensing inofrmation, see the file 'LICENSE' in the root folder
# ====================================================================
if [ 1 -eq 1 ]
then
 echo params 0: $0 1: $1 2: $2 3: $3 4: $4
fi
RUNNING_DIRECTORY_PATH=$1
RELATIVE_PATH_TO_ROOT=$2
YML_PROJECT_FILE=$3
TEST_NAME=$4
ETH_FW_COMPILER=gcc

exit_func() {
	PATH=$OLD_PATH
	exit $1
}

set OLD_PATH=$PATH

# Fuzz plugin paths
CEEDLING_PLUGINS_PATH="/usr/local/share/gems/gems/ceedling-0.31.1/plugins/"
FUZZ_PLUGIN_NAME="fuzz"
FUZZ_PLUGIN_PATH="${CEEDLING_PLUGINS_PATH}${FUZZ_PLUGIN_NAME}"
FUZZ_PLUGIN_GIT="https://github.com/intel-innersource/applications.security.fuzzing.unit-fuzzing.git"

#get full path
cd  $RELATIVE_PATH_TO_ROOT
ROOT_DIRECTORY=$PWD
echo $ROOT_DIRECTORY
cd $RUNNING_DIRECTORY_PATH
export CEEDLING_MAIN_PROJECT_FILE=$RUNNING_DIRECTORY_PATH/$YML_PROJECT_FILE


/bin/rm -rf $RUNNING_DIRECTORY_PATH/build_fuzz

# If fuzz plugin isn't installed yet, clone it and move it to Ceedling plugins path
if [ ! -d $FUZZ_PLUGIN_PATH ]; then
	git clone $FUZZ_PLUGIN_GIT $FUZZ_PLUGIN_NAME 2> /dev/null
	sudo mv $FUZZ_PLUGIN_NAME $CEEDLING_PLUGINS_PATH
fi

#select which test to run
if [ "$TEST_NAME" = "" ]; then
	ceedling fuzz:all --logging --trace
else
	ceedling fuzz:$TEST_NAME --logging --trace
fi
if [ "$?" != "0" ]; then
	echo CEEDLING failed
	exit_func 1
fi
exit_func 0
