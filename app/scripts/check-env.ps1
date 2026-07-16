param(
    [switch]$StrictDocker
)

$ErrorActionPreference = "Stop"

$AppRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$RepoRoot = Resolve-Path (Join-Path $AppRoot "..")
$ContainerName = "matrix-prp-mysql"
$HasFailure = $false
$DockerDaemonRunning = $false

function Write-Check {
    param(
        [string]$Status,
        [string]$Message
    )

    $color = switch ($Status) {
        "OK" { "Green" }
        "WARN" { "Yellow" }
        default { "Red" }
    }
    Write-Host ("[{0}] {1}" -f $Status, $Message) -ForegroundColor $color
}

function Mark-Failure {
    param([string]$Message)
    $script:HasFailure = $true
    Write-Check "FAIL" $Message
}

function Get-CommandPath {
    param([string]$Name)
    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }
    return $null
}

function Test-RequiredCommand {
    param(
        [string]$Name,
        [string]$VersionArgument = "--version"
    )

    $path = Get-CommandPath $Name
    if (-not $path) {
        Mark-Failure "$Name is not available in PATH."
        return
    }

    $version = (& cmd /c "$Name $VersionArgument 2>&1" | Select-Object -First 1)
    Write-Check "OK" "$Name available: $version"
}

function Test-PathExists {
    param(
        [string]$Label,
        [string]$Path
    )

    if (Test-Path $Path) {
        Write-Check "OK" "$Label exists: $Path"
    } else {
        Mark-Failure "$Label is missing: $Path"
    }
}

function Test-Java {
    $path = Get-CommandPath "java"
    if (-not $path) {
        Mark-Failure "java is not available in PATH."
        return
    }

    $versionLine = (& cmd /c "java -version 2>&1" | Select-Object -First 1)
    $major = $null
    if ($versionLine -match '"(?<major>\d+)') {
        $major = [int]$Matches.major
    }

    if ($major -ge 21) {
        Write-Check "OK" "Java available: $versionLine"
    } elseif ($major) {
        Mark-Failure "Java 21+ is required by backend pom.xml, found: $versionLine"
    } else {
        Mark-Failure "Unable to parse Java version: $versionLine"
    }
}

function Test-Docker {
    $path = Get-CommandPath "docker"
    if (-not $path) {
        if ($StrictDocker) {
            Mark-Failure "docker is not available in PATH."
        } else {
            Write-Check "WARN" "docker is not available in PATH. MySQL Compose cannot be started until Docker is installed."
        }
        return
    }

    $version = (& cmd /c "docker --version 2>&1" | Select-Object -First 1)
    Write-Check "OK" "Docker client available: $version"

    & cmd /c "docker info >nul 2>nul"
    if ($LASTEXITCODE -eq 0) {
        $script:DockerDaemonRunning = $true
        Write-Check "OK" "Docker daemon is running."
    } elseif ($StrictDocker) {
        Mark-Failure "Docker daemon is not running."
    } else {
        Write-Check "WARN" "Docker daemon is not running. Start Docker Desktop before running app/docker/docker-compose.yml."
    }
}

function Test-DockerMysql {
    if (-not $DockerDaemonRunning) {
        Write-Check "WARN" "Skipping MySQL container check because Docker daemon is not running."
        return
    }

    $state = (& docker inspect -f "{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{end}}" $ContainerName 2>$null)
    if ($LASTEXITCODE -ne 0 -or -not $state) {
        Write-Check "WARN" "MySQL container '$ContainerName' is not created. Run .\app\scripts\start-infra.ps1."
        return
    }

    $state = $state.Trim()
    if ($state -match "running healthy") {
        Write-Check "OK" "MySQL container is healthy: $state"
    } elseif ($state -match "running") {
        Write-Check "WARN" "MySQL container is running but not healthy yet: $state"
    } else {
        Write-Check "WARN" "MySQL container is not running: $state. Run .\app\scripts\start-infra.ps1."
    }
}

function Test-Port {
    param(
        [int]$Port,
        [string]$Label
    )

    $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if (-not $listener) {
        Write-Check "OK" "$Label port $Port is free."
        return
    }

    $process = Get-Process -Id $listener.OwningProcess -ErrorAction SilentlyContinue
    $processName = if ($process) { $process.ProcessName } else { "unknown" }
    Write-Check "WARN" "$Label port $Port is already in use by PID $($listener.OwningProcess) ($processName)."
}

function Write-NextSteps {
    Write-Host ""
    Write-Host "Suggested next steps:" -ForegroundColor Cyan
    Write-Host "  1. .\app\scripts\start-infra.ps1"
    Write-Host "  2. .\app\scripts\start-backend.ps1"
    Write-Host "  3. .\app\scripts\smoke-api.ps1"
    Write-Host "  4. .\app\scripts\verify.ps1"
}

Write-Host "Matrix PRP local environment check" -ForegroundColor Cyan
Write-Host ""

Test-Java
Test-RequiredCommand "node"
Test-RequiredCommand "npm"
Test-RequiredCommand "git"
Test-Docker
Test-DockerMysql

Write-Host ""
Test-Port -Port 8080 -Label "Backend"
Test-Port -Port 5173 -Label "Web"

Write-Host ""
Test-PathExists "Backend Maven wrapper" (Join-Path $AppRoot "backend/mvnw.cmd")
Test-PathExists "Docker Compose file" (Join-Path $AppRoot "docker/docker-compose.yml")
Test-PathExists "MySQL schema" (Join-Path $AppRoot "docker/mysql/init/001-schema.sql")
Test-PathExists "Web env example" (Join-Path $AppRoot "web/.env.example")
Test-PathExists "Mobile env example" (Join-Path $AppRoot "mobile/.env.example")
Test-PathExists "Knowledge directory" (Join-Path $RepoRoot "knowledge")

Write-Host ""
if ($HasFailure) {
    Write-Check "FAIL" "Environment check failed."
    exit 1
}

Write-Check "OK" "Environment check passed."
Write-NextSteps
