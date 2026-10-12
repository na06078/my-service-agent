param([switch]$CheckOnly)

$ErrorActionPreference = "Stop"
$Executable = "C:\llm\llama-b11429-bin-win-vulkan-x64\llama-server.exe"
$ModelPath = "C:/Users/YH/.lmstudio/models/0bserverx/Qwen3.8-27B-Heretic-Abliterated-Uncensored-GGUF/RVN-Q4_K_M-multilingual-mtp.gguf"
$McpConfig = Join-Path $PSScriptRoot "검색연결설정.json"

# 종료 전 확인한 기존 인자 순서와 값을 유지하고 MCP 설정만 마지막에 추가한다.
$ServerArguments = @(
    "-m", $ModelPath,
    "--host", "127.0.0.1", "--port", "8080",
    "-c", "131072", "--parallel", "1",
    "--reasoning-effort", "medium",
    "--temp", "0.6", "--top-p", "0.95", "--top-k", "20",
    "--spec-type", "draft-mtp", "--spec-draft-n-max", "3",
    "--alias", "Qwen 3.8 27B",
    "-ngl", "all", "-fa", "on", "-lm", "none",
    "-ctk", "bf16", "-ctv", "bf16",
    "--cache-reuse", "2048", "--cache-ram", "8192", "--cache-prompt",
    "-lv", "4", "-b", "1024", "-ub", "512", "-t", "16",
    "--prio", "2", "--slots", "--jinja", "--fit", "on",
    "--fit-target", "128", "--min-p", "0",
    "--mcp-servers-config", $McpConfig
)

foreach ($Path in @($Executable, $ModelPath, $McpConfig)) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Required file is missing: $Path"
    }
}
$Config = Get-Content -LiteralPath $McpConfig -Raw -Encoding UTF8 | ConvertFrom-Json
if (-not $Config.mcpServers.qdrant) { throw "Qdrant MCP configuration is missing." }
if (-not (Test-Path -LiteralPath $Config.mcpServers.qdrant.command -PathType Leaf)) {
    throw "The project Python environment is missing."
}
$HelpText = (& $Executable --help 2>&1 | Out-String)
if ($HelpText -notmatch "--mcp-servers-config") {
    throw "This executable does not support --mcp-servers-config."
}

$Client = New-Object System.Net.Sockets.TcpClient
try {
    $Connect = $Client.ConnectAsync("127.0.0.1", 8080)
    $Busy = $Connect.Wait(1000) -and $Client.Connected
} catch {
    $Busy = $false
} finally {
    $Client.Dispose()
}
if ($Busy) { throw "Port 8080 is already in use. This script does not stop any existing server." }

Write-Host "Executable: $Executable"
Write-Host "Model: $ModelPath"
Write-Host "MCP config: $McpConfig"
Write-Host "Arguments (JSON):"
Write-Host (ConvertTo-Json -InputObject $ServerArguments -Compress)
if ($CheckOnly) {
    Write-Host "CHECK_ONLY_PASS: required files, MCP flag, JSON configuration, port availability"
    Write-Host "No server was started and no process was stopped."
    exit 0
}

# 실제 서버 실행은 사용자가 BAT를 열었을 때만 한다. 종료·재시작 명령은 없다.
$LogDirectory = Join-Path $PSScriptRoot "실행기록"
New-Item -ItemType Directory -Path $LogDirectory -Force | Out-Null
$LogPath = Join-Path $LogDirectory ("서버로그-" + (Get-Date -Format "yyyyMMdd-HHmmss-fff") + ".txt")
Start-Transcript -LiteralPath $LogPath -NoClobber | Out-Null
$Code = 1
try {
    Write-Host "Starting the existing model with Qdrant MCP only. Built-in file/shell tools are not enabled."
    Write-Host "Open http://127.0.0.1:8080 after the model load completes."
    Write-Host "Keep this console open while using the server."
    Write-Host "Server log: $LogPath"
    & $Executable @ServerArguments
    $Code = $LASTEXITCODE
} finally {
    Stop-Transcript | Out-Null
}
exit $Code
