param(
    [int]$Port = 8080,
    [switch]$StopExisting
)

$ErrorActionPreference = "Stop"

$AppRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$BackendRoot = Join-Path $AppRoot "backend"

function Get-PortProcess {
    param([int]$Port)

    Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1 |
        ForEach-Object {
            $process = Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue
            [PSCustomObject]@{
                PID = $_.OwningProcess
                ProcessName = $process.ProcessName
                Path = $process.Path
            }
        }
}

function Write-Step {
    param([string]$Message)
    Write-Host "==> $Message" -ForegroundColor Cyan
}

$existing = Get-PortProcess -Port $Port
if ($existing) {
    if (-not $StopExisting) {
        Write-Host "Port $Port is already in use." -ForegroundColor Red
        Write-Host "PID: $($existing.PID)"
        Write-Host "Process: $($existing.ProcessName)"
        Write-Host "Path: $($existing.Path)"
        Write-Host ""
        Write-Host "If this is an old Matrix PRP backend, rerun with:" -ForegroundColor Yellow
        Write-Host "  .\app\scripts\start-backend.ps1 -StopExisting"
        Write-Host ""
        Write-Host "Or choose another port:" -ForegroundColor Yellow
        Write-Host "  .\app\scripts\start-backend.ps1 -Port 18080"
        exit 1
    }

    Write-Step "Stopping process on port $Port"
    Stop-Process -Id $existing.PID -Force
    Start-Sleep -Seconds 2
}

Write-Step "Starting backend on port $Port"
Push-Location $BackendRoot
try {
    $env:MAVEN_OPTS = "-Xmx192m -XX:MaxMetaspaceSize=160m"
    .\mvnw.cmd spring-boot:run `
        "-Dspring-boot.run.jvmArguments=-Xmx160m -XX:MaxMetaspaceSize=160m" `
        "-Dspring-boot.run.arguments=--server.port=$Port"
} finally {
    Pop-Location
}
