@echo off
setlocal DisableDelayedExpansion
rem Do not inherit incompatible PowerShell 7 module paths into Windows PowerShell.
set "PSModulePath="
pushd "%~dp0" || exit /b 1
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -ExecutionPolicy RemoteSigned -File "%~dp0scripts\stop-local.ps1"
if errorlevel 1 (
  echo.
  echo Stop refused. Read the diagnostic above and docs\LOCAL-DESKTOP.md.
  echo No application data was deleted.
  pause
  popd
  exit /b 1
)
popd
exit /b 0
