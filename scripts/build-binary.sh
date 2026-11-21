#!/usr/bin/env bash
# Собрать standalone-бинарник rb-tui и упаковать его в архив для релиза.
#
# Использование:
#   scripts/build-binary.sh            # собрать под текущую ОС/архитектуру
#
# Результат: dist/release/rb-tui-<os>-<arch>.tar.gz (+ .sha256)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PYTHON_VERSION="${RB_TUI_BUILD_PYTHON:-3.12}"
VENV="$ROOT/.build-venv"

if [ ! -x "$VENV/bin/pyinstaller" ]; then
    echo "==> готовлю сборочное окружение (Python $PYTHON_VERSION)"
    uv venv --python "$PYTHON_VERSION" "$VENV"
    uv pip install --python "$VENV/bin/python" pyinstaller >/dev/null
fi

echo "==> собираю бинарник"
"$VENV/bin/pyinstaller" --clean --noconfirm packaging/rb-tui.spec

VERSION="$(tr -d '[:space:]' < VERSION)"
OS="$(uname -s | tr '[:upper:]' '[:lower:]')"
case "$(uname -m)" in
    x86_64|amd64) ARCH="x86_64" ;;
    aarch64|arm64) ARCH="arm64" ;;
    *) ARCH="$(uname -m)" ;;
esac

OUT="$ROOT/dist/release"
ASSET="rb-tui-${OS}-${ARCH}.tar.gz"
mkdir -p "$OUT"

echo "==> упаковываю $ASSET (v$VERSION)"
tar -czf "$OUT/$ASSET" -C "$ROOT/dist" rb-tui
(cd "$OUT" && sha256sum "$ASSET" > "$ASSET.sha256")

echo
echo "готово:"
echo "  $OUT/$ASSET"
echo "  $OUT/$ASSET.sha256"
"$ROOT/dist/rb-tui" --version