cd /D "%~dp0"
SET PYTHONUNBUFFERED=TRUE
set "ARG01=%1"
set "ARG02=%2"
python\python.exe run.py cmd.exe /c "python\python.exe %ARG01% %ARG02% && pause || pause"
