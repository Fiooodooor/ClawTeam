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
ETH_FW_COMPILER=covc

exit_func() {
	#unset bullseye
	if [ "$APPLY_COVERAGE" = "yes" ]; then
		/opt/BullseyeCoverage/bin/cov01 --off
	fi
	PATH=$OLD_PATH
	exit $1
}

set OLD_PATH=$PATH
if [ -v $APPLY_COVERAGE ]; then
	APPLY_COVERAGE="yes"
	PATH=/opt/BullseyeCoverage/bin:$PATH
fi
#get full path
cd  $RELATIVE_PATH_TO_ROOT
ROOT_DIRECTORY=$PWD
echo $ROOT_DIRECTORY
cd $RUNNING_DIRECTORY_PATH
export CEEDLING_MAIN_PROJECT_FILE=$RUNNING_DIRECTORY_PATH/$YML_PROJECT_FILE
HTML_REPORT_DIR=$RUNNING_DIRECTORY_PATH/build/html_report

if [ -z $COVFILE ]; then
	export COVFILE=$RUNNING_DIRECTORY_PATH/build/test.cov
fi

echo COVFILE=$COVFILE

/bin/rm -rf $RUNNING_DIRECTORY_PATH/build
#set bullseye
if [ "$APPLY_COVERAGE" = "yes" ]; then
	cov01 -1
fi

if [ "$?" != "0" ]; then
	echo bullseye cov01 faild $RESULT
	exit_func 1
fi
#select which test to run
if [ "$TEST_NAME" = "" ]; then
	ceedling test:all --logging --trace
else
	ceedling test:$TEST_NAME --logging --trace
fi
if [ "$?" != "0" ]; then
	echo CEEDLING failed
	exit_func 1
fi
#create clover report for Jenkins
if [ "$APPLY_COVERAGE" = "yes" ]; then
	mkdir -p $HTML_REPORT_DIR
	# covhtml -f $COVFILE $HTML_REPORT_DIR
    $IMC_TOOLS_ROOT/BullsHTML_Linux/bullshtml.sh -f $COVFILE $HTML_REPORT_DIR
fi
if [ "$?" != "0" ]; then
	echo covhtml failed
	exit_func 1
fi

if [ "$COVFILTER_PATTERN" != "" ]; then
    echo COVFILTER_PATTERN is $COVFILTER_PATTERN
    covselect -f$COVFILE -a $COVFILTER_PATTERN
fi

exit_func 0
