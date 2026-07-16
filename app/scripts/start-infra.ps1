param(
    [int]$TimeoutSeconds = 120
)

$ErrorActionPreference = "Stop"

$AppRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$DockerRoot = Join-Path $AppRoot "docker"
$ContainerName = "matrix-prp-mysql"
$deadline = (Get-Date).AddSeconds($TimeoutSeconds)

function Write-Step {
    param([string]$Message)
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Get-ContainerHealth {
    $state = (& docker inspect -f "{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{end}}" $ContainerName 2>$null)
    if ($LASTEXITCODE -ne 0 -or -not $state) {
        return "missing"
    }
    return $state.Trim()
}

Write-Step "Starting local infrastructure"
Push-Location $DockerRoot
try {
    docker compose up -d
} finally {
    Pop-Location
}

Write-Step "Waiting for MySQL to become healthy"
do {
    $health = Get-ContainerHealth
    if ($health -match "running healthy") {
        Write-Host "MySQL is healthy." -ForegroundColor Green
        Write-Host "JDBC URL: jdbc:mysql://localhost:3306/matrix_prp" -ForegroundColor Green
        exit 0
    }

    if ($health -match "exited|dead") {
        Write-Host "MySQL container is not running: $health" -ForegroundColor Red
        docker logs --tail 80 $ContainerName
        exit 1
    }

    Write-Host "Current MySQL state: $health"
    Start-Sleep -Seconds 3
} while ((Get-Date) -lt $deadline)

Write-Host "Timed out waiting for MySQL health after $TimeoutSeconds seconds." -ForegroundColor Red
docker logs --tail 80 $ContainerName
exit 1
