@echo off
REM ── bz2togrib launcher ──────────────────────────────────────────────

python -m AdaptEns.grib_decoder "%~1"

IF %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Script failed with exit code %ERRORLEVEL%
    pause
) ELSE (
    echo.
    echo [DONE] Finished successfully.
    exit
)