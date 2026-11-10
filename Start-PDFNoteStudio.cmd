@echo off
setlocal
cd /d "%~dp0"
if exist "runtime\pythonw.exe" (
  start "" "runtime\pythonw.exe" "app\OpenPDFStudio.py"
  exit /b
)
if not exist ".venv\Scripts\python.exe" (
  py -3.12 -m venv .venv
  if errorlevel 1 goto failed
)
".venv\Scripts\python.exe" -c "from importlib.metadata import version; [version(p) for p in ['PyQt6','PyMuPDF','ollama','psycopg','socksio']]" >nul 2>&1
if errorlevel 1 (
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt socksio
  if errorlevel 1 goto failed
)
".venv\Scripts\python.exe" OpenPDFStudio.py
if errorlevel 1 goto failed
exit /b
:failed
echo Open failed. See the message above and FINAL_PROJECT_TH.md.
pause
exit /b 1
