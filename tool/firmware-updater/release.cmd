@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" py -3.11 -m venv .venv
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed
if not defined IDF_PATH set "IDF_PATH=D:\project\esp-idf-v6.0.2"
call "%IDF_PATH%\export.bat"
if errorlevel 1 goto failed
cd /d "%~dp0..\.."
python "%IDF_PATH%\tools\idf.py" build
if errorlevel 1 goto failed
cd /d "%~dp0"
".venv\Scripts\python.exe" package_release.py
if errorlevel 1 goto failed
echo Release ready in "%~dp0release"
if /i not "%~1"=="--quiet" pause
exit /b 0
:failed
echo Release failed.
if /i not "%~1"=="--quiet" pause
exit /b 1
