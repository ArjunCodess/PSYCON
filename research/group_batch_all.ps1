$ErrorActionPreference = 'Continue'
$project = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
Set-Location -LiteralPath $project
$inventory = Get-Content -LiteralPath 'instance/group_batch/inventory.json' -Raw | ConvertFrom-Json
foreach ($item in $inventory) {
    $stem = [IO.Path]::GetFileNameWithoutExtension($item.file)
    foreach ($method in @('existing', 'nvidia', 'psycon')) {
        $summary = Join-Path (Join-Path 'instance/group_batch' $stem) "$method-summary.json"
        if (Test-Path -LiteralPath $summary) {
            try {
                $saved = Get-Content -LiteralPath $summary -Raw | ConvertFrom-Json
                if ($saved.status -eq 'complete') {
                    Write-Output "SKIP $($item.file) $method completed"
                    continue
                }
            } catch { }
        }
        Write-Output "START $($item.file) $method"
        docker run --rm --gpus all --env-file .env -e PYTHONPATH=/app `
            -e PSYCON_DIARIZATION_DEVICE=cuda -e PSYCON_SPEAKER_DEVICE=cuda `
            -e PSYCON_WHISPER_DEVICE=cuda -e "GROUP_BATCH_FILE=$($item.file)" `
            -e "GROUP_BATCH_METHOD=$method" -v "${project}:/app" `
            -v psycon-week4_psycon_models:/opt/psycon/hf-cache `
            --entrypoint python psycon-psycon-worker:local /app/research/group_batch_run.py 2>&1 |
            Tee-Object -FilePath (Join-Path 'instance/group_batch' "$stem-$method.log")
        Write-Output "EXIT $($item.file) $method $LASTEXITCODE"
    }
}
