@echo off
:: Build standalone Windows executable (dist\rom.exe) using PyInstaller
setlocal enabledelayedexpansion

set "ROOT=%~dp0"
cd /d "%ROOT%"

set "VENV=%USERPROFILE%\.venvs\rom"

:: ── 1. Detect Python Environment ──────────────────────────────────────────
if exist "%VENV%\Scripts\python.exe" (
    set "PY=%VENV%\Scripts\python.exe"
) else (
    where pyinstaller >nul 2>&1
    if !errorlevel! equ 0 (
        set "PY=python"
    ) else (
        where python >nul 2>&1 && ( set "PY=python" & goto :found_py )
        where py >nul 2>&1 && ( set "PY=py -3" & goto :found_py )
        echo [ERROR] Python not found. Please install Python 3.8+ or run install.bat first.
        exit /b 1
    )
)

:found_py
echo using Python: %PY%

:: ── 2. Ensure Required Build Tools ─────────────────────────────────────────
echo checking dependencies...
%PY% -m pip install -q pyinstaller textual rich pillow >nul 2>&1

:: ── 3. Protect Against Python 3.10.0 BPO-45434 dis.py bug ───────────────────
%PY% -c "import sys, os; sitedirs = [p for p in sys.path if 'site-packages' in p]; sc = os.path.join(sitedirs[0], 'sitecustomize.py') if sitedirs else None; (open(sc, 'w', encoding='utf-8').write('import dis\n_orig = dis._unpack_opargs\ndef _fixed(code):\n    ext = 0\n    for i in range(0, len(code), 2):\n        op = code[i]\n        if op >= dis.HAVE_ARGUMENT:\n            arg = code[i+1] | ext\n            ext = (arg << 8) if op == dis.EXTENDED_ARG else 0\n        else:\n            arg = None\n            ext = 0\n        yield (i, op, arg)\ndis._unpack_opargs = _fixed\n') if sc and not os.path.exists(sc) else None)" >nul 2>&1

:: ── 4. Build Standalone rom.exe ────────────────────────────────────────────
echo.
echo ========================================================
echo   Compiling rom-cli to standalone Windows EXE...
echo ========================================================
echo.

if exist "%ROOT%rom.spec" (
    %PY% -m PyInstaller --clean -y "%ROOT%rom.spec"
) else (
    %PY% -m PyInstaller --clean -y --onefile --name rom --paths . --collect-all textual --collect-all rich --collect-all PIL --collect-all rom bin/rom
)

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Build failed! See logs above.
    exit /b %errorlevel%
)

echo.
echo ========================================================
echo   BUILD SUCCESSFUL!
echo   Executable: %ROOT%dist\rom.exe
echo ========================================================
echo.

:: ── 5. Optionally Copy to User Bin Directory ──────────────────────────────
if exist "%USERPROFILE%\bin" (
    copy /y "%ROOT%dist\rom.exe" "%USERPROFILE%\bin\rom.exe" >nul
    echo Copied rom.exe to %USERPROFILE%\bin\rom.exe (in your PATH)
)

echo.
echo You can run it directly:
echo   .\dist\rom.exe
echo   .\dist\rom.exe -l
echo.
