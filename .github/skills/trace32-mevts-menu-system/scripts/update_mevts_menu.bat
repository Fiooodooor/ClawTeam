@echo off

rem Some definitions
set T32_folder=C:\T32
set Menue_folder=%T32_folder%\demo\arm
set Script_folder=%T32_folder%\scripts
set Kernel_folder=%T32_folder%\demo\arm

rem Check Trace32 base folder exists
IF NOT EXIST %T32_folder% (
	ECHO %T32_folder% not found!
	goto :ERROR
)


pushd "%~dp0"


xcopy MEVTS_Menues %Menue_folder%\MEVTS_Menues /E /Y /I 
xcopy  /y init_subcore.cmm %Script_folder%\*

popd

IF ERRORLEVEL 1 GOTO ERROR

ECHO MEVTS Menus Update Succeded!
PAUSE
goto :eof

:ERROR
ECHO MEVTS Menus Update Failed!
PAUSE