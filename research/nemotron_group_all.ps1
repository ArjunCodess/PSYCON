param([string]$WaitForContainer = '')
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $false
$project = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
Set-Location -LiteralPath $project
if ($WaitForContainer) { docker wait $WaitForContainer | Out-Null }
$failedModes = @()
foreach ($mode in @('offline', 'streaming-control')) {
    docker run --rm --gpus all --name "psycon-nemotron-benchmark-$mode" --env-file .env -e PYTHONPATH=/app `
        -e PSYCON_WHISPER_DEVICE=cuda -e "NEMOTRON_BENCHMARK_MODE=$mode" `
        -v "${project}:/app" -v psycon-week4_psycon_models:/opt/psycon/hf-cache `
        --entrypoint python psycon-psycon-worker:local /app/research/nemotron_group_benchmark.py 2>&1 |
        Tee-Object -FilePath "instance/group_batch/nemotron-$mode.log"
    if ($LASTEXITCODE -ne 0) { $failedModes += $mode }
}
python (Join-Path $PSScriptRoot 'nemotron_benchmark_report.py')
if ($LASTEXITCODE -ne 0) { throw 'Could not build Nemotron comparison; inference summaries remain saved' }
if ($failedModes.Count) { throw "Nemotron benchmarks failed: $($failedModes -join ', '); see saved failure summaries" }
