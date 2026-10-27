#!/usr/bin/env bash
# Bootstrap preset expert profiles on a fresh Hermes install.
# Idempotent: skips profiles that already exist.
set -euo pipefail

HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"

bootstrap_expert() {
  local name="$1" persona="$2" expertise="$3" prompt="$4" model="${5:-deepseek-chat}"
  local soul_path="$HERMES_HOME/profiles/$name/SOUL.md"

  if [ -f "$soul_path" ]; then
    echo "✓ $name already exists, skipping"
    return
  fi

  echo "→ Creating profile: $name"
  hermes profile create "$name"

  mkdir -p "$HERMES_HOME/profiles/$name"
  cat > "$soul_path" <<EOF
# Persona
$persona

# Expertise
$expertise

# Prompt
$prompt
EOF
  echo "✓ $name SOUL.md written"
}

# Source the preset definitions from the backend package.
PY_PRESETS="$(cd "$(dirname "$0")/.." && pwd)/backend/app/presets.py"

eval "$(python3 -c "
import sys
sys.path.insert(0, '$(dirname "$0")/../backend')
from app.presets import PRESET_EXPERTS
for p in PRESET_EXPERTS:
    print(f'bootstrap_expert {p[\"name\"]!r} {p[\"persona\"]!r} {p[\"expertise\"]!r} {p[\"prompt\"]!r} {p[\"model\"]!r}')
")"

echo "✅ All preset experts bootstrapped"