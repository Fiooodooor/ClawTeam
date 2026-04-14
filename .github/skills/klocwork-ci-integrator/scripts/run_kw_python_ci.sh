#!/bin/bash
#set -x
set -e
set -o xtrace

if [ $# -ne 8 ]
then
	echo "usage is ./run_kw_python_ci.sh <project_name> <project_dir> <build_name> <project_to_link> <output_dir_log> <pipeline_build_url> <build_user_name> <build_user_mail>"
	exit 1
fi

current_dir=$(pwd)

# Begin script in case all parameters are correct
project="$1"
projectdir="$2"
name="$3"
project_to_link="$4"
output_dir_log=$5
pipeline_build_url=$6
build_user_name=$7
build_user_mail=$8

echo "project name is $project"
echo "project dir is $projectdir"
echo "build name is $name"
echo "project to link is $project_to_link"
echo "out dir to save log is $output_dir_log"

SEM_FILE="$project.$name"
KW_SEM_FOLDER_PATH="/mnt/ci_tools/kw_semaphore"
SEM_FILE_PATH="$KW_SEM_FOLDER_PATH/$SEM_FILE"
REL_SEM_FILE_PATH="$KW_SEM_FOLDER_PATH/$project.*"
KW_SERVER=gerklocwork001.devtools.intel.com
KW_SERVER_PORT=8090
KW_LICENSE_SERVER=klocwork05p.elic.intel.com
KW_LICENSE_SERVER_PORT=7500
# KW_SYNC_SERVER=klocwork-igk2.devtools.intel.com

echo "Checking disk size before..."
df -h /srv
du -hl

export KLOCWORK_LTOKEN=~/klocwork/ltoken
echo "*************** start Auth with server ***************"
# kwauth --host $KW_SERVER --port $KW_SERVER_PORT --ssl
echo "*************** start sync with server ***************"
/home/sys_sysfw/klocwork_22.2/bin/kwxsync --url "https://$KW_SERVER:$KW_SERVER_PORT"  $project_to_link

echo "*************** start deploy sync from server ***************"
/home/sys_sysfw/klocwork_22.2/bin/kwdeploy sync --url https://$KW_SERVER:$KW_SERVER_PORT

cd $projectdir
# source mev_imc_init_build_env
export KLOCWORK_LTOKEN=~/klocwork/ltoken
set LM_LICENSE_FILE=$KW_LICENSE_SERVER_PORT@$KW_LICENSE_SERVER

echo "*************** Run KW pyspec ($0) ***************"
if [ "$project" == "nvm-generator" ]
then
  /home/sys_sysfw/klocwork_22.2/bin/kwpyspec `pwd`
fi

echo "Checking disk size after kwpyspec..."
df -h /srv
du -hl -d 1

set +e
echo "*************** Run KW build project ***************"
/home/sys_sysfw/klocwork_22.2/bin/kwbuildproject kwpyspec.out --project $project_to_link --host $KW_SERVER --port $KW_SERVER_PORT --ssl --short-log --license-host $KW_LICENSE_SERVER --license-port $KW_LICENSE_SERVER_PORT --tables-directory "KW_$project" --force -j auto
set -e
export KLOCWORK_LTOKEN=~/klocwork/ltoken
#echo "*************** Run KW admin for project ***************"
#kwadmin --host $KW_SERVER --port $KW_SERVER_PORT --ssl load $project "KW_$project" --name "$name" --force

echo "Checking disk size after kwbuildproject..."
df -h /srv
du -hl -d 1

while compgen -G $REL_SEM_FILE_PATH > /dev/null
do
  echo "Semaphore file exists at: $REL_SEM_FILE_PATH - going to sleep 30 sec..."
  ls -la $KW_SEM_FOLDER_PATH
  sleep 30
done

n=0
until [ "$n" -ge 5 ]
do
   # creating semaphore file to declare that a KW build for certain KW project is being uploaded
   echo "Creating semaphore file for: $SEM_FILE"
   sudo touch $SEM_FILE_PATH
   echo "*************** Run KW admin for project (attempt: $n) ***************"
   /home/sys_sysfw/klocwork_22.2/bin/kwadmin --host $KW_SERVER --port $KW_SERVER_PORT --ssl load $project_to_link "KW_$project" --name "$name" --force && break  # substitute your command here
   n=$((n+1))
   echo "Deleting semaphore file: $SEM_FILE"
   sudo rm -rf $SEM_FILE_PATH
   echo "kwadmin failed printing kwloaddb.db"
   cat kwloaddb.db || echo "cat: kwloaddb.db: No such file or directory"

   echo "Checking disk size after kwadmin..."
   df -h /srv
   du -hl -d 1

   sleep 30
done

echo "Deleting semaphore file (try2): $SEM_FILE"
sudo rm -rf $SEM_FILE_PATH


if [ $? -gt 0 ]; then
	echo "failed to upload kw build result to server"
	exit 1
fi
# cp -r /var/jenkins_slave/ltoken /root/.klocwork/

echo "*************** Removing Tables Directory to save space for next runs ***************"
rm -rf "./KW_$project"

echo "*************** Run KW verify issues for current build***************"

echo "https://$KW_SERVER:$KW_SERVER_PORT/review/insight-review.html#issuelist_goto:project=$project_to_link,searchquery=build%253A'${name}'+status%253AAnalyze+severity%253A1%252C2%252C3%252C4,sortcolumn=id,sortdirection=ASC,start=0,view_id=1" | tee $output_dir_log/kw_link_to_project_$project.log

cd $current_dir
# sudo ./kwquery.py sys_sysfw 62693413898a69d8c12ca3297398bd0655b85b543a0995902bb09d54c751124e $project https://$KW_SERVER:$KW_SERVER_PORT

sudo python -m pip install --proxy=http://proxy-chain.intel.com:911 -r ./requirements.txt --user 2> null
# -b "$name" -html .\KlocWork_report.html -p $project -t 62693413898a69d8c12ca3297398bd0655b85b543a0995902bb09d54c751124e -u sys_sysfw -m alex.bilik@intel.com -bu https://www.google.com/ -pr https://www.google.com/ -bus -s https://$KW_SERVER:$KW_SERVER_PORT
chmod +x ./parse_create_kw_report.py
sudo ./parse_create_kw_report.py -b "$name" -html $output_dir_log\KlocWork_report.html -proj $project_to_link -pl $project_to_link -t 350bd36c6909f46117b6b364b34e23d8022990ea0147461cfffaf38245c2e073 -u sys_sysfw -m alex.bilik@intel.com mahmoudx.omar@intel.com $build_user_mail -bu $pipeline_build_url -pr $pipeline_build_url -s https://$KW_SERVER:$KW_SERVER_PORT --build_user "$build_user_name"
echo "kw result on server can find : https://$KW_SERVER:$KW_SERVER_PORT/review/insight-review.html#issuelist_goto:project=$project_to_link,searchquery=build%253A'${name}'+status%253AAnalyze+severity%253A1%252C2%252C3%252C4,sortcolumn=id,sortdirection=ASC,start=0,view_id=1"
