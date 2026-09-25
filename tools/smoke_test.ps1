# Smoke test of the packaged app in dist\StrikeWorks, isolated from the real
# user profile (settings go to a temporary folder):
#   1. the app starts and is still running after 25 s
#   2. the prediction worker runs the shipped models on a dataset
#   3. (optional) the training worker's final stage runs a train_config.json
#
# Usage (from the repo root):
#   powershell -File tools\smoke_test.ps1 -Dataset input_data\<dataset>.csv
#   powershell -File tools\smoke_test.ps1 -Dataset ... -TrainConfig <run>\train_config.json
param(
    [Parameter(Mandatory = $true)][string]$Dataset,
    [string]$TrainConfig = ""
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$dist = Join-Path $root "dist\StrikeWorks"
$exe = Join-Path $dist "StrikeWorks.exe"
$work = Join-Path ([System.IO.Path]::GetTempPath()) ("strikeworks_smoke_" + [guid]::NewGuid().ToString("N").Substring(0, 8))
New-Item -ItemType Directory -Force $work | Out-Null
$failed = $false

"1. App start (offscreen, 25 s)"
$psi = New-Object System.Diagnostics.ProcessStartInfo $exe
$psi.UseShellExecute = $false
$psi.EnvironmentVariables["QT_QPA_PLATFORM"] = "offscreen"
$psi.EnvironmentVariables["USERPROFILE"] = $work
$psi.EnvironmentVariables["HOME"] = $work
$app = [System.Diagnostics.Process]::Start($psi)
Start-Sleep -Seconds 25
if ($app.HasExited) { "   FAIL - exited with code $($app.ExitCode)"; $failed = $true }
else { "   OK"; $app.Kill(); $app.WaitForExit() }

"2. Prediction worker"
$models = Join-Path $dist "models"
$out = Join-Path $work "predict"
New-Item -ItemType Directory -Force $out | Out-Null
$args_ = @("--worker", "predict",
    "--bin-model", "`"$(Join-Path $models 'binary1.joblib')`"",
    "--bin-metrics", "`"$(Join-Path $models 'binary1performance_metrics.json')`"",
    "--mc-model", "`"$(Join-Path $models 'multiclass1.joblib')`"",
    "--mc-metrics", "`"$(Join-Path $models 'multiclass1performance_metrics.json')`"",
    "--data", "`"$((Resolve-Path $Dataset).Path)`"", "--out", "`"$out`"")
$w = Start-Process -FilePath $exe -ArgumentList $args_ -Wait -PassThru -NoNewWindow `
    -RedirectStandardOutput (Join-Path $work "predict_out.txt") `
    -RedirectStandardError (Join-Path $work "predict_err.txt")
if ($w.ExitCode -eq 0 -and (Test-Path (Join-Path $out "predictions.csv"))) { "   OK" }
else { "   FAIL - exit $($w.ExitCode)"; Get-Content (Join-Path $work "predict_err.txt") -Tail 5; $failed = $true }

if ($TrainConfig) {
    "3. Training worker (final stage)"
    $t = Start-Process -FilePath $exe -ArgumentList @("--worker", "train", "--config",
        "`"$((Resolve-Path $TrainConfig).Path)`"", "--stage", "final") -Wait -PassThru -NoNewWindow `
        -RedirectStandardOutput (Join-Path $work "train_out.txt") `
        -RedirectStandardError (Join-Path $work "train_err.txt")
    if ($t.ExitCode -eq 0) { "   OK" }
    else { "   FAIL - exit $($t.ExitCode)"; Get-Content (Join-Path $work "train_err.txt") -Tail 5; $failed = $true }
}

Remove-Item $work -Recurse -Force -ErrorAction SilentlyContinue
if ($failed) { exit 1 }
"All checks passed."
