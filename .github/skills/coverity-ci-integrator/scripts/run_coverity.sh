#!/bin/bash
# ===================================================================
# Copyright(c) 2023 - 2023 Intel Corporation
#
# For licensing information, see the file 'LICENSE' in the root folder
# ====================================================================

set -e
set -o xtrace

if [ $# -ne 12 ]
then
	echo "usage is ./run_coverity.sh <build_command> <project_name> <stream_name> <project_dir> <build_name> <project_to_link> <output_dir_log> <pipeline_build_url> <build_user_name> <build_user_mail> <config_type> <custom_checkers_dir> <additional_coverity_excludes>"
	exit -1
fi 

current_dir=$(pwd)

# Begin script in case all parameters are correct
build_command="$1"
project="$2"
stream="$3"
projectdir="$4"
name="$5"
output_dir_log=$6
pipeline_build_url=$7
build_user_name=$8
build_user_mail=$9
config_type=${10}
custom_checkers_dir=${11}
additional_coverity_excludes=${12}

echo "project name is $project"
echo "stream name is $stream"
echo "project dir is $projectdir"
echo "build name is $name"
echo "out dir to save log is $output_dir_log"

#Not in use yet, if needed implement semaphore logic
SEM_FILE="$stream.$name"
COVERITY_SEM_FOLDER_PATH="/mnt/ci_tools/coverity_semaphore"
SEM_FILE_PATH="$COVERITY_SEM_FOLDER_PATH/$SEM_FILE"
REL_SEM_FILE_PATH="$COVERITY_SEM_FOLDER_PATH/$stream.*"

if [ -z "$additional_coverity_excludes" ]; then
  EXCLUDE_PATHS="\/usr\/share\/.*|\/opt\/Xtensa_Explorer\/.*"
else
  EXCLUDE_PATHS="\/usr\/share\/.*|\/opt\/Xtensa_Explorer\/.*|"$additional_coverity_excludes
fi

COV_SERVER=https://coverity.devtools.intel.com/prod8

echo "Checking disk size before..."
df -h /srv
du -hl -d 1

echo "Adding all codexm checkers into a single command line..."
codexm_files=""
for file in $(find $custom_checkers_dir -maxdepth 1 -type f -name "*.cxm"); do
  codexm_files+="--codexm ${file} "
done
echo "CodeXM command line: $codexm_files"

# need to set path as . imc_setenv overrides initial dockerfile path
export PATH=$PATH:/opt/coverity/analysis/bin
# need it so coverity could access all codexm_files and run builds without warnings
git config --global --add safe.directory "*"

# Set config file configuration and choose which compiler config to use
if [ "${config_type}" == "arm" ]; then
    #arm compilers config
    cov-configure --template --config mev-coverity-config.xml --compiler arm --comptype armcc
    cov-configure --template --config mev-coverity-config.xml --compiler aarch64-intel-linux-gcc --comptype gcc
    cov-configure --template --config mev-coverity-config.xml --compiler aarch64-intel-linux-cpp --comptype g++
    config_file=mev-coverity-config.xml
elif [ "${config_type}" == "nsc" ]; then
    #nsc compilers config
    cov-configure --template --config mev-coverity-config.xml --compiler arm --comptype armcc
    cov-configure --template --config mev-coverity-config.xml --compiler aarch64-none-elf-gcc --comptype gcc
    cov-configure --template --config mev-coverity-config.xml --compiler aarch64-intel-linux-cpp --comptype g++
    config_file=mev-coverity-config.xml
    export PATH=/opt/arm-toolchain/arm-gnu-toolchain-14.2.rel1-x86_64-aarch64-none-elf/bin:$PATH
elif [ "${config_type}" == "xtensa" ]; then
    #xtensa compilers config
    cov-configure --template --config xtensa-coverity.xml --compiler xt-clang --comptype xtclang
    cov-configure --template --config xtensa-coverity.xml --compiler aarch64-intel-linux-gcc --comptype gcc
    cov-configure --template --config xtensa-coverity.xml --compiler aarch64-intel-linux-cpp --comptype g++
    config_file=xtensa-coverity.xml
elif [ "${config_type}" == "python" ]; then
    cov-configure --template --config python-coverity.xml --python
    config_file=python-coverity.xml
else
    echo "Unknown config_type: ${config_type}"
fi

#creating cov stream build directory to store coverity artifacts, and cov-results output dir
mkdir -p cov-$stream
mkdir -p $output_dir_log/cov-results
cd $projectdir

echo "PATH content: $PATH"

# Verify no previous build dir exists with the same name
rm -rf $WORKSPACE/cov-$stream
# cov-build (building project), cov-analyze (static analysis), cov-commit-defects (sends results to coverity server)

if [ "${config_type}" == "python" ]; then
    cov-build --config $WORKSPACE/$config_file --dir $WORKSPACE/cov-$stream --no-command --fs-capture-search $projectdir
else
    cov-build --config $WORKSPACE/$config_file --dir $WORKSPACE/cov-$stream bash "$build_command"
fi

# Check for existing stream, if not add one and connect to project
existing_streams=`cov-manage-im --mode projects --show --name "${project}" --output streams --fields stream-name --auth-key-file /mnt/ci_tools/auth-key.txt --url $COV_SERVER`
echo "Existing streams: $existing_streams"
if [[ "${existing_streams}" =~ "${stream}" ]]; then
  echo "${stream} already present in project: ${project}"
else
  echo "${stream} NOT present in project: ${project} .. creating"
  # ignoring any failure in the create stream command
#  cov-manage-im --mode streams --add --set name:"${stream}" --set lang:"Mixed" --set desc:"${stream} stream" --set triage:"TS_${project}" --set expiration:enabled --auth-key-file /mnt/ci_tools/auth-key.txt --url $COV_SERVER || true
  cov-manage-im --mode streams --add --set name:"${stream}" --set lang:"Mixed" --set desc:"${stream} stream" --set expiration:enabled --auth-key-file /mnt/ci_tools/auth-key.txt --url $COV_SERVER || true
  cov-manage-im --mode projects --name "${project}" --update --insert stream:"${stream}" --auth-key-file /mnt/ci_tools/auth-key.txt --url $COV_SERVER
fi

cov-analyze --dir $WORKSPACE/cov-$stream --aggressiveness-level high --enable-parse-warnings --parse-warnings-config $IMC_TOOLS_ROOT/scripts/coverity/parse_warnings.conf $codexm_files --checker-option UNUSED_VALUE:report_overwritten_initializer:false --checker-option DEADCODE:no_dead_default:true  
cov-commit-defects --dir $WORKSPACE/cov-$stream --url $COV_SERVER --description $name --snapshot-id-file $output_dir_log/cov-results/snapshot-$stream.txt --stream $stream  --auth-key-file /mnt/ci_tools/auth-key.txt --exclude-files "${EXCLUDE_PATHS}"

# need those packages to run rest api call to coverity server to export CSV with results, better move those and jq installation to dockerfile
sudo python -m pip install --proxy=http://proxy-chain.intel.com:911 requests
sudo python -m pip install --proxy=http://proxy-chain.intel.com:911 future
echo "COVERITY result on server can find : $COV_SERVER/query/defects.htm?project=$project&snapshotId=$(cat $output_dir_log/cov-results/snapshot-$stream.txt)"
chmod a+x $IMC_TOOLS_ROOT/scripts/coverity/get_coverity_run_issues.py
apt -y install jq # json parser
# rest api call to coverity server to export CSV with results
python $IMC_TOOLS_ROOT/scripts/coverity/get_coverity_run_issues.py -server $COV_SERVER -project $project -stream $stream -snapshot $(cat $output_dir_log/cov-results/snapshot-$stream.txt) -user sys_sysfw -pass $(cat /mnt/ci_tools/auth-key.txt  | jq -r '.key') > $output_dir_log/cov-results/results-$stream.csv

chmod -R 777 $output_dir_log

echo "Checking disk size after coveritybuildproject..."
df -h /srv
du -hl -d 1

# need to add logic here to send mails to owners and the one who ran this build with coverity project returned csv from rest api call
# and also to fail the build if csv is full of issues (not empty)
