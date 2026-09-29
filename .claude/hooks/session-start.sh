#!/bin/bash
# Prepare the venv so .mcp.json can start the interpreter MCP server and
# tests can run in Claude Code on the web. Idempotent.
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "$CLAUDE_PROJECT_DIR"

if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
fi
.venv/bin/pip install -q -e '.[dev]'

echo 'export PATH="'"$CLAUDE_PROJECT_DIR"'/.venv/bin:$PATH"' >> "${CLAUDE_ENV_FILE:-/dev/null}"
echo "interpreter: venv ready ($(.venv/bin/python --version))"
