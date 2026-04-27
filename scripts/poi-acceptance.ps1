param(
    [string]$ApiBase = "http://localhost:5000/api",
    [string]$Destination = "Xian",
    [string]$Category = "attraction",
    [int]$Days = 2,
    [double]$Budget = 1800,
    [string[]]$Preferences = @("history", "food"),
    [string]$RecommendFocus = "money",
    [int]$Limit = 10,
    [string]$Keyword = "",

    [string]$DbHost = "localhost",
    [int]$DbPort = 3306,
    [string]$DbUser = "root",
    [string]$DbPassword = "",
    [string]$DbName = "tour_planning"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Section {
    param([string]$Title)
    Write-Host ""
    Write-Host "========== $Title ==========" -ForegroundColor Cyan
}

function Invoke-Api {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][hashtable]$Body
    )

    $url = "$ApiBase$Path"
    Write-Host "POST $url"
    $json = $Body | ConvertTo-Json -Depth 20
    return Invoke-RestMethod -Uri $url -Method Post -ContentType "application/json" -Body $json
}

function Get-MySqlAvailable {
    $cmd = Get-Command mysql -ErrorAction SilentlyContinue
    return $null -ne $cmd
}

function Invoke-Sql {
    param([Parameter(Mandatory = $true)][string]$Sql)

    $env:MYSQL_PWD = $DbPassword
    try {
        $args = @(
            "-h", $DbHost,
            "-P", "$DbPort",
            "-u", $DbUser,
            "-D", $DbName,
            "-N",
            "-e", $Sql
        )
        $output = & mysql @args 2>&1
        if ($LASTEXITCODE -ne 0) {
            throw "mysql command failed: $output"
        }
        return ($output | Out-String).Trim()
    }
    finally {
        Remove-Item Env:MYSQL_PWD -ErrorAction SilentlyContinue
    }
}

function Parse-Count {
    param([string]$Value)
    $n = 0
    if (-not [int]::TryParse(($Value | Out-String).Trim(), [ref]$n)) {
        throw "Cannot parse count from SQL result: $Value"
    }
    return $n
}

Write-Section "Request payload"
$payload = @{
    destination     = $Destination
    category        = $Category
    budget          = $Budget
    days            = $Days
    preferences     = $Preferences
    recommend_focus = $RecommendFocus
    limit           = $Limit
}
if ($Keyword -ne "") {
    $payload.keyword = $Keyword
}
$payload | ConvertTo-Json -Depth 20 | Write-Host

$mysqlAvailable = Get-MySqlAvailable
$cacheBefore = $null

if ($mysqlAvailable) {
    Write-Section "SQL checkpoint: schema"
    $tables = Invoke-Sql @"
SELECT table_name
FROM information_schema.tables
WHERE table_schema = '$DbName'
  AND table_name IN ('poi_cache', 'poi_cost_rules')
ORDER BY table_name;
"@
    Write-Host "Found tables:"
    Write-Host $tables

    if (-not ($tables -match "poi_cache")) { throw "Missing table poi_cache" }
    if (-not ($tables -match "poi_cost_rules")) { throw "Missing table poi_cost_rules" }

    $ruleCountRaw = Invoke-Sql "SELECT COUNT(*) FROM poi_cost_rules;"
    $ruleCount = Parse-Count $ruleCountRaw
    Write-Host "poi_cost_rules count: $ruleCount"
    if ($ruleCount -le 0) {
        Write-Warning "poi_cost_rules is empty. Fallback rules may not be initialized."
    }

    $cacheBeforeRaw = Invoke-Sql "SELECT COUNT(*) FROM poi_cache;"
    $cacheBefore = Parse-Count $cacheBeforeRaw
    Write-Host "poi_cache count (before): $cacheBefore"
}
else {
    Write-Warning "mysql client not found in PATH; SQL checks will be skipped."
    Write-Host "Install mysql client or run SQL section manually in Navicat/MySQL shell."
}

Write-Section "API checkpoint: /poi/recommend"
$recommend = Invoke-Api -Path "/poi/recommend" -Body $payload

if (-not $recommend.items) {
    throw "recommend response has no items"
}

$itemCount = @($recommend.items).Count
Write-Host "recommend.items count: $itemCount"

$missingEstimated = @($recommend.items | Where-Object { $null -eq $_.estimated_cost })
if ($missingEstimated.Count -gt 0) {
    throw "Found $($missingEstimated.Count) item(s) without estimated_cost"
}

Write-Host "cache_upserted: $($recommend.cache_upserted)"
Write-Host "First 3 items summary:"
$recommend.items |
    Select-Object -First 3 name, category, cost, estimated_cost, cost_source, score |
    Format-Table -AutoSize |
    Out-String |
    Write-Host

Write-Section "API checkpoint: /poi/pull (first call)"
$pull1 = Invoke-Api -Path "/poi/pull" -Body $payload
Write-Host "pull1 message: $($pull1.message)"
Write-Host "pull1 cache_upserted: $($pull1.cache_upserted)"
Write-Host "pull1 items count: $(@($pull1.items).Count)"

Write-Section "API checkpoint: /poi/pull (second call, idempotence)"
$pull2 = Invoke-Api -Path "/poi/pull" -Body $payload
Write-Host "pull2 cache_upserted: $($pull2.cache_upserted)"
Write-Host "pull2 items count: $(@($pull2.items).Count)"

if ($mysqlAvailable) {
    Write-Section "SQL checkpoint: data after API calls"
    $cacheAfterRaw = Invoke-Sql "SELECT COUNT(*) FROM poi_cache;"
    $cacheAfter = Parse-Count $cacheAfterRaw
    Write-Host "poi_cache count (after): $cacheAfter"
    Write-Host "poi_cache delta: $($cacheAfter - $cacheBefore)"

    Write-Host "Latest cached rows:"
    try {
        $latest = Invoke-Sql @"
SELECT name, category, raw_cost, estimated_cost, cost_source, updated_at
FROM poi_cache
ORDER BY updated_at DESC
LIMIT 10;
"@
        Write-Host $latest
    }
    catch {
        Write-Warning "Could not query raw_cost/estimated_cost/cost_source from poi_cache: $($_.Exception.Message)"
        Write-Host "Try DESCRIBE poi_cache; then adjust selected columns."
    }

    Write-Host "Duplicate amap_id check (should be empty):"
    try {
        $dup = Invoke-Sql @"
SELECT amap_id, COUNT(*) AS c
FROM poi_cache
GROUP BY amap_id
HAVING COUNT(*) > 1
LIMIT 10;
"@
        if ([string]::IsNullOrWhiteSpace($dup)) {
            Write-Host "No duplicate amap_id rows."
        }
        else {
            Write-Warning "Found duplicate amap_id rows:"
            Write-Host $dup
        }
    }
    catch {
        Write-Warning "Duplicate key check skipped: $($_.Exception.Message)"
    }
}

Write-Section "Acceptance result"
Write-Host "PASS conditions to verify manually:"
Write-Host "1) /poi/recommend returns items with estimated_cost"
Write-Host "2) /poi/recommend and /poi/pull report cache_upserted"
Write-Host "3) DB has poi_cache and poi_cost_rules"
Write-Host "4) Cache rows increase or are updated without duplicate key growth"
Write-Host "5) cost_source shows amap_raw or rule:* or fallback:*"
