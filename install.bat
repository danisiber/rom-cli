@echo off
:: Installs the rom CLI on Windows (CMD / PowerShell).
:: For Git Bash users, use ./install.sh instead.
setlocal

set "ROOT=%~dp0"
set "SRC=%ROOT%bin"
set "DEST=%USERPROFILE%\bin"
set "VENV=%USERPROFILE%\.venvs\rom"

:: ── Detect Python ──────────────────────────────────────────────────────
python --version >nul 2>&1 && ( set "PY=python" & goto :found_py )
py -3 --version >nul 2>&1 && ( set "PY=py -3" & goto :found_py )
python3 --version >nul 2>&1 && ( set "PY=python3" & goto :found_py )
echo Python not found. Install Python 3.8+ from https://python.org
exit /b 1

:found_py
echo using: %PY%

:: ── Create venv ────────────────────────────────────────────────────────
if not exist "%DEST%" mkdir "%DEST%"
if not exist "%VENV%\Scripts\python.exe" (
    echo creating venv in %VENV%
    %PY% -m venv "%VENV%"
)

echo installing textual and pillow
"%VENV%\Scripts\python.exe" -m pip install -q --upgrade pip >nul 2>&1
"%VENV%\Scripts\python.exe" -m pip install -q textual pillow

:: ── Create wrapper scripts ─────────────────────────────────────────────────
echo @echo off> "%DEST%\rom.cmd"
echo "%VENV%\Scripts\python.exe" "%SRC%\rom" %%*>> "%DEST%\rom.cmd"

(
echo #!/usr/bin/env bash
echo exec "%VENV%\Scripts\python.exe" "%SRC%\rom" "$@"
) > "%DEST%\rom"

echo.
echo installed: %DEST%\rom.cmd  (for CMD / PowerShell)
echo installed: %DEST%\rom      (for Git Bash / MSYS2)
echo venv:      %VENV%

:: ── Safe PATH Registration ─────────────────────────────────────────────────
powershell -NoProfile -Command "$d = '%DEST%'; $p = [Environment]::GetEnvironmentVariable('Path', 'User'); if ($p -notlike ('*' + $d + '*')) { [Environment]::SetEnvironmentVariable('Path', ($d + ';' + $p), 'User'); Write-Host '  added ' + $d + ' to your User PATH' }" >nul 2>&1

echo.
echo test: rom -l    ^|    rom --index
