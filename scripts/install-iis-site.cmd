@echo off
REM Creates the Cacsms-Traders IIS site (requires Administrator approval).
powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process powershell -Verb RunAs -ArgumentList '-NoProfile -ExecutionPolicy Bypass -File \"%~dp0setup-iis.ps1\"' -Wait"
pause
