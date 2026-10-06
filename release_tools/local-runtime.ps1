param(
    [ValidateSet('services','ollama','web','worker','configure','test','protocol-test')]
    [string]$Action = 'web'
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$runtimeRoot = Join-Path $projectRoot '.runtime'
$pythonExe = Join-Path $runtimeRoot 'venv\Scripts\python.exe'
$ollamaExe = Join-Path $runtimeRoot 'ollama\ollama.exe'
if (!(Test-Path $pythonExe) -or !(Test-Path $ollamaExe)) {
    throw 'Install the project-local runtime first; see docs/COMMUNICATION_COACH.md.'
}
Set-Location $projectRoot
$env:HF_HOME = Join-Path $runtimeRoot 'models\huggingface'
$env:TORCH_HOME = Join-Path $runtimeRoot 'models\torch'
$env:OLLAMA_MODELS = Join-Path $runtimeRoot 'models\ollama'
$env:OLLAMA_HOST = '127.0.0.1:11434'
$env:OLLAMA_KEEP_ALIVE = '0'
$env:OLLAMA_NO_CLOUD = '1'
$env:TEMP = Join-Path $runtimeRoot 'tmp'
$env:TMP = $env:TEMP
$env:PATH = (Join-Path $runtimeRoot 'bin')+';'+(Join-Path $runtimeRoot 'node')+';'+(Join-Path $runtimeRoot 'venv\Scripts')+';'+(Join-Path $runtimeRoot 'venv\Lib\site-packages\torch\lib')+';'+$env:PATH
$env:UV_CACHE_DIR = Join-Path $runtimeRoot 'cache\uv'
$env:NPM_CONFIG_CACHE = Join-Path $runtimeRoot 'cache\npm'
$env:PSYCON_DATABASE_URL = 'postgresql://psycon:psycon@127.0.0.1:5432/psycon'
$env:PSYCON_S3_ENDPOINT_URL = 'http://127.0.0.1:9000'
$env:PSYCON_S3_SECRET_KEY = 'psycon-local-object-secret'
$env:PSYCON_DIARIZATION_DEVICE = 'cuda'
$env:PSYCON_SPEAKER_DEVICE = 'cuda'
$env:PSYCON_WHISPER_DEVICE = 'cuda'
switch ($Action) {
    'services' { docker compose -f docker-compose.yml -f docker-compose.local.yml up -d postgres minio }
    'ollama' {
        $listener = Get-NetTCPConnection -LocalPort 11434 -State Listen -ErrorAction SilentlyContinue
        if ($listener) {
            $process = Get-CimInstance Win32_Process -Filter ("ProcessId = "+$listener[0].OwningProcess)
            if ($process.ExecutablePath -eq $ollamaExe) { return }
            throw 'Port 11434 is owned by another runtime. Stop that runtime before starting this one.'
        }
        Start-Process -FilePath $ollamaExe -ArgumentList 'serve' -WorkingDirectory $projectRoot -WindowStyle Hidden `
            -RedirectStandardOutput (Join-Path $runtimeRoot 'logs\ollama-stdout.log') `
            -RedirectStandardError (Join-Path $runtimeRoot 'logs\ollama-stderr.log')
    }
    'web' { & $pythonExe -m backend.communication.runtime web }
    'worker' { & $pythonExe -m backend.communication.runtime worker }
    'configure' { & $pythonExe -m backend.communication.runtime configure-local }
    'test' { & $pythonExe -m pytest tests -p no:cacheprovider --basetemp (Join-Path $runtimeRoot 'tmp\pytest') }
    'protocol-test' { & (Join-Path $runtimeRoot 'node\node.exe') (Join-Path $runtimeRoot 'node\npm\bin\npm-cli.js') --prefix protocol test }
}
if ($LASTEXITCODE -and $LASTEXITCODE -ne 0) { throw "Runtime command failed: $Action" }
