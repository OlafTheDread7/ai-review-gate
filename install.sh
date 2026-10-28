#!/usr/bin/env bash
# Installs or updates the AI Review ship gate in one or more repos (macOS / Linux).
# Same job as Install-AIReview.ps1: copies files/github/ into each repo's .github/.
# A preview unless you pass --go. Runs no git commands.
#
#   bash install.sh path/to/repo                       # preview
#   bash install.sh --go path/to/repo                  # write
#   bash install.sh --go --context notes/CONTEXT.md --surface notes/surface.json path/to/repo
set -euo pipefail

usage() { sed -n '2,8p' "$0" | sed 's/^# \{0,1\}//'; exit "${1:-0}"; }

GO=0; CONTEXT=""; SURFACE=""; REPOS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --go) GO=1 ;;
    --context) CONTEXT="${2:?--context needs a file}"; shift ;;
    --surface) SURFACE="${2:?--surface needs a file}"; shift ;;
    -h|--help) usage 0 ;;
    -*) echo "Unknown option: $1" >&2; usage 1 ;;
    *) REPOS+=("$1") ;;
  esac
  shift
done

[ ${#REPOS[@]} -gt 0 ] || { echo "Give at least one repo path." >&2; usage 1; }
if { [ -n "$CONTEXT" ] || [ -n "$SURFACE" ]; } && [ ${#REPOS[@]} -ne 1 ]; then
  echo "--context and --surface work with exactly one repo." >&2; exit 1
fi
for f in "$CONTEXT" "$SURFACE"; do
  if [ -n "$f" ] && [ ! -f "$f" ]; then echo "Not found: $f" >&2; exit 1; fi
done

KIT="$(cd "$(dirname "$0")" && pwd)/files/github"
[ -d "$KIT" ] || { echo "Kit files not found at $KIT" >&2; exit 1; }
OWNED=(workflows/ai-review.yml ai-review/prepare.sh ai-review/checks.py ai-review/enforce.py ai-review/gitleaks.toml ai-review/REVIEW.md)

same() { cmp -s "$1" "$2"; }

if [ $GO -eq 1 ]; then echo "AI Review kit -> ${#REPOS[@]} repo(s). WRITING"; else echo "AI Review kit -> ${#REPOS[@]} repo(s). PREVIEW (add --go to write)"; fi

changed_any=0
for repo in "${REPOS[@]}"; do
  if [ ! -d "$repo" ]; then echo "SKIP $repo (folder not found)"; continue; fi
  repo="$(cd "$repo" && pwd)"
  if [ ! -e "$repo/.git" ]; then echo "SKIP $repo (not a git repo; run git init first)"; continue; fi
  lines=(); srcs=(); dsts=()
  for rel in "${OWNED[@]}"; do
    src="$KIT/$rel"; dst="$repo/.github/$rel"
    if [ ! -f "$dst" ]; then lines+=("new      .github/$rel")
    elif ! same "$src" "$dst"; then lines+=("updated  .github/$rel")
    else continue; fi
    srcs+=("$src"); dsts+=("$dst")
  done
  for pair in "CONTEXT.md:$CONTEXT" "surface.json:$SURFACE"; do
    name="${pair%%:*}"; src="${pair#*:}"
    [ -n "$src" ] || continue
    dst="$repo/.github/ai-review/$name"
    if [ ! -f "$dst" ]; then lines+=("new      .github/ai-review/$name")
    elif ! same "$src" "$dst"; then lines+=("updated  .github/ai-review/$name")
    else continue; fi
    srcs+=("$src"); dsts+=("$dst")
  done
  if [ ${#lines[@]} -eq 0 ]; then echo "OK   $repo (already current)"; continue; fi
  changed_any=1
  if [ $GO -eq 1 ]; then echo "DONE $repo"; else echo "WILL $repo"; fi
  for i in "${!lines[@]}"; do
    echo "       ${lines[$i]}"
    if [ $GO -eq 1 ]; then
      mkdir -p "$(dirname "${dsts[$i]}")"
      cp "${srcs[$i]}" "${dsts[$i]}"
    fi
  done
  [ -f "$repo/.github/ai-review/CONTEXT.md" ] || [ -n "$CONTEXT" ] || \
    echo "       note     no .github/ai-review/CONTEXT.md yet (the reviewer works without one, but better with it)"
done

if [ $changed_any -eq 1 ]; then
  if [ $GO -eq 1 ]; then echo; echo "Written. Commit and push each repo listed above."
  else echo; echo "Nothing written. Run again with --go to install."; fi
fi
