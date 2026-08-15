<#
.SYNOPSIS
    Publishes the NER Knowledge Transfer pages in .\wiki\ to an Azure DevOps project wiki.

.DESCRIPTION
    Clones the ADO wiki Git repo, copies the pages and .attachments into it, MERGES the root
    .order file instead of overwriting it, and creates a commit. Nothing is pushed unless you
    pass -Push, so you can review the diff first.

.EXAMPLE
    .\publish-to-ado-wiki.ps1 -WikiRepoUrl "https://dev.azure.com/celanese/MyProject/_git/MyProject.wiki"

.EXAMPLE
    .\publish-to-ado-wiki.ps1 -WikiRepoUrl "https://..." -Push
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string] $WikiRepoUrl,

    # Sub-folder inside the wiki to publish into. "" = wiki root (default).
    # Example: "Engineering" nests the section under an existing "Engineering" page.
    [string] $TargetFolder = "",

    [string] $WorkDir = (Join-Path $env:TEMP "ado-wiki-publish"),

    [string] $Message = "Add NER Knowledge Transfer KT section",

    [switch] $Push
)

$ErrorActionPreference = "Stop"

$srcRoot   = Join-Path $PSScriptRoot "wiki"
$parent    = "NER-Knowledge-Transfer"

if (-not (Test-Path $srcRoot)) { throw "Source folder not found: $srcRoot" }
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw "git is not on PATH." }

# ---------- 1. clone ----------
$repoName = ($WikiRepoUrl -split '/')[-1]
$clone    = Join-Path $WorkDir $repoName

if (Test-Path $clone) {
    Write-Host "Reusing existing clone: $clone" -ForegroundColor Cyan
    git -C $clone fetch --all
    git -C $clone pull --ff-only
} else {
    New-Item -ItemType Directory -Force -Path $WorkDir | Out-Null
    Write-Host "Cloning $WikiRepoUrl ..." -ForegroundColor Cyan
    git clone $WikiRepoUrl $clone
    if ($LASTEXITCODE -ne 0) { throw "git clone failed. Check the URL and your credentials." }
}

# ---------- 2. work out destinations ----------
$dest = if ([string]::IsNullOrWhiteSpace($TargetFolder)) { $clone } else { Join-Path $clone $TargetFolder }
New-Item -ItemType Directory -Force -Path $dest | Out-Null

# .attachments ALWAYS lives at the wiki root, regardless of where the pages go
$attSrc  = Join-Path $srcRoot ".attachments"
$attDest = Join-Path $clone ".attachments"
New-Item -ItemType Directory -Force -Path $attDest | Out-Null

# ---------- 3. copy pages ----------
Write-Host "Copying pages -> $dest" -ForegroundColor Cyan
Copy-Item -Path (Join-Path $srcRoot "$parent.md") -Destination $dest -Force
Copy-Item -Path (Join-Path $srcRoot $parent)      -Destination $dest -Recurse -Force

Write-Host "Copying attachments -> $attDest" -ForegroundColor Cyan
Copy-Item -Path (Join-Path $attSrc "*.png") -Destination $attDest -Force

# ---------- 4. merge .order (never overwrite) ----------
$orderFile = Join-Path $dest ".order"
if (Test-Path $orderFile) {
    $lines = @(Get-Content $orderFile | Where-Object { $_.Trim() -ne "" })
    if ($lines -contains $parent) {
        Write-Host ".order already lists '$parent' - left unchanged." -ForegroundColor Yellow
    } else {
        $lines += $parent
        Set-Content -Path $orderFile -Value $lines -Encoding utf8
        Write-Host "Appended '$parent' to existing .order" -ForegroundColor Green
    }
} else {
    Set-Content -Path $orderFile -Value $parent -Encoding utf8
    Write-Host "Created .order with '$parent'" -ForegroundColor Green
}

# ---------- 5. commit ----------
git -C $clone add -A
git -C $clone -c core.pager=cat status --short

$staged = git -C $clone diff --cached --name-only
if (-not $staged) {
    Write-Host "`nNothing changed - wiki is already up to date." -ForegroundColor Yellow
    return
}

git -C $clone commit -m $Message
if ($LASTEXITCODE -ne 0) { throw "git commit failed." }

# ---------- 6. push ----------
if ($Push) {
    git -C $clone push
    if ($LASTEXITCODE -ne 0) { throw "git push failed." }
    Write-Host "`nPublished. Open the wiki to see the 'NER Knowledge Transfer' section." -ForegroundColor Green
} else {
    Write-Host "`nCommit created but NOT pushed (dry run)." -ForegroundColor Yellow
    Write-Host "Review it:  git -C `"$clone`" show --stat"
    Write-Host "Publish it: git -C `"$clone`" push"
}
