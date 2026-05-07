@echo off
title TENS – Neural Assistant

echo.
echo  ╔═══════════════════════════════════════════════╗
echo  ║         TENS – Neural Assistant               ║
echo  ╚═══════════════════════════════════════════════╝
echo.

:: ── Check Python ──────────────────────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python nicht gefunden. Bitte Python 3.10+ installieren.
    pause
    exit /b 1
)

:: ── Install / update dependencies ────────────────────────────────────────────
echo  [1/3] Prüfe Abhängigkeiten...
pip install -q -r requirements.txt
if errorlevel 1 (
    echo  [WARN] Einige Pakete konnten nicht installiert werden.
)
echo  [1/3] Abhängigkeiten OK

:: ── Start Ollama (if not running) ────────────────────────────────────────────
echo  [2/3] Starte Ollama...
tasklist /FI "IMAGENAME eq ollama.exe" 2>nul | find /I "ollama.exe" >nul
if errorlevel 1 (
    start /B "" ollama serve
    echo  [2/3] Ollama gestartet
    timeout /T 3 /NOBREAK >nul
) else (
    echo  [2/3] Ollama läuft bereits
)

:: ── Start Brain API ────────────────────────────────────────────────────────────
echo  [3/3] Starte TENS Brain API...
echo.
echo  ► Chat:   http://localhost:8000/
echo  ► Brain:  http://localhost:8000/brain-view
echo  ► Admin:  http://localhost:8000/admin
echo  ► Docs:   http://localhost:8000/docs
echo.
echo  Zum Beenden: Strg+C
echo.

:: Open browser after short delay
start /B cmd /C "timeout /T 2 /NOBREAK >nul && start http://localhost:8000/"

python brain_api.py

pause
