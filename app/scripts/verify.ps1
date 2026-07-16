param(
    [switch]$SkipBackend,
    [switch]$SkipWeb,
    [switch]$SkipMobile,
    [switch]$SkipCli
)

$ErrorActionPreference = "Stop"

$AppRoot = Resolve-Path (Join-Path $PSScriptRoot "..")

function Invoke-Step {
    param(
        [string]$Name,
        [string]$Path,
        [scriptblock]$Command
    )

    Write-Host ""
    Write-Host "==> $Name" -ForegroundColor Cyan
    Push-Location $Path
    try {
        $global:LASTEXITCODE = 0
        & $Command
        if ($LASTEXITCODE -ne 0) {
            throw "$Name failed with exit code $LASTEXITCODE"
        }
    } finally {
        Pop-Location
    }
}

if (-not $SkipBackend) {
    Invoke-Step "Backend tests" (Join-Path $AppRoot "backend") {
        $env:MAVEN_OPTS = "-Xmx192m -XX:MaxMetaspaceSize=160m"
        .\mvnw.cmd test
    }
}

if (-not $SkipWeb) {
    Invoke-Step "Web build" (Join-Path $AppRoot "web") {
        npm run build
    }
}

if (-not $SkipMobile) {
    Invoke-Step "Mobile type-check and H5 build" (Join-Path $AppRoot "mobile") {
        npm run type-check
        npm run build:h5
    }
}

if (-not $SkipCli) {
    Invoke-Step "CLI build" (Join-Path $AppRoot "cli") {
        npm run build
    }
}

Write-Host ""
Write-Host "All selected checks passed." -ForegroundColor Green
