#!/usr/bin/env bash
# Stop hook: if there are uncommitted changes, run the verify command.
# Exit 2 blocks the stop and feeds the tail of the output back to Claude.
set -uo pipefail
input="$(cat)"
# Avoid loops: if this hook already blocked once this turn, let the stop through.
if printf '%s' "$input" | grep -q '"stop_hook_active": *true'; then
  exit 0
fi
# Run from the repo root even if the session has cd'd elsewhere. Quoted: the path has a space.
cd "${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel)}" || exit 0
# Nothing to check if the tree is clean.
if [ -z "$(git status --porcelain 2>/dev/null)" ]; then
  exit 0
fi
# Hooks run in a bare shell that skips nvm, so load it if npm is missing.
export PATH="$HOME/.local/bin:$PATH"  # uv lives here
if ! command -v npm >/dev/null 2>&1; then
  export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
  [ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh" >/dev/null 2>&1 && nvm use 24 >/dev/null 2>&1
fi
if ! command -v npm >/dev/null 2>&1; then
  echo "Stop hook: npm not found even after loading nvm. Verify did not run." >&2
  exit 2
fi
out="$(npm run verify --silent 2>&1)"
code=$?
if [ "$code" -ne 0 ]; then
  {
    echo "npm run verify FAILED (exit $code). Fix this before stopping. Last 80 lines:"
    printf '%s\n' "$out" | tail -n 80
  } >&2
  exit 2
fi
exit 0
