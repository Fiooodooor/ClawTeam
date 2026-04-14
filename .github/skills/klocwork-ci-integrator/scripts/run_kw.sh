#!/bin/bash

set -o xtrace

if [ $# -ne 5 ] && [ $# -ne 6 ]
then
	echo "usage is ./run_kw.sh <project_name> <project_dir> <build_name> <mev_project>"
	exit 1
fi 

current_dir=$(pwd)

# Begin script in case all parameters are correct
project="$1"
projectdir="$2"
name="$3"
project_to_link="$4"
output_dir_log=$5
mev_project=$6

echo "project name is $project"
echo "project dir is $projectdir"
echo "build name is $name"
echo "out dir to save log is $project_to_link"
echo "out dir to save log is $output_dir_log"
echo "mev_project to save log is $mev_project"


KW_SERVER=gkvkw004.igk.intel.com
KW_SERVER_PORT=8080
KW_LICENSE_SERVER=klocwork05p.elic.intel.com
KW_LICENSE_SERVER_PORT=7500
KW_SYNC_SERVER=klocwork-igk2.devtools.intel.com

export KLOCWORK_LTOKEN=~/klocwork/ltoken
echo "*************** start Auth with server ***************"
# kwauth --host $KW_SERVER --port $KW_SERVER_PORT --ssl
echo "*************** start sync with server ***************"
kwxsync --url "https://$KW_SYNC_SERVER:$KW_SERVER_PORT"  $project

echo "*************** start deploy sync from server ***************"
kwdeploy sync --url https://$KW_SERVER:$KW_SERVER_PORT

cd $projectdir
# source mev_imc_init_build_env
export KLOCWORK_LTOKEN=~/klocwork/ltoken
set LM_LICENSE_FILE=$KW_LICENSE_SERVER_PORT@$KW_LICENSE_SERVER
echo "*************** Run KW inject ***************"
if [ $project == "MEV_NSL" ]; 
then
	if [ $mev_project == "MEV_TS" ];
	then
		kwinject --output kwinject.out sh build/nsl_build_release_imc.sh -t mev_ts
		kwinject --output kwinject.out sh build/nsl_build_release_imc_llvm.sh -t mev_ts
	else 
		kwinject --output kwinject.out sh build/nsl_build_release_imc.sh
		kwinject --output kwinject.out sh build/nsl_build_release_imc_llvm.sh
	fi	
else
	kwinject --output kwinject.out sh mev_imc_build_all.sh
fi
set +e
echo "*************** Run KW build project ***************"
kwbuildproject kwinject.out --project $project --host $KW_SERVER --port $KW_SERVER_PORT --ssl  --license-host $KW_LICENSE_SERVER --license-port $KW_LICENSE_SERVER_PORT --tables-directory "KW" --force -j auto
set -e
export KLOCWORK_LTOKEN=~/klocwork/ltoken
echo "*************** Run KW admin for project ***************"
for i in 1 2 3 4 5
do
  kwadmin --host $KW_SERVER --port $KW_SERVER_PORT --ssl load $project KW --name "$name" --force
  if [ $? -eq 0 ]; then
    break
  fi
  echo "failed to upload kw build result to server, try $i of 5"
  sleep 30
done
if [ $? -gt 0 ]; then
    echo "failed to upload kw build result to server"
    exit 1
fi
# cp -r /var/jenkins_slave/ltoken /root/.klocwork/

echo "*************** Run KW verify issues for current build***************"

echo "https://$KW_SYNC_SERVER:$KW_SERVER_PORT/review/insight-review.html#issuelist_goto:project=$project_to_link,searchquery=build%253A'${name}'+status%253AAnalyze+severity%253A1%252C2%252C3%252C4,sortcolumn=id,sortdirection=ASC,start=0,view_id=1" | tee $output_dir_log/kw_link_to_project_$project.log

cd $current_dir
sudo ./kwquery.py sys_sysfw 62693413898a69d8c12ca3297398bd0655b85b543a0995902bb09d54c751124e $project https://$KW_SERVER:$KW_SERVER_PORT

echo "kw result on server can find : https://$KW_SYNC_SERVER:$KW_SERVER_PORT/review/insight-review.html#issuelist_goto:project=$project_to_link,searchquery=build%253A'${name}'+status%253AAnalyze+severity%253A1%252C2%252C3%252C4,sortcolumn=id,sortdirection=ASC,start=0,view_id=1"
