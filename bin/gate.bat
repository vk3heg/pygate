@echo off
REM Enhanced PyGate Automation Script for Windows
REM Runs PyGate import/export cycle with robust error handling
REM Designed to be run every 30 minutes via Task Scheduler
REM

setlocal enabledelayedexpansion

REM Configuration
set "SCRIPT_DIR=%~dp0"
set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"
for %%i in ("%SCRIPT_DIR%") do set "PYGATE_DIR=%%~dpi"
set "PYGATE_DIR=%PYGATE_DIR:~0,-1%"
set "LOGFILE=%PYGATE_DIR%\data\logs\gate.log"
set "LOCKFILE=%TEMP%\pygate.lock"
set "MAX_RUNTIME=1800"
set "DEBUG=%DEBUG%"
if "%DEBUG%"=="" set "DEBUG=0"

REM Parse command line arguments
if "%1"=="--debug" set "DEBUG=1"
if "%1"=="--help" goto :show_help
if "%1"=="-h" goto :show_help
if "%1"=="/?" goto :show_help

REM Cache start date/time once at script startup for better performance
for /f "tokens=*" %%a in ('powershell -Command "Get-Date -Format 'dd-MMM-yy'"') do set "CACHED_DATE=%%a"

REM Main execution
call :log "PyGate automation started (PID: %RANDOM%%RANDOM%)"
call :rotate_logs
call :check_lock
call :preflight_checks
call :run_pygate_cycle
call :generate_stats
call :run_maintenance
call :log "PyGate automation completed successfully"
call :cleanup
exit /b 0

REM ===== Functions =====

:log
REM Use cached date and Windows native time for fast logging
set "timestamp=%CACHED_DATE% %TIME:~0,8%"
echo [%timestamp%] %~1 >> "%LOGFILE%"
echo [%timestamp%] %~1
exit /b 0

:debug
if "%DEBUG%"=="1" call :log "DEBUG: %~1"
exit /b 0

:error_exit
call :log "ERROR: %~1"
call :cleanup
exit /b 1

:cleanup
if exist "%LOCKFILE%" del /f /q "%LOCKFILE%" >nul 2>&1
call :debug "Cleanup completed"
exit /b 0

:run_with_timeout
set "cmd=%~1"
set "timeout_val=%~2"
set "desc=%~3"

call :log "Starting: %desc%"
call :debug "Command: %cmd% (timeout: %timeout_val%s)"

REM Windows doesn't have built-in timeout command for processes
REM Using start /wait for simple execution without timeout enforcement
start /wait /b cmd /c "%cmd%" >nul 2>&1
set "exit_code=!errorlevel!"

if !exit_code! equ 0 (
    call :log "Completed: %desc%"
    exit /b 0
) else (
    call :log "FAILED: %desc% (exit code: !exit_code!)"
    exit /b !exit_code!
)

:check_lock
if exist "%LOCKFILE%" (
    set /p lock_pid=<"%LOCKFILE%"
    tasklist /fi "PID eq !lock_pid!" 2>nul | find "!lock_pid!" >nul
    if !errorlevel! equ 0 (
        call :log "PyGate is already running (PID: !lock_pid!). Exiting."
        exit /b 0
    ) else (
        call :log "Stale lock file found. Removing..."
        del /f /q "%LOCKFILE%" >nul 2>&1
    )
)

REM Create lock file with random PID-like number
set "current_pid=%RANDOM%%RANDOM%"
echo !current_pid! > "%LOCKFILE%"
call :debug "Lock file created (PID: !current_pid!)"
exit /b 0

:preflight_checks
call :log "Performing pre-flight checks..."

REM Check if pygate.py exists
if not exist "%PYGATE_DIR%\pygate.py" (
    call :error_exit "pygate.py not found in %PYGATE_DIR%"
)

REM Check Python availability
python --version >nul 2>&1
if !errorlevel! neq 0 (
    call :error_exit "python not found in PATH"
)

REM Check configuration (try new location first, then old location)
if exist "%PYGATE_DIR%\pygate.cfg" (
    set "CONFIG_FILE=%PYGATE_DIR%\pygate.cfg"
    call :debug "Using config file: pygate.cfg"
) else if exist "%PYGATE_DIR%\pygate.cfg" (
    set "CONFIG_FILE=%PYGATE_DIR%\pygate.cfg"
    call :debug "Using config file: pygate.cfg)"
) else (
    call :error_exit "Configuration file not found (checked pygate.cfg)"
)

REM Check required directories
for %%d in (data\inbound data\outbound data\logs data\hold data\temp) do (
    if not exist "%PYGATE_DIR%\%%d" (
        call :debug "Creating directory: %%d"
        mkdir "%PYGATE_DIR%\%%d" 2>nul
        if !errorlevel! neq 0 (
            call :error_exit "Cannot create directory: %%d"
        )
    )
)

REM Test basic configuration (quick check)
python "%PYGATE_DIR%\pygate.py" --config "%CONFIG_FILE%" --check --dry-run >nul 2>&1
if !errorlevel! neq 0 (
    call :log "WARNING: Configuration check failed - proceeding anyway"
)

call :debug "Pre-flight checks completed"
exit /b 0

:generate_stats
set "stats_file=%PYGATE_DIR%\data\logs\gate_stats.log"

REM Count files in various directories
set "inbound_count=0"
for %%f in ("%PYGATE_DIR%\data\inbound\*.pkt") do set /a inbound_count+=1

set "outbound_count=0"
for %%f in ("%PYGATE_DIR%\data\outbound\*.pkt") do set /a outbound_count+=1

set "held_count=0"
if exist "%PYGATE_DIR%\data\hold\pending" (
    for %%f in ("%PYGATE_DIR%\data\hold\pending\*.json") do set /a held_count+=1
)

set "processed_count=0"
if exist "%PYGATE_DIR%\data\inbound\processed" (
    for %%f in ("%PYGATE_DIR%\data\inbound\processed\*.pkt") do set /a processed_count+=1
)

REM Log statistics
set "timestamp=%CACHED_DATE% %TIME:~0,8%"
echo [!timestamp!] Inbound: !inbound_count!, Outbound: !outbound_count!, Held: !held_count!, Processed(24h): !processed_count! >> "%stats_file%"

REM Rotate stats file if it gets too large (keep last 500 lines)
if exist "%stats_file%" (
    for /f %%a in ('find /c /v "" ^< "%stats_file%"') do set "line_count=%%a"
    if !line_count! gtr 1000 (
        call :debug "Rotating stats file"
        powershell -Command "Get-Content '%stats_file%' | Select-Object -Last 500 | Set-Content '%stats_file%.tmp'"
        move /y "%stats_file%.tmp" "%stats_file%" >nul 2>&1
    )
)

call :debug "Statistics: Inbound=!inbound_count!, Outbound=!outbound_count!, Held=!held_count!"
exit /b 0

:check_disk_space
set "min_free_mb=100"

REM Get available disk space in MB for the drive where PYGATE_DIR is located
for /f "tokens=3" %%a in ('dir "%PYGATE_DIR%" ^| find "bytes free"') do set "available_bytes=%%a"
set "available_bytes=%available_bytes:,=%"
set /a available_mb=available_bytes/1048576

if !available_mb! lss %min_free_mb% (
    call :log "WARNING: Low disk space: !available_mb!MB available (minimum: %min_free_mb%MB)"
    exit /b 1
)

call :debug "Disk space OK: !available_mb!MB available"
exit /b 0

:run_pygate_cycle
call :log "Starting PyGate cycle"

REM Change to PyGate directory
cd /d "%PYGATE_DIR%" || (
    call :error_exit "Cannot change to PyGate directory"
)

REM Check disk space before processing
call :check_disk_space
if !errorlevel! neq 0 call :log "WARNING: Continuing despite low disk space"

REM Import FidoNet packets
call :run_with_timeout "python pygate.py --import" 300 "Import FidoNet packets"
if !errorlevel! equ 0 (
    set "imported_files=0"
    if exist "data\inbound\processed" (
        for %%f in (data\inbound\processed\*.pkt) do set /a imported_files+=1
    )
    if !imported_files! gtr 0 call :log "Imported !imported_files! packet(s)"
) else (
    call :log "WARNING: Import phase failed - continuing with export"
)

REM Export NNTP messages
call :run_with_timeout "python pygate.py --export" 600 "Export NNTP messages"
if !errorlevel! equ 0 (
    set "exported_files=0"
    if exist "data\outbound" (
        for %%f in (data\outbound\*.pkt) do set /a exported_files+=1
    )
    if !exported_files! gtr 0 call :log "Created !exported_files! outbound packet(s)"
) else (
    call :log "WARNING: Export phase failed"
)

REM Process held messages (if any)
set "held_count=0"
if exist "data\hold\approved" (
    for %%f in (data\hold\approved\*.json) do set /a held_count+=1
)
if !held_count! gtr 0 (
    call :log "Processing !held_count! held message(s)"
    call :run_with_timeout "python pygate.py --process-held" 300 "Process held messages"
)

REM Pack outbound messages
call :run_with_timeout "python pygate.py --pack" 180 "Pack outbound messages"
if !errorlevel! neq 0 call :log "WARNING: Pack phase failed"

REM Connect to FidoNet hub with binkd to send/receive packets
if exist "%PYGATE_DIR%\bin\BINKDWIN.EXE" (
    if exist "%CONFIG_FILE%" (
        REM Extract linked_address from pygate.cfg
        for /f "tokens=2 delims==" %%a in ('findstr /r "^linked_address" "%CONFIG_FILE%"') do (
            set "linked_address=%%a"
            set "linked_address=!linked_address: =!"
        )

        if not "!linked_address!"=="" (
            set "binkd_config=%PYGATE_DIR%\config\binkd.config"
            if not exist "!binkd_config!" (
                if exist "%PYGATE_DIR%\config\binkd.config" set "binkd_config=%PYGATE_DIR%\config\binkd.config"
            )

            if exist "!binkd_config!" (
                call :log "Connecting to FidoNet hub (!linked_address!)"
                call :run_with_timeout "%PYGATE_DIR%\bin\BINKDWIN.EXE -p -P !linked_address! !binkd_config!" 300 "FidoNet hub connection (binkd)"
                if !errorlevel! neq 0 call :log "WARNING: FidoNet hub connection failed"
            ) else (
                call :log "WARNING: binkd.config not found - skipping FidoNet connection"
            )
        ) else (
            call :log "WARNING: linked_address not found in config - skipping FidoNet connection"
        )
    )
) else (
    call :log "WARNING: binkd binary not found - skipping FidoNet connection"
)

REM Areafix processing (lightweight)
call :run_with_timeout "python pygate.py --areafix" 60 "Process areafix requests"

call :log "PyGate cycle completed"
exit /b 0

:run_maintenance
REM Get current hour
set "hour=%time:~0,2%"
if "%hour:~0,1%"==" " set "hour=0%hour:~1,1%"

REM Run maintenance at 2 AM
if "%hour%"=="02" (
    call :log "Running maintenance tasks"
    call :run_with_timeout "python pygate.py --maintenance" 600 "Maintenance tasks"
    if !errorlevel! neq 0 call :log "WARNING: Maintenance failed"
)
exit /b 0

:rotate_logs
set "max_size_mb=10"

if exist "%LOGFILE%" (
    for %%a in ("%LOGFILE%") do set "size_bytes=%%~za"
    set /a size_mb=!size_bytes!/1048576
    if !size_mb! gtr %max_size_mb% (
        call :debug "Rotating log file (size: !size_mb!MB)"
        copy /y "%LOGFILE%" "%LOGFILE%.old" >nul 2>&1
        REM Use cached date for rotation (only happens rarely so performance is fine)
        set "timestamp=%CACHED_DATE% %TIME:~0,8%"
        echo [!timestamp!] Log rotated (previous log saved as gate.log.old) > "%LOGFILE%"
    )
)
exit /b 0

:show_help
echo Usage: %~nx0 [--debug] [--help]
echo Enhanced PyGate automation script for Windows
echo.
echo Options:
echo   --debug    Enable debug logging
echo   --help     Show this help message
exit /b 0
