@echo off
cd /d "%~dp0"
echo SEC Pro Beta local preview: http://127.0.0.1:8765
echo This mode uses local demo data and does not upload to GitHub.
echo Requires Python 3.11 or newer. Keep this window open while using the preview.
python secpro.py serve --preview --port 8765 --data-dir "%LOCALAPPDATA%\SECPro\preview"
pause
