#!/usr/bin/env bash
# Bootstrap preset expert profiles on a fresh Hermes install.
# Idempotent: skips profiles whose SOUL.md already has the 3-section layout
# (Persona / Expertise / Prompt); rewrites missing or malformed ones.
set -euo pipefail

HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"

soul_complete() {
  local soul_path="$1"
  [ -f "$soul_path" ] || return 1
  grep -q '^# Persona' "$soul_path" || return 1
  grep -q '^# Expertise' "$soul_path" || return 1
  grep -q '^# Prompt' "$soul_path" || return 1
  # At least one non-empty line under each heading.
  awk '/^# Persona/{s=1;c=0;next} /^# Expertise/{s=2;next} /^# Prompt/{s=3;next} s==1&&NF{c=1} s==2&&NF{c+=10} s==3&&NF{c+=100} END{if(c==111){exit 0}else{exit 1}}' "$soul_path"
}

bootstrap_expert() {
  local name="$1" persona="$2" expertise="$3" prompt="$4" model="${5:-deepseek-chat}"
  local profile_dir="$HERMES_HOME/profiles/$name"
  local soul_path="$profile_dir/SOUL.md"

  if soul_complete "$soul_path"; then
    echo "✓ $name already configured, skipping"
    return
  fi

  if [ ! -f "$soul_path" ] && [ ! -d "$profile_dir" ]; then
    echo "→ Creating profile: $name"
    hermes profile create "$name"
  fi

  mkdir -p "$profile_dir"
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
eval "$(python3 -c "
import sys
sys.path.insert(0, '$(dirname "$0")/../backend')
from app.presets import PRESET_EXPERTS
for p in PRESET_EXPERTS:
    print(f'bootstrap_expert {p[\"name\"]!r} {p[\"persona\"]!r} {p[\"expertise\"]!r} {p[\"prompt\"]!r} {p[\"model\"]!r}')
")"

echo "✅ All preset experts bootstrapped"