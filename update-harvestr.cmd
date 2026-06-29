@echo off
copy /Y "C:\Scripts\Media\harvestr\harvestr-local.patch" "V:\harvestr\patch\harvestr-local.patch"
if errorlevel 1 (
    echo ERROR: Failed to copy patch file. Is V: drive mapped?
    pause
    exit /b 1
)
pwsh.exe -ExecutionPolicy Bypass -File "C:\Scripts\Media\harvestr\Apply-HarvestrPatch.ps1"
