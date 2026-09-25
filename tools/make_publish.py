#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Генерирует `tools/publish.ps1` (Windows, двойной клик через publish.bat)
и `tools/publish.sh` (Linux/macOS). Оба делают одно и то же и оба обращаются
к GitHub REST API напрямую — git и gh не нужны, токен никуда не записывается.

Источник истины — эта программа. Файлы в tools/ являются её выводом,
`python3 tools/make_publish.py --check` сверяет, что они не отстали (то же делает CI).
"""
import io
import os
import stat
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

PS1 = r'''#requires -Version 5
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
'''

BAT = """@echo off\nrem publish.bat - entry point for Windows. Same as tools/publish.ps1, but one double-click.\nrem The token is never written to disk: it is asked once at run time.\ntitle AULA F75 - publish to GitHub\nsetlocal\ncd /d "%~dp0"\nif not exist "tools\\publish.ps1" (\n  echo ERROR: tools\\publish.ps1 not found next to this file.\n  echo Unpack the WHOLE folder, do not drag out a single file.\n  pause\n  exit /b 1\n)\npowershell -NoProfile -ExecutionPolicy Bypass -File "tools\\publish.ps1" %*\nif errorlevel 1 (\n  echo.\n  echo Something went wrong. Screenshot this window and send it.\n  pause\n)\n"""

SH = r'''#!/usr/bin/env bash
# publish.sh — Linux/macOS. Репозиторий, один коммит, релиз с ассетом, сверка.
# git и gh не нужны: только curl. Токен не пишется на диск.
#   GH_TOKEN=github_pat_... ./tools/publish.sh --tag v1.0.2 --make-repo
set -euo pipefail
cd "$(dirname "$0")/.."

REPO=aula-f75-russian; OWNER=""; TAG=v1.0.0; MAKE=0; PUBLIC=1; DRY=0
ASSET=AULA_F75_RU_installer.zip; NOTES=RELEASE_NOTES.md
TITLE="AULA F75 — русский интерфейс драйвера"
INCLUDE=(README.md LICENSE RELEASE_NOTES.md TESTS.md .gitignore .gitattributes AULA_F75_RU_installer.zip dist tools)
while [ $# -gt 0 ]; do case "$1" in
  --repo) REPO=$2; shift 2;; --owner) OWNER=$2; shift 2;; --tag) TAG=$2; shift 2;;
  --asset) ASSET=$2; shift 2;; --make-repo) MAKE=1; shift;; --private) PUBLIC=0; shift;;
  --dry-run) DRY=1; shift;; *) echo "не знаю флаг: $1" >&2; exit 2;;
esac; done

[ -n "${GH_TOKEN:-}" ] || { printf 'Токен GitHub: '; read -rs GH_TOKEN; echo; }
API=https://api.github.com
h=( -H "Authorization: token $GH_TOKEN" -H "Accept: application/vnd.github+json"
    -H "X-GitHub-Api-Version: 2022-11-28" -H "User-Agent: aula-f75-ru-publish" )
code() { curl -sS -o /tmp/pub.out -w '%{http_code}' "${h[@]}" "$@"; }

echo "[1/6] проверяю токен"
c=$(code "$API/user"); [ "$c" = 200 ] || { echo "токен не принят (HTTP $c)" >&2; exit 1; }
LOGIN=$(python3 -c "import json;print(json.load(open('/tmp/pub.out'))['login'])")
[ -n "$OWNER" ] || OWNER=$LOGIN
echo "   ok: $LOGIN"

RA="$API/repos/$OWNER/$REPO"
echo "[2/6] репозиторий $OWNER/$REPO"
c=$(code "$RA")
if [ "$c" != 200 ]; then
  if [ "$MAKE" = 0 ]; then echo "репо нет (HTTP $c). Для создания: --make-repo" >&2; exit 1; fi
  if [ "$DRY" = 1 ]; then echo "   DRYRUN: создал бы $OWNER/$REPO"; else
    body=$(python3 -c "import json;print(json.dumps({'name':'$REPO','public':$([ "$PUBLIC" = 1 ] && echo True || echo False),'auto_init':True,'has_issues':True,'description':'Русский интерфейс драйвера AULA F75 (OemDrv / BYCOMBO4).'}))")
    code -X POST "$API/user/repos" -H 'Content-Type: application/json' -d "$body" >/dev/null
    echo "   создан"; sleep 2
  fi
fi

echo "[3/6] собираю файлы"
LIST=/tmp/pub.files; : > "$LIST"
python3 - "$LIST" "${INCLUDE[@]}" <<'PY'
import base64, json, os, sys
out = sys.argv[1]; files = []
for pat in sys.argv[2:]:
    if not os.path.exists(pat):
        print("   нет в папке:", pat); continue
    if os.path.isdir(pat):
        for root, dirs, fs in os.walk(pat):
            for f in sorted(fs):
                p = os.path.join(root, f)
                if 'text_en_reference.xml' in f or '__pycache__' in p: continue
                files.append(p)
    else: files.append(pat)
with open(out, 'w') as fh:
    for p in sorted(files):
        b = open(p, 'rb').read()
        fh.write(json.dumps({'path': p.replace(os.sep, '/'), 'size': len(b),
                             'b64': base64.b64encode(b).decode()}) + "\n")
        print(f"   {len(b):>8}  {p}")
PY
N=$(wc -l < "$LIST" | tr -d ' ')
[ "$N" -gt 0 ] || { echo "нечего отправлять" >&2; exit 1; }
[ "$DRY" = 1 ] && { echo "DRYRUN: стоп, ничего не изменил"; exit 0; }

echo "[4/6] один коммит"
code "$RA/git/ref/heads/main" >/dev/null || true
SHA=$(python3 -c "
import json
try: print(json.load(open('/tmp/pub.out'))['object']['sha'])
except Exception: print('')")
echo "   база-коммит: ${SHA:-<нет, репо пустой>}"
python3 - "$LIST" "$SHA" > /tmp/pub.json <<'PY'
import json, sys
lines = [json.loads(l) for l in open(sys.argv[1])]
sha = sys.argv[2]
body = {"tree": [{"path": f["path"], "mode": "100644", "type": "blob",
                 "content": f["b64"], "encoding": "base64"} for f in lines]}
if sha: body["base_tree"] = sha
print(json.dumps(body))
PY
code -X POST "$RA/git/trees" -H 'Content-Type: application/json' --data-binary @/tmp/pub.json >/dev/null
TREE=$(python3 -c "import json;print(json.load(open('/tmp/pub.out'))['sha'])")
if [ -n "$SHA" ]; then
  printf '{"message":"выложил %s · %s файлов","tree":"%s","parents":["%s"]}' "$(date '+%F %H:%M')" "$N" "$TREE" "$SHA" > /tmp/pub2.json
else
  printf '{"message":"выложил %s · %s файлов","tree":"%s"}' "$(date '+%F %H:%M')" "$N" "$TREE" > /tmp/pub2.json
fi
code -X POST "$RA/git/commits" -H 'Content-Type: application/json' --data-binary @/tmp/pub2.json >/dev/null
COMMIT=$(python3 -c "import json;print(json.load(open('/tmp/pub.out'))['sha'])")
printf '{"sha":"%s"}' "$COMMIT" > /tmp/pub3.json
code -X PUT "$RA/git/refs/heads/main" -H 'Content-Type: application/json' --data-binary @/tmp/pub3.json >/dev/null
echo "   коммит ${COMMIT:0:7}"

echo "[5/6] релиз $TAG"
python3 - "$NOTES" "$TAG" "$TITLE" > /tmp/pubr.json <<'PY'
import json, sys, os
body = open(sys.argv[1], encoding='utf-8').read() if os.path.exists(sys.argv[1]) else 'Сборка'
print(json.dumps({"tag_name": sys.argv[2], "name": sys.argv[3], "body": body,
                  "target_commitish": "main", "draft": False, "prerelease": False}))
PY
c=$(code -X POST "$RA/releases" -H 'Content-Type: application/json' --data-binary @/tmp/pubr.json)
if [ "$c" = 422 ]; then
  echo "   релиз уже есть — беру существующий"
  code "$RA/releases/tags/$TAG" >/dev/null
fi
RID=$(python3 -c "import json;print(json.load(open('/tmp/pub.out'))['id'])")
UP=$(python3 -c "import json;print(json.load(open('/tmp/pub.out'))['upload_url'].split('{')[0])")
if [ -f "$ASSET" ]; then
  for a in $(python3 -c "
import json
d=json.load(open('/tmp/pub.out'))
print(' '.join(x['id'] and x['url'] for x in d.get('assets',[])))" 2>/dev/null); do
    code -X DELETE "$a" >/dev/null; echo "   удалил старый ассет"
  done
  code -X POST "$UP?name=$(basename "$ASSET")" -H 'Content-Type: application/octet-stream' \
      --data-binary "@$ASSET" >/dev/null
  echo "   ассет загружен"
fi

echo "[6/6] сверка с GitHub"
code "$RA/git/trees/$COMMIT?recursive=1" >/dev/null
python3 - "$LIST" <<'PY'
import json, sys
remote = {e['path']: e.get('size') for e in json.load(open('/tmp/pub.out'))['tree'] if e['type'] == 'blob'}
bad = 0
for line in open(sys.argv[1]):
    f = json.loads(line)
    if remote.get(f['path']) != f['size']:
        print(f"   ✗ {f['path']}: локально {f['size']}, на GitHub {remote.get(f['path'])}"); bad += 1
    else:
        print(f"   ✓ {f['path']}  ({f['size']} байт)")
sys.exit(1 if bad else 0)
PY
echo
echo "готово: https://github.com/$OWNER/$REPO/releases/latest"
'''


def main() -> None:
    # `--check` — режим для CI: ничего НЕ писать, а расхождение считать ошибкой.
    # Без этого флага генератор всегда «зелёный», потому что сам себя чинит,
    # и тогда проверка в GitHub Actions не проверяет ровно ничего.
    check = '--check' in sys.argv[1:]
    outs = {
        os.path.join(ROOT, 'tools', 'publish.ps1'): PS1,
        os.path.join(ROOT, 'tools', 'publish.bat'): BAT,
        os.path.join(ROOT, 'tools', 'publish.sh'): SH,
    }
    rc = 0
    for path, text in outs.items():
        # Windows-скрипты (.bat, .ps1) — строго CRLF и побайтово; .sh — строго LF.
        # Ошибки в этой строке стоят «bat не запускается» / «git переписал файл».
        if path.endswith('.bat'):
            text.encode('ascii')                       # обёртка обязана быть чистой ASCII
        nl = '\n' if path.endswith('.sh') else '\r\n'
        want = text.replace('\r\n', '\n').replace('\n', nl).encode('utf-8')
        have = open(path, 'rb').read() if os.path.exists(path) else None
        if have == want:
            print(f"ok  {os.path.relpath(path, ROOT)} не отстал")
            continue
        if check:
            print(f"ОТСТАЛ  {os.path.relpath(path, ROOT)}: на диске {len(have or b'')} байт, "
                  f"генератор даёт {len(want)}. Запусти: python3 tools/make_publish.py")
            rc = 1
            continue
        io.open(path, 'wb').write(want)
        if path.endswith('.sh'):
            os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR | stat.S_IXGRP)
        print(f"write {os.path.relpath(path, ROOT)} ({len(want)} байт)")
    if rc:
        sys.exit(rc)


if __name__ == '__main__':
    main()
