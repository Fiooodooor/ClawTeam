@echo off

rem Some definitions
set upload_Folder=\\ladjfs.jer.intel.com\hwfw\Software\Trace32\MEVTS

rem Check Trace32 base folder exists
IF NOT EXIST %upload_Folder% (
	ECHO %upload_Folder% not found!
	goto :ERROR
)


pushd "%~dp0"

echo Uploading MEVTS Menus Setup folder to %upload_Folder%...

rem upload everything in Menus
xcopy MEVTS_Menues %upload_Folder%\MEVTS_Menues /E /Y /I 
xcopy  /y init_subcore.cmm %upload_Folder%\*
xcopy  /y update_mevts_menu.bat %upload_Folder%\*
xcopy  /y readme.txt %upload_Folder%\*

popd

IF ERRORLEVEL 1 GOTO ERROR

ECHO MEVTS Menus Setup Upload Succeded!
PAUSE
goto :eof

:ERROR
ECHO MEVTS Menus Setup Upload Failed!
PAUSE