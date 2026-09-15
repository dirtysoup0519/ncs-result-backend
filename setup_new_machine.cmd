@echo off
setlocal
powershell.exe -NoProfile -NoExit -ExecutionPolicy Bypass -File "%~dp0scripts\setup_new_machine.ps1" %*
