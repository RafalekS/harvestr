@echo off
REM Update harvestr from your fork: https://github.com/RafalekS/harvestr
REM (Replaces the old clone+patch flow. Upstream updates are merged into the
REM  fork separately, then land here via this pull.)
cd /d "C:\Scripts\Media\harvestr"

echo Pulling latest from your fork (origin/main)...
git pull --ff-only origin main
if errorlevel 1 (
    echo.
    echo ERROR: git pull failed. If you made local edits, commit or discard them first.
    pause
    exit /b 1
)

echo.
REM Deps (yt-dlp, flask, etc.) live in the venv that runs webui.py + the downloader.
REM The launcher GUI uses global Python (PyQt6) and is not covered by requirements.txt.
if exist "venv\Scripts\python.exe" (
    echo Updating dependencies in venv...
    "venv\Scripts\python.exe" -m pip install -r requirements.txt
) else (
    echo Updating dependencies (global Python)...
    python -m pip install -r requirements.txt
)

echo.
echo Update complete.
pause
