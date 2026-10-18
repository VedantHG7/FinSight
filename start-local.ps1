param([string]$PythonPath = '')
$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$backendPath = Join-Path $projectRoot 'backend'
$frontendPath = Join-Path $projectRoot 'frontend'
$logPath = Join-Path $projectRoot 'output/services'
New-Item -ItemType Directory -Force -Path $logPath | Out-Null
if (-not $PythonPath) {
    $installedPython = Get-ItemProperty 'HKCU:/Software/Python/PythonCore/3.13/InstallPath' -ErrorAction SilentlyContinue
    if ($installedPython) { $PythonPath = $installedPython.ExecutablePath }
    else { $PythonPath = (Get-Command python -ErrorAction Stop).Source }
}
# The HTTP health endpoint alone cannot verify native ML dependencies.
Push-Location $backendPath
try {
    & $PythonPath -m app.check_runtime
    if ($LASTEXITCODE -ne 0) { throw 'ML runtime check failed. Resolve the reported dependency error before starting FinSight.' }
} finally { Pop-Location }
function Test-FinSightApi {
    try { return (Invoke-RestMethod 'http://127.0.0.1:8000/api/health' -TimeoutSec 2).service -eq 'FinSight API' }
    catch { return $false }
}
if (-not (Test-FinSightApi)) {
    $apiProcess = Start-Process -FilePath $PythonPath -ArgumentList '-m','uvicorn','main:app','--host','127.0.0.1','--port','8000' -WorkingDirectory $backendPath -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logPath 'api.log') -RedirectStandardError (Join-Path $logPath 'api-error.log')
    for ($attempt=0; $attempt -lt 20; $attempt++) {
        if (Test-FinSightApi) { break }
        if ($apiProcess.HasExited) { throw "API exited. Check output/services/api-error.log." }
        Start-Sleep -Seconds 1
    }
    if (-not (Test-FinSightApi)) { throw 'API did not become ready. Check PostgreSQL and output/services/api-error.log.' }
}
# PostgreSQL's advisory lock ensures a second worker cannot process the same queue concurrently.
$workerPidFile = Join-Path $logPath 'worker.pid'
$existingWorker = $null
if (Test-Path $workerPidFile) {
    $storedWorkerId = Get-Content $workerPidFile
    $existingWorker = Get-CimInstance Win32_Process -Filter "ProcessId=$storedWorkerId" -ErrorAction SilentlyContinue
    if ($existingWorker -and $existingWorker.CommandLine -notmatch '-m app\.worker') { $existingWorker = $null }
}
if (-not $existingWorker) {
    $worker = Start-Process -FilePath $PythonPath -ArgumentList '-m','app.worker' -WorkingDirectory $backendPath -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logPath 'worker.log') -RedirectStandardError (Join-Path $logPath 'worker-error.log')
    Set-Content -Path $workerPidFile -Value $worker.Id
}
$frontendReady = $false
try { $frontendReady = (Invoke-WebRequest 'http://127.0.0.1:5173/' -TimeoutSec 2).StatusCode -eq 200 } catch {}
if (-not $frontendReady) {
    $nodePath = (Get-Command node -ErrorAction Stop).Source
    Start-Process -FilePath $nodePath -ArgumentList 'node_modules/vite/bin/vite.js','--host','127.0.0.1','--port','5173','--strictPort' -WorkingDirectory $frontendPath -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logPath 'frontend.log') -RedirectStandardError (Join-Path $logPath 'frontend-error.log') | Out-Null
}
Write-Output 'FinSight: http://127.0.0.1:5173/app. Service logs: output/services.'
