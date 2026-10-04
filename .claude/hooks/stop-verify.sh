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
