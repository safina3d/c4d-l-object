@echo off
rem Runs the L-Object test suite in Cinema 4D (c4dpy).
rem Usage: run_tests.bat [path\to\c4dpy.exe]
setlocal
if not "%~1"=="" set "C4DPY=%~1"
if "%C4DPY%"=="" set "C4DPY=C:\Program Files\Maxon Cinema 4D 2023\c4dpy.exe"
set "g_additionalModulePath=%~dp0..\L-Object"
"%C4DPY%" "%~dp0test_lobject.py"
exit /b %ERRORLEVEL%
