REM ===================================================================
REM Copyright(c) 2018 - 2019 Intel Corporation
REM
REM For licensing information, see the file 'LICENSE' in the root folder
REM ====================================================================

REM parameters:
REM Param1: RUNNING_DIRECTORY_PATH
REM Param2: RELATIVE_PATH_TO_ROOT
REM Param3: YML_PROJECT_FILE
REM Param5: APPLY_COVERAGE
REM Param5: TEST_NAME
REM example: common_run_utests.bat %~dp0 ..\..\ filename.yml YES testname
@echo OFF

setlocal EnableDelayedExpansion

SET RUNNING_DIRECTORY_PATH=%1
SET RELATIVE_PATH_TO_ROOT=%2
SET YML_PROJECT_FILE=%3
SET APPLY_COVERAGE=%4
SET TEST_NAME=%5

SET ETH_FW_COMPILER = covc.exe 


IF NOT DEFINED APPLY_COVERAGE (
	SET APPLY_COVERAGE=YES
)

SET CYGWIN_LOCAL_PATH=C:\mev_toolchain\cygwin64\
SET RUBY_PATH=C:\Ruby26-x64\bin\;

REM get full path
cd %RELATIVE_PATH_TO_ROOT%
SET ROOT_DIRECTORY=%CD%

cd %RUNNING_DIRECTORY_PATH%

set CEEDLING_MAIN_PROJECT_FILE=%RUNNING_DIRECTORY_PATH%\%YML_PROJECT_FILE%

set CEEDLING_WS_PATH=%ROOT_DIRECTORY%\ndfw_mountevans-mev_tools\ceedling\ceed_ws\
set HTML_REPORT_DIR=%RUNNING_DIRECTORY_PATH%\build\html_report

IF NOT DEFINED COVFILE (
	set COVFILE=%RUNNING_DIRECTORY_PATH%\build\test.cov
)

set PATH=%CYGWIN_LOCAL_PATH%bin;%RUBY_PATH%;%PATH%

REM if bullseye needed add to path

IF /I ["%APPLY_COVERAGE%"] == ["YES"] (
	set PATH=%ROOT_DIRECTORY%\ndfw_mountevans-mev_tools\BullseyeCoverage\bin;%ROOT_DIRECTORY%\ndfw_mountevans-mev_tools\BullsHTML\;!PATH!
)


rmdir /s /q %RUNNING_DIRECTORY_PATH%\build > nul
echo "issue to ignore if dir not exist"


REM set bullseye
IF /I ["%APPLY_COVERAGE%"] == ["YES"] (
	%ROOT_DIRECTORY%\ndfw_mountevans-mev_tools\BullseyeCoverage\bin\cov01 -1
)
IF %ERRORLEVEL% NEQ 0 (
  ECHO bullseye cov01 failed
  goto ERRORS
)

REM select which test to run
IF [%TEST_NAME%]==[] (
	call %CEEDLING_WS_PATH%ceedling test:all logging
) ELSE (
	call %CEEDLING_WS_PATH%ceedling test:%TEST_NAME% logging
)

REM Note: Ceedling Error level ignored since Ceedling returns Error on test failures 

REM Filter out non-relevant files from coverage report
setlocal DisableDelayedExpansion
IF DEFINED COVFILTER_PATTERN (
	%ROOT_DIRECTORY%\ndfw_mountevans-mev_tools\BullseyeCoverage\bin\covselect -f%COVFILE% -a %COVFILTER_PATTERN%
)
setlocal EnableDelayedExpansion


REM create clover report for Jenkins
IF [%APPLY_COVERAGE%]==[YES] (
	md %HTML_REPORT_DIR%
	bullshtml.exe -f %COVFILE% %HTML_REPORT_DIR%
)

IF [%APPLY_COVERAGE%]==[YES] IF %ERRORLEVEL% NEQ 0 (
  ECHO bullsHTML failed
  goto ERRORS
)

:PASS_OK
exit /B 0


:ERRORS
exit /B 1