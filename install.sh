#!/usr/bin/env bash
# Installs the rom CLI: a venv with Textual + wrappers in ~/bin.
# Works on Linux, macOS, and Windows (Git Bash / MSYS2).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
SRC="$ROOT/bin"
DEST="${PREFIX:-$HOME/bin}"
VENV="${ROM_VENV:-$HOME/.venvs/rom}"

# ── detect usable Python ────────────────────────────────────────────────
PY="${PYTHON:-}"
if [ -z "$PY" ]; then
  for cand in python3 python py; do
    if command -v "$cand" >/dev/null 2>&1 && "$cand" -c "import sys" 2>/dev/null; then
      PY="$cand"
      break
    fi
  done
fi
[ -n "$PY" ] || { echo "error: python not found — install Python 3.8+ first"; exit 1; }
echo "using $("$PY" --version 2>&1)"

mkdir -p "$DEST" "$(dirname "$VENV")"

# ── detect venv layout (Windows uses Scripts/, Unix uses bin/) ──────────
venv_py() {
  if [ -x "$VENV/Scripts/python.exe" ]; then
    echo "$VENV/Scripts/python"
  elif [ -x "$VENV/Scripts/python" ]; then
    echo "$VENV/Scripts/python"
  else
    echo "$VENV/bin/python"
  fi
}

if [ ! -x "$(venv_py)" ]; then
  echo "creating venv in ${VENV}"
  "$PY" -m venv "$VENV"
fi
VENV_PY="$(venv_py)"

echo "installing textual and pillow"
"$VENV_PY" -m pip install -q --upgrade pip >/dev/null 2>&1 || true
"$VENV_PY" -m pip install -q textual pillow

# ── create wrapper scripts ──────────────────────────────────────────────
write_wrapper() {
  local name="$1" target="$2"
  cat > "$DEST/$name" <<EOF
#!/usr/bin/env bash
exec "$VENV_PY" "$target" "\$@"
EOF
  chmod 755 "$DEST/$name"
}

write_wrapper rom "$SRC/rom"

# Windows: also create a .cmd wrapper for CMD / PowerShell
if [[ "${OSTYPE:-}" == msys* || "${OSTYPE:-}" == cygwin* || "${MSYSTEM:-}" != "" ]]; then
  VENV_PY_W="$(cygpath -w "$VENV_PY" 2>/dev/null || echo "$VENV_PY")"
  SRC_W="$(cygpath -w "$SRC/rom" 2>/dev/null || echo "$SRC/rom")"
  cat > "$DEST/rom.cmd" <<CMDEOF
@echo off
"$VENV_PY_W" "$SRC_W" %*
CMDEOF
  echo "created: $DEST/rom.cmd (for CMD / PowerShell)"
fi

if [ -f "$SRC/rom-remote" ]; then
  install -m 755 "$SRC/rom-remote" "$DEST/rom-remote"
fi

echo "installed: $DEST/rom (venv: $VENV)"
case ":$PATH:" in
  *":$DEST:"*) ;;
  *) echo "warning: add $DEST to your PATH (e.g. export PATH=\"$DEST:\$PATH\")";;
esac
echo "test: rom -l    |    rom --index"
