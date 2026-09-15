@echo off
rem Windows-side driver for the VM ADS sync watcher (README section 3.11).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start_ads_sync.ps1" %*
