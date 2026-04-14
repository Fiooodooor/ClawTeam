REM Check number of arguments are == 8
set argsCount=0
for %%x in (%*) do Set /A argsCount+=1
IF %argsCount% NEQ 8 (
	echo "Usage is run_kw_new_ci.bat <project> <project_dir> <build_name> <project_to_link> <output_dir_log> <pipeline_build_url> <build_user_name> <build_user_mail>"
	EXIT 1
)


set current_dir=%cd%
SET KW_SERVER=klocwork-igk2.devtools.intel.com
SET KW_SERVER_PORT=8080
SET KW_LICENSE_SERVER=klocwork05p.elic.intel.com
SET KW_LICENSE_SERVER_PORT=7500
SET KLOCWORK_LTOKEN=C:\Users\sys_ethfwcigeneric\ltoken

SET project=%1
SET projectdir=%2
SET name=%3
SET project_to_link=%4
SET output_dir_log=%5
SET pipeline_build_url=%6
SET build_user_name=%7
SET build_user_mail=%8

ECHO "Path to KW binaries KW_BIN='%KW_BIN%'"
IF "%KW_BIN%"=="" ECHO "WARNING: no KW_BIN!"

SET KW_SEM_FOLDER_PATH=\\ladjfwfs4.ger.corp.intel.com\fwfs\SNIC\ci_tools\kw_semaphore
SET REL_KW_SEM_FILE_NAME="%project%.*"
SET SEM_FILE="%project%.%name%"

echo "*************** start sync with server ***************"
"%KW_BIN%"\kwxsync --url "https://%KW_SERVER%:%KW_SERVER_PORT%" %project%
IF 0 NEQ %ERRORLEVEL% EXIT /B %ERRORLEVEL%

echo "*************** start deploy sync from server ***************"
"%KW_BIN%"\kwdeploy sync --url "https://%KW_SERVER%:%KW_SERVER_PORT%"
IF 0 NEQ %ERRORLEVEL% EXIT /B %ERRORLEVEL%

cd %projectdir%

echo "*************** Run KW inject (%0) ***************"
"%KW_BIN%"\kwinject --output kwinject.out cmd /c build_script.bat
IF 0 NEQ %ERRORLEVEL% EXIT /B %ERRORLEVEL%

echo "*************** Run KW build project ***************"
"%KW_BIN%"\kwbuildproject "kwinject.out" --project %project% --host "%KW_SERVER%" --port "%KW_SERVER_PORT%" --ssl --short-log --license-host "%KW_LICENSE_SERVER%" --license-port "%KW_LICENSE_SERVER_PORT%" --tables-directory "KW_%project%" --force -j "auto"
IF 0 NEQ %ERRORLEVEL% EXIT /B %ERRORLEVEL%

REM poll on semaphore file existance from same project till deleted
pushd %KW_SEM_FOLDER_PATH%
:SEM_DELETE_LOOP
if exist %REL_KW_SEM_FILE_NAME% (
	echo "Semaphore file exists at: %REL_KW_SEM_FILE_NAME% - going to sleep 30 sec..."
	dir
	timeout 30
	goto SEM_DELETE_LOOP
)
popd

REM create new semaphore and run kwadmin
set n=0
:RUN_KW_LOOP
echo %n%
if %n% LSS 5 (
	echo "Creating semaphore file for: %SEM_FILE%"
	
	pushd %KW_SEM_FOLDER_PATH%
	echo yes | copy nul %SEM_FILE%
	popd
	
	echo "*************** Run KW admin for project (attempt: %n%) ***************"
	SET error=NO

	"%KW_BIN%"\kwadmin --host %KW_SERVER% --port %KW_SERVER_PORT% --ssl load %project% "KW_%project%" --name %name% --force && goto EXIT_RUN_KW_LOOP
	
	SET error=YES
	set /A n=%n%+1
	echo "Deleting semaphore file: $SEM_FILE"

	pushd %KW_SEM_FOLDER_PATH%
	del %SEM_FILE%
	popd

	echo "kwadmin failed printing kwloaddb.db"
	more kwloaddb.db
	if %ERRORLEVEL% neq 0 (
	    echo "raised exception when command more kwloaddb.db executed"
	)
	timeout 30
	goto RUN_KW_LOOP
) 


:EXIT_RUN_KW_LOOP

REM second try to remove semaphore
echo "Deleting semaphore file (try2): %SEM_FILE%"
pushd %KW_SEM_FOLDER_PATH%
del %SEM_FILE%
popd

REM check if kwadmin succeeded and exit on fail
if %error% == YES (
	echo "failed to upload kw build result to server"
	EXIT 100
)

echo "*************** Removing Tables Directory to save space for next runs ***************"
rmdir /s /q KW_%project%

echo "*************** Run KW verify issues for current build***************"

echo "https://%KW_SERVER%:%KW_SERVER_PORT%\review\insight-review.html#issuelist_goto:project=%project_to_link%,searchquery=build%%253A'%name%'+status%%253AAnalyze+severity%%253A1%%252C2%%252C3%%252C4,sortcolumn=id,sortdirection=ASC,start=0,view_id=1" | tee %output_dir_log%/kw_link_to_project_%project%.log


cd "%current_dir%"
REM This part is not necessary for SEP CI
REM kwxsync "--url" "https://%KW_SERVER%:%KW_SERVER_PORT%" "MEV_TS_IMC_ML" "MEV_IMC_BOOT"
REM kwxsync "--url" "https://%KW_SERVER%:%KW_SERVER_PORT%" "MEV_TS_LIBS" "MEV_NSL"
REM kwxsync "--url" "https://%KW_SERVER%:%KW_SERVER_PORT%" "MEV_IMC_USERSPACE" "MEV_TS_LINUX_USERSPACE"
REM kwxsync "--url" "https://%KW_SERVER%:%KW_SERVER_PORT%" "MEV_IMC_USERSPACE" "MMG_USERSPACE"
REM kwxsync "--url" "https://%KW_SERVER%:%KW_SERVER_PORT%" "MEV_TS_LINUX_ATF" "MEV_IMC_ATF"
REM kwxsync "--url" "https://%KW_SERVER%:%KW_SERVER_PORT%" "MMG_ATF" "MEV_IMC_ATF"
REM kwxsync "--url" "https://%KW_SERVER%:%KW_SERVER_PORT%" "MEV_TS_LINUX_BOOT" "MEV_IMC_BOOT"
REM kwxsync "--url" "https://%KW_SERVER%:%KW_SERVER_PORT%" "MEV_TS_LINUX_NSL" "MEV_NSL"
REM kwxsync "--url" "https://%KW_SERVER%:%KW_SERVER_PORT%" "MEV_TS_LINUX_INFRA" "MEV_IMC_INFRA"
REM kwxsync "--url" "https://%KW_SERVER%:%KW_SERVER_PORT%" "MMG_INFRA" "MEV_IMC_INFRA"
REM kwxsync "--url" "https://%KW_SERVER%:%KW_SERVER_PORT%" "MEV_TS_LINUX_PHYSS" "MEV_PHYSS"

python -m pip install --proxy=http://proxy-chain.intel.com:911 -r ./requirements.txt --user 2> null
IF 0 NEQ %ERRORLEVEL% EXIT /B %ERRORLEVEL%

parse_create_kw_report.py -b %name% -html %output_dir_log%\KlocWork_report.html -proj %project% -pl %project_to_link% -t "62693413898a69d8c12ca3297398bd0655b85b543a0995902bb09d54c751124e" -u "sys_sysfw" -m "alex.bilik@intel.com mahmoudx.omar@intel.com" %build_user_mail% -bu %pipeline_build_url% -pr %pipeline_build_url% -s "https://%KW_SERVER%:%KW_SERVER_PORT%" --build_user %build_user_name%
IF 0 NEQ %ERRORLEVEL% EXIT /B %ERRORLEVEL%

echo "kw result on server can find : https://%KW_SERVER%:%KW_SERVER_PORT%\review\insight-review.html#issuelist_goto:project=%project_to_link%,searchquery=build%%253A'%name%'+status%%253AAnalyze+severity%%253A1%%252C2%%252C3%%252C4,sortcolumn=id,sortdirection=ASC,start=0,view_id=1"
