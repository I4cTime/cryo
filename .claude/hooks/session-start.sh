#!/bin/bash
# SessionStart hook for Claude Code cloud sessions: prepares the uv venv so
# tests and the CI checks can run without a local machine.
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "$CLAUDE_PROJECT_DIR"

if ! command -v uv >/dev/null 2>&1; then
  python3 -m pip install --quiet --user uv
  export PATH="$HOME/.local/bin:$PATH"
fi

# Same install CI uses: Python 3.12 (requires-python >=3.12) and the
# locked deps, including the dev group (pytest). Idempotent.
uv sync --frozen --python 3.12

# Put the venv first on PATH so `pytest`, `cryoctl` etc. resolve directly.
if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
  echo "export PATH=\"$CLAUDE_PROJECT_DIR/.venv/bin:\$PATH\"" >> "$CLAUDE_ENV_FILE"
fi
