param(
    [string]$ApiBaseUrl = "http://localhost:8080/api",
    [string]$Username = "admin",
    [string]$Password = "matrix-prp"
)

$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Assert-SuccessResponse {
    param(
        [object]$Response,
        [string]$Name
    )

    if ($Response.code -ne "SUCCESS") {
        throw "$Name returned unexpected code: $($Response.code)"
    }
    if ($Response.message -ne "OK") {
        throw "$Name returned unexpected message: $($Response.message)"
    }
}

function Invoke-Api {
    param(
        [string]$Method,
        [string]$Path,
        [object]$Body = $null,
        [string]$Token = $null
    )

    $headers = @{}
    if ($Token) {
        $headers.Authorization = "Bearer $Token"
    }

    $parameters = @{
        Method = $Method
        Uri = "$ApiBaseUrl$Path"
        Headers = $headers
    }

    if ($null -ne $Body) {
        $parameters.ContentType = "application/json"
        $parameters.Body = ($Body | ConvertTo-Json -Depth 10)
    }

    Invoke-RestMethod @parameters
}

function Invoke-SmokeCleanup {
    param(
        [string]$Token,
        [long]$AccountId,
        [long]$CategoryId
    )

    if (-not $Token) {
        return
    }

    if ($CategoryId -gt 0) {
        try {
            $null = Invoke-Api -Method "DELETE" -Path "/finance/categories/$CategoryId" -Token $Token
            Write-Host "Cleaned up finance category #$CategoryId" -ForegroundColor Yellow
        } catch {
            Write-Host "Could not clean up finance category #${CategoryId}: $($_.Exception.Message)" -ForegroundColor Yellow
        }
    }

    if ($AccountId -gt 0) {
        try {
            $null = Invoke-Api -Method "DELETE" -Path "/finance/accounts/$AccountId" -Token $Token
            Write-Host "Cleaned up finance account #$AccountId" -ForegroundColor Yellow
        } catch {
            Write-Host "Could not clean up finance account #${AccountId}: $($_.Exception.Message)" -ForegroundColor Yellow
        }
    }
}

Write-Host "Matrix PRP API smoke test" -ForegroundColor Cyan
Write-Host "API base URL: $ApiBaseUrl"
Write-Host ""

$token = $null
$accountId = 0
$categoryId = 0

try {
    Write-Step "Checking health"
    $health = Invoke-Api -Method "GET" -Path "/health"
    Assert-SuccessResponse $health "Health"
    if ($health.data.status -ne "UP") {
        throw "Health status is not UP: $($health.data.status)"
    }
    if ($health.data.version -ne "0.1.0") {
        throw "Unexpected backend version: $($health.data.version)"
    }
    if ($health.data.apiContract -ne "phase-1-runtime-api") {
        throw "Unexpected API contract: $($health.data.apiContract)"
    }
    Write-Host "Health: $($health.data.service) $($health.data.version) $($health.data.status)" -ForegroundColor Green

    Write-Step "Checking runtime health"
    $runtime = Invoke-Api -Method "GET" -Path "/health/runtime"
    Assert-SuccessResponse $runtime "Runtime health"
    if ($runtime.data.status -ne "UP") {
        throw "Runtime status is not UP: $($runtime.data.status)"
    }
    if ($runtime.data.persistence -ne "mysql") {
        throw "Runtime persistence is not mysql: $($runtime.data.persistence)"
    }
    if ($runtime.data.database -ne "UP") {
        throw "Database status is not UP: $($runtime.data.database)"
    }
    if (-not $runtime.data.knowledgeAvailable) {
        throw "Knowledge root is not available: $($runtime.data.knowledgeRoot)"
    }
    Write-Host "Runtime: $($runtime.data.persistence), database $($runtime.data.database), knowledge ready" -ForegroundColor Green

    Write-Step "Logging in"
    $login = Invoke-Api -Method "POST" -Path "/auth/login" -Body @{
        username = $Username
        password = $Password
    }
    Assert-SuccessResponse $login "Login"
    $token = $login.data.token
    if (-not $token) {
        throw "Login did not return a token."
    }
    Write-Host "Logged in as $($login.data.user.username)." -ForegroundColor Green

    Write-Step "Checking current user"
    $me = Invoke-Api -Method "GET" -Path "/users/me" -Token $token
    Assert-SuccessResponse $me "Current user"
    if ($me.data.username -ne $Username) {
        throw "Current user mismatch: $($me.data.username)"
    }
    Write-Host "Current user: $($me.data.displayName)" -ForegroundColor Green

    Write-Step "Checking dashboard"
    $dashboard = Invoke-Api -Method "GET" -Path "/dashboard/summary" -Token $token
    Assert-SuccessResponse $dashboard "Dashboard"
    if ($null -eq $dashboard.data.date) {
        throw "Dashboard did not return date."
    }
    Write-Host "Dashboard date: $($dashboard.data.date)" -ForegroundColor Green

    Write-Step "Checking task summary"
    $taskSummary = Invoke-Api -Method "GET" -Path "/tasks/summary" -Token $token
    Assert-SuccessResponse $taskSummary "Task summary"
    if ($null -eq $taskSummary.data.openCount) {
        throw "Task summary did not return openCount."
    }
    if ($null -eq $taskSummary.data.statusCounts) {
        throw "Task summary did not return statusCounts."
    }
    Write-Host "Task summary: open $($taskSummary.data.openCount), overdue $($taskSummary.data.overdueCount)" -ForegroundColor Green

    $stamp = Get-Date -Format "yyyyMMddHHmmss"

    Write-Step "Checking finance account CRUD"
    $accountName = "smoke-account-$stamp"
    $account = Invoke-Api -Method "POST" -Path "/finance/accounts" -Token $token -Body @{
        name = $accountName
        type = "cash"
        currency = "CNY"
        openingBalance = 12.34
        note = "smoke account"
    }
    Assert-SuccessResponse $account "Create finance account"
    if ($account.data.name -ne $accountName) {
        throw "Created finance account name mismatch: $($account.data.name)"
    }
    $accountId = $account.data.id
    $accounts = Invoke-Api -Method "GET" -Path "/finance/accounts" -Token $token
    Assert-SuccessResponse $accounts "List finance accounts"
    if (@($accounts.data | Where-Object { $_.id -eq $accountId }).Count -ne 1) {
        throw "Created finance account was not listed: $accountId"
    }
    $updatedAccount = Invoke-Api -Method "PUT" -Path "/finance/accounts/$accountId" -Token $token -Body @{
        name = "$accountName-updated"
        type = "bank"
        currency = "CNY"
        openingBalance = 56.78
        note = "updated smoke account"
    }
    Assert-SuccessResponse $updatedAccount "Update finance account"
    if ($updatedAccount.data.type -ne "bank") {
        throw "Finance account update did not persist type: $($updatedAccount.data.type)"
    }
    Write-Host "Finance account CRUD: #$accountId" -ForegroundColor Green

    Write-Step "Checking finance category CRUD"
    $categoryName = "smoke-category-$stamp"
    $category = Invoke-Api -Method "POST" -Path "/finance/categories" -Token $token -Body @{
        name = $categoryName
        type = "expense"
        color = "#0f766e"
        note = "smoke category"
    }
    Assert-SuccessResponse $category "Create finance category"
    if ($category.data.name -ne $categoryName) {
        throw "Created finance category name mismatch: $($category.data.name)"
    }
    $categoryId = $category.data.id
    $categories = Invoke-Api -Method "GET" -Path "/finance/categories?type=expense" -Token $token
    Assert-SuccessResponse $categories "List finance categories"
    if (@($categories.data | Where-Object { $_.id -eq $categoryId }).Count -ne 1) {
        throw "Created finance category was not listed: $categoryId"
    }
    $updatedCategory = Invoke-Api -Method "PUT" -Path "/finance/categories/$categoryId" -Token $token -Body @{
        name = "$categoryName-updated"
        type = "income"
        color = "#2563eb"
        note = "updated smoke category"
    }
    Assert-SuccessResponse $updatedCategory "Update finance category"
    if ($updatedCategory.data.type -ne "income") {
        throw "Finance category update did not persist type: $($updatedCategory.data.type)"
    }
    Write-Host "Finance category CRUD: #$categoryId" -ForegroundColor Green

    Write-Step "Cleaning up smoke finance config"
    $deleteCategory = Invoke-Api -Method "DELETE" -Path "/finance/categories/$categoryId" -Token $token
    Assert-SuccessResponse $deleteCategory "Delete finance category"
    $categoryId = 0
    $deleteAccount = Invoke-Api -Method "DELETE" -Path "/finance/accounts/$accountId" -Token $token
    Assert-SuccessResponse $deleteAccount "Delete finance account"
    $accountId = 0
    Write-Host "Smoke finance config cleaned up." -ForegroundColor Green

    Write-Step "Checking finance account summary"
    $accountSummary = Invoke-Api -Method "GET" -Path "/finance/summary/monthly/accounts" -Token $token
    Assert-SuccessResponse $accountSummary "Finance account summary"
    if ($null -eq $accountSummary.data) {
        throw "Finance account summary did not return data."
    }
    Write-Host "Finance account summary rows: $(@($accountSummary.data).Count)" -ForegroundColor Green

    Write-Step "Checking knowledge stats"
    $knowledgeStats = Invoke-Api -Method "GET" -Path "/knowledge/stats" -Token $token
    Assert-SuccessResponse $knowledgeStats "Knowledge stats"
    if ($null -eq $knowledgeStats.data.fileCount) {
        throw "Knowledge stats did not return fileCount."
    }
    Write-Host "Knowledge stats: $($knowledgeStats.data.fileCount) files, $($knowledgeStats.data.directoryCount) directories" -ForegroundColor Green

    Write-Step "Checking feature modules"
    $modules = Invoke-Api -Method "GET" -Path "/modules/features" -Token $token
    Assert-SuccessResponse $modules "Feature modules"
    $moduleCodes = @($modules.data | ForEach-Object { $_.code })
    foreach ($required in @("records", "tasks", "finance", "reviews", "knowledge")) {
        if ($moduleCodes -notcontains $required) {
            throw "Missing feature module: $required"
        }
    }
    Write-Host "Feature modules: $($moduleCodes -join ', ')" -ForegroundColor Green

    Write-Host ""
    Write-Host "API smoke test passed." -ForegroundColor Green
} catch {
    Write-Host ""
    Write-Host "API smoke test failed: $($_.Exception.Message)" -ForegroundColor Red
    Invoke-SmokeCleanup -Token $token -AccountId $accountId -CategoryId $categoryId
    Write-Host "Make sure MySQL and backend are running, then retry:" -ForegroundColor Yellow
    Write-Host "  .\app\scripts\start-infra.ps1"
    Write-Host "  cd app\backend; .\mvnw.cmd spring-boot:run"
    exit 1
}
