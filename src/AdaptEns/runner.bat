@echo off 
REM ── bz2togrib launcher ──────────────────────────────────────────────        
python -m AdaptEns.grib_decoder "%~1" "%~2" "%~3" "%~4"
REM ── proceed with ranking only if 6th argument is True ──────────────────────────────────────────────
IF /I NOT "%~6"=="True" (
    echo [SKIP] Ranking steps skipped ^(flag = "%~6"^).
    GOTO :end
)
REM ── making 50% percentile of all ensemble members launcher ──────────────────────────────────────────────
python -m AdaptEns.make_threshold "%~1" "%~5"
REM ── calculating fractions per ens_member based on the 50% threshold ──────────────────────────────────────────────
python -m AdaptEns.compute_fraction "%~1" "%~5"
REM ── calculating fraction skill score and displacement ──────────────────────────────────────────────
python -m AdaptEns.make_fss_disp "%~1" "%~5"
REM ── calculating the mean_displacement ──────────────────────────────────────────────
python -m AdaptEns.get_mean_displacement "%~1" "%~5"
REM ── ranking the ensemble members ──────────────────────────────────────────────
python -m AdaptEns.rank_ensemble "%~1" "%~5"
REM ── deleting──────────────────────────────────────────────
python -m AdaptEns.clean_up "%~1" "%~3"

:end

IF %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Script failed with exit code %ERRORLEVEL%
    pause
) ELSE (
    echo.
    echo [DONE] Finished successfully.
    exit
)