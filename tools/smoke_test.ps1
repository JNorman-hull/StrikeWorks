# Smoke test of the packaged app in dist\StrikeWorks. Settings go to a
# temporary file, so nothing in dist\StrikeWorks or the user profile changes:
#   1. the app starts and is still running after 25 s
#   2. the prediction worker runs the default models on a dataset (by
#      default the example dataset shipped in input_data)
#   3. (optional) the training worker's final stage runs a train_config.json
#   4. (-Demos) on a copy of the whole folder, as a colleague would get it:
#      the Simple demo, then the Advanced demo, from the demo pack's raw
#      files to the reports - using only the copy's own folders
#   -Simple tests the Simple edition (dist\StrikeWorks_Simple) instead: its
#      demos are Simple only, and it must refuse the Advanced demo even when
#      the environment asks for the full edition
#
# Usage (from the repo root):
#   powershell -File tools\smoke_test.ps1
#   powershell -File tools\smoke_test.ps1 -Demos
#   powershell -File tools\smoke_test.ps1 -Simple -Demos
#   powershell -File tools\smoke_test.ps1 -Dataset <dataset.csv> -TrainConfig <run>\train_config.json
param(
    [string]$Dataset = "",
    [string]$TrainConfig = "",
    [switch]$Demos,
    [switch]$Simple
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$dist = Join-Path $root $(if ($Simple) { "dist\StrikeWorks_Simple" } else { "dist\StrikeWorks" })
$exe = Join-Path $dist "StrikeWorks.exe"
if (-not $Dataset) { $Dataset = Join-Path $dist "input_data\Pumpflow_2024_datatset1_only.csv" }
$work = Join-Path ([System.IO.Path]::GetTempPath()) ("strikeworks_smoke_" + [guid]::NewGuid().ToString("N").Substring(0, 8))
New-Item -ItemType Directory -Force $work | Out-Null
$failed = $false

function Start-App($path, $arguments, $settingsFile, $edition = "") {
    $psi = New-Object System.Diagnostics.ProcessStartInfo $path
    $psi.Arguments = $arguments
    $psi.UseShellExecute = $false
    $psi.EnvironmentVariables["QT_QPA_PLATFORM"] = "offscreen"
    if ($settingsFile) { $psi.EnvironmentVariables["STRIKEWORKS_SETTINGS"] = $settingsFile }
    else { $psi.EnvironmentVariables.Remove("STRIKEWORKS_SETTINGS") }
    if ($edition) { $psi.EnvironmentVariables["STRIKEWORKS_EDITION"] = $edition }
    else { $psi.EnvironmentVariables.Remove("STRIKEWORKS_EDITION") }
    return [System.Diagnostics.Process]::Start($psi)
}

"1. App start (offscreen, 25 s)"
$app = Start-App $exe "" (Join-Path $work "settings.json")
Start-Sleep -Seconds 25
if ($app.HasExited) { "   FAIL - exited with code $($app.ExitCode)"; $failed = $true }
else { "   OK"; $app.Kill(); $app.WaitForExit() }

"2. Prediction worker ($(Split-Path -Leaf $Dataset))"
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

if ($Simple) {
    "3b. Simple edition lock (the Advanced demo, asking for the full edition)"
    $env:STRIKEWORKS_EDITION = "full"
    $env:STRIKEWORKS_SETTINGS = Join-Path $work "settings.json"
    $env:QT_QPA_PLATFORM = "offscreen"
    $lock = Start-Process -FilePath $exe -ArgumentList @("--demo", "advanced") -Wait -PassThru `
        -NoNewWindow -RedirectStandardError (Join-Path $work "lock_err.txt")
    Remove-Item Env:STRIKEWORKS_EDITION, Env:STRIKEWORKS_SETTINGS, Env:QT_QPA_PLATFORM
    if ($lock.ExitCode -eq 2) { "   OK - refused: $(Get-Content (Join-Path $work 'lock_err.txt'))" }
    else { "   FAIL - exit $($lock.ExitCode) (expected 2, refused)"; $failed = $true }
}

if ($Demos) {
    "4. Demos on a fresh copy of the folder"
    $copy = Join-Path $work "StrikeWorks"
    robocopy $dist $copy /E /NFL /NDL /NJH /NJS /NP | Out-Null
    $copyExe = Join-Path $copy "StrikeWorks.exe"
    $reports = Join-Path $copy "libraries\StrikeWorks_demo\StrikeWorks_user_output"
    $modes = if ($Simple) { @("simple") } else { @("simple", "advanced") }
    foreach ($mode in $modes) {
        $log = Join-Path $work "demo_$mode.log"
        $start = Get-Date
        # no STRIKEWORKS_SETTINGS: the copy uses its own settings.json
        $p = Start-App $copyExe "--demo $mode --log `"$log`"" ""
        $p.WaitForExit()
        $secs = [int]((Get-Date) - $start).TotalSeconds
        if ($p.ExitCode -eq 0) { "   $mode demo OK ($secs s)" }
        else { "   $mode demo FAIL - exit $($p.ExitCode)"; Get-Content $log -Tail 15; $failed = $true }
    }
    "   Reports written:"
    Get-ChildItem $reports -Recurse -Filter report.html -ErrorAction SilentlyContinue |
        ForEach-Object { "     " + $_.FullName.Substring($copy.Length + 1) }
    "   Folders the copy wrote to (all inside it):"
    Get-ChildItem $copy -Directory | Where-Object { $_.Name -ne "_internal" } |
        ForEach-Object { "     " + $_.Name }
}

if ($failed) { "Kept for inspection: $work"; exit 1 }
Remove-Item $work -Recurse -Force -ErrorAction SilentlyContinue
"All checks passed."
