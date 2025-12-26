@echo off
setlocal enabledelayedexpansion

set MODULE_DIR=%~dp0handlers

set CMD=pyinstaller main.py  --onefile --name=server

for /r "%MODULE_DIR%" %%f in (*.py) do (
    set "full=%%f"
    set "mod=!full:%MODULE_DIR%\=!"
    set "mod=!mod:.py=!"
    set "mod=!mod:\=.!"
    set "CMD=!CMD! --hidden-import=handlers.!mod!"
)

call !CMD!

REM nuitka --standalone --show-memory --show-progress --output-dir=out --mingw64 --include-package=handlers --include-package=utils main.py