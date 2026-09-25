#!/usr/bin/env bash
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
out = sys.argv[1]; files = []; skipped = 0
for pat in sys.argv[2:]:
    if not os.path.exists(pat):
        print("   нет в папке:", pat); continue
    if os.path.isdir(pat):
        for root, dirs, fs in os.walk(pat):
            for f in sorted(fs):
                p = os.path.join(root, f)
                if 'text_en_reference.xml' in f or '__pycache__' in p: continue
                if p.replace(os.sep, '/').startswith('.github/workflows/'):
                    skipped += 1; continue          # fine-grained PAT: право `workflow` недоступно
                files.append(p)
    else: files.append(pat)
with open(out, 'w') as fh:
    for p in sorted(files):
        b = open(p, 'rb').read()
        fh.write(json.dumps({'path': p.replace(os.sep, '/'), 'size': len(b),
                             'b64': base64.b64encode(b).decode()}) + "\n")
        print(f"   {len(b):>8}  {p}")
if skipped:
    print(f"   пропущено .github/workflows/* : {skipped} шт. — fine-grained токен не может их писать")
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
