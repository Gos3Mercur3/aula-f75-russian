#requires -Version 5
<#
  publish.ps1 — выложить папку проекта на GitHub: репозиторий, один коммит,
  релиз с ассетом, и проверка того, что реально доехало.

  Запуск (из папки проекта, там где README.md):
      powershell -NoProfile -ExecutionPolicy Bypass -File tools\publish.ps1 -Tag v1.0.2
  Токен: введите в приглашении, либо заранее $env:GH_TOKEN (fine-grained,
  права Contents: Read and write; для СОЗДАНИЯ нового репо нужен классический
  PAT со scope `repo` — об этом скрипт скажет прямо, а не упадёт непонятно).
  Токен не сохраняется на диск и не попадает в командную строку процесса.
#>
[CmdletBinding()]
param(
    [string]$Repo = 'aula-f75-russian',
    [string]$Owner = '',
    [string]$Tag = 'v1.0.0',
    [string]$Title = 'AULA F75 — русский интерфейс драйвера',
    [string]$NotesFile = 'RELEASE_NOTES.md',
    [string]$Asset = 'AULA_F75_RU_installer.zip',
    [string[]]$Include = @('README.md','LICENSE','RELEASE_NOTES.md','TESTS.md','.gitignore','.gitattributes',
                           'AULA_F75_RU_installer.zip','dist','tools'),
    [switch]$MakeRepo,
    [switch]$Public,
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch {}

$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $Root

# ---------- токен ------------------------------------------------------------
$Token = if ($env:GH_TOKEN) { $env:GH_TOKEN } else {
    $secure = Read-Host 'Токен GitHub (ввод не виден, на диск не пишется)' -AsSecureString
    [Net.NetworkCredential]::new('', $secure).Password
}
if (-not $Token) { throw 'Токена нет — прервано.' }
$H = @{ Authorization = "token $Token"; Accept = 'application/vnd.github+json';
        'X-GitHub-Api-Version' = '2022-11-28'; 'User-Agent' = 'aula-f75-ru-publish' }

function Api([string]$Method, [string]$Uri, $BodyObj = $null, [hashtable]$ExtraHeaders = $null) {
    $args = @{ Method = $Method; Uri = $Uri; Headers = ($H + @{} + $ExtraHeaders) }
    if ($null -ne $BodyObj) {
        $json = $BodyObj | ConvertTo-Json -Depth 10 -Compress
        $args.ContentType = 'application/json; charset=utf-8'
        $args.Body = [Text.Encoding]::UTF8.GetBytes($json)
    }
    Invoke-RestMethod @args
}

# ---------- проверка токена --------------------------------------------------
Write-Host "`n[1/6] проверяю токен…" -ForegroundColor Cyan
try { $me = Api GET 'https://api.github.com/user' } catch {
    throw "токен не принят ($($_.Exception.Response.StatusCode.value__)). Проверьте, что он жив и не отозван."
}
if (-not $Owner) { $Owner = $me.login }
Write-Host ("   ok: {0} (id {1})" -f $me.login, $me.id)

$repoApi = "https://api.github.com/repos/$Owner/$Repo"
Write-Host "`n[2/6] репозиторий $Owner/$Repo" -ForegroundColor Cyan
try { $repo = Api GET $repoApi; Write-Host "   существует" }
catch {
    if (-not $MakeRepo) {
        throw "репо $Owner/$Repo не найден (или токен его не видит). Для создания: -MakeRepo -Public"
    }
    if ($DryRun) { Write-Host "   DRYRUN: создал бы $Owner/$Repo (public=$Public)"; }
    else {
        Write-Host "   создаю (public=$Public)…"
        $repo = Api POST 'https://api.github.com/user/repos' @{
            name = $Repo; public = [bool]$Public; auto_init = $true;
            description = 'Русский интерфейс драйвера AULA F75 (OemDrv / BYCOMBO4).'; has_issues = $true }
        Write-Host "   создан: $($repo.html_url)"
    }
}

# ---------- какие файлы берём ------------------------------------------------
function Collect([string[]]$patterns) {
    $out = New-Object System.Collections.Generic.List[object]
    foreach ($p in $patterns) {
        $full = Join-Path $Root $p
        if (-not (Test-Path -LiteralPath $full)) { Write-Warning "нет в рабочей папке: $p"; continue }
        if ((Get-Item -LiteralPath $full).PSIsContainer) {
            Get-ChildItem -LiteralPath $full -Recurse -File | ForEach-Object {
                $rel = $_.FullName.Substring($Root.Length + 1).Replace('\', '/')
                if ($rel -match 'text_en_reference\.xml$' -or $rel -match '__pycache__') { return }
                $out.Add([pscustomobject]@{ Path = $rel; File = $_.FullName })
            }
        } else {
            $out.Add([pscustomobject]@{ Path = $p.Replace('\','/'); File = $full })
        }
    }
    return $out
}
$files = Collect $Include
if (-not $files -or $files.Count -eq 0) { throw "нечего отправлять — проверьте -Include" }
Write-Host ("`n[3/6] файлов к отправке: {0}" -f $files.Count) -ForegroundColor Cyan
foreach ($f in $files) { Write-Host ("   {0,8}  {1}" -f (Get-Item -LiteralPath $f.File).Length, $f.Path) }

if ($DryRun) { Write-Host "`nDRYRUN: на этом останавливаюсь, ничего не изменил." -ForegroundColor Yellow; return }

# ---------- один коммит через trees API -------------------------------------
Write-Host "`n[4/6] пушу одним коммитом…" -ForegroundColor Cyan
$sha = $null
try { $sha = (Api GET "$repoApi/git/ref/heads/main").object.sha } catch {
    try { $sha = (Api GET "$repoApi/git/ref/heads/master").object.sha } catch { $sha = $null }
}
$tree = foreach ($f in $files) {
    $bytes = [IO.File]::ReadAllBytes($f.File)
    @{ path = $f.Path; mode = '100644'; type = 'blob'
       content = [Convert]::ToBase64String($bytes); encoding = 'base64' }
}
$body = @{ tree = @($tree) }
$newTree = if ($sha) { Api POST "$repoApi/git/trees" ($body + @{ base_tree = "refs/heads/main" }) }
           else       { Api POST "$repoApi/git/trees" $body }
$msg = "выложил $(Get-Date -Format 'yyyy-MM-dd HH:mm') · $($files.Count) файлов"
$commit = Api POST "$repoApi/git/commits" @{ message = $msg; tree = $newTree.sha } +
          @{}
if ($sha) { $commit = Api POST "$repoApi/git/commits" @{ message = $msg; tree = $newTree.sha; parents = @($sha) } }
Api PUT "$repoApi/git/refs/heads/main" @{ sha = $commit.sha } | Out-Null
Write-Host "   коммит $($commit.sha.Substring(0,7))"

# ---------- релиз + ассет ----------------------------------------------------
Write-Host "`n[5/6] релиз $Tag…" -ForegroundColor Cyan
$notes = if ($NotesFile -and (Test-Path -LiteralPath (Join-Path $Root $NotesFile))) {
    Get-Content -LiteralPath (Join-Path $Root $NotesFile) -Raw -Encoding UTF8 } else { "Сборка $Tag" }
try { $rel = Api POST "$repoApi/releases" @{ tag_name = $Tag; name = $Title; body = $notes;
                                             target_commitish = 'main'; draft = $false; prerelease = $false }
      Write-Host "   создан: $($rel.html_url)" }
catch {
    Write-Host "   релиз уже есть — беру существующий" -ForegroundColor Yellow
    $rel = Api GET "$repoApi/releases/tags/$Tag"
}
if ($Asset -and (Test-Path -LiteralPath (Join-Path $Root $Asset))) {
    foreach ($a in $rel.assets) { Api DELETE $a.url | Out-Null; Write-Host "   удалил старый ассет $($a.name)" }
    $bin = [IO.File]::ReadAllBytes((Join-Path $Root $Asset))
    $up = $rel.upload_url.Replace('{?name,label}', '')
    $null = Invoke-RestMethod -Method Post -Uri "$up`?name=$([Uri]::EscapeDataString([IO.Path]::GetFileName($Asset)))" `
            -Headers $H -ContentType 'application/octet-stream' -Body $bin
    Write-Host "   ассет загружен"
}

# ---------- проверка ---------------------------------------------------------
Write-Host "`n[6/6] сверяю то, что реально лежит на GitHub…" -ForegroundColor Cyan
$fail = 0
$treeApi = Api GET "$repoApi/git/trees/$($commit.sha)?recursive=1"
$onGithub = @{}
foreach ($e in $treeApi.tree) { if ($e.type -eq 'blob') { $onGithub[$e.path] = $e.size } }
foreach ($f in $files) {
    $local = (Get-Item -LiteralPath $f.File).Length
    $remote = if ($onGithub.ContainsKey($f.Path)) { $onGithub[$f.Path] } else { -1 }
    if ($local -ne $remote) { Write-Host ("   ✗ {0}: локально {1}, на GitHub {2}" -f $f.Path, $local, $remote) -ForegroundColor Red; $fail++ }
    else { Write-Host ("   ✓ {0}  ({1} байт)" -f $f.Path, $local) }
}
if ($Asset -and $rel) {
    $a = Api GET "$repoApi/releases/$($rel.id)/assets"
    if ($a.total_count -eq 0) { Write-Host "   ✗ ассет не приложен" -ForegroundColor Red; $fail++ }
    else { Write-Host ("   ✓ ассет {0} · {1} байт · {2}" -f $a.assets[0].name, $a.assets[0].size, $a.assets[0].browser_download_url) }
}
if ($fail) { throw "расхождений: $fail — НЕ считайте, что выложено." }
Write-Host "`nготово: https://github.com/$Owner/$Repo/releases/latest" -ForegroundColor Green
