#!/bin/sh
# Установщик rb-tui из GitHub Releases.
#
#   curl -fsSL https://raw.githubusercontent.com/JeySerYT/rb-tui/main/install.sh | sh
#
# Переменные:
#   RB_TUI_REPO          owner/repo (по умолч. JeySerYT/rb-tui)
#   RB_TUI_VERSION       версия без v (по умолч. latest)
#   RB_TUI_INSTALL_DIR   куда ставить бинарник (по умолч. ~/.local/bin)
#   RB_TUI_BASE_URL      свой базовый URL вместо GitHub (для тестов)
set -eu

REPO="${RB_TUI_REPO:-JeySerYT/rb-tui}"
VERSION="${RB_TUI_VERSION:-latest}"
INSTALL_DIR="${RB_TUI_INSTALL_DIR:-${PREFIX:-$HOME/.local}/bin}"

say() { printf '%s\n' "$*"; }
die() { printf 'ошибка: %s\n' "$*" >&2; exit 1; }

if command -v curl >/dev/null 2>&1; then
    download() { curl -fsSL -o "$1" "$2"; }
elif command -v wget >/dev/null 2>&1; then
    download() { wget -q -O "$1" "$2"; }
else
    die "нужен curl или wget"
fi

os="$(uname -s)"
case "$os" in
    Linux) os="linux" ;;
    Darwin) os="darwin" ;;
    *) die "неподдерживаемая ОС: $os (для Windows скачай архив со страницы релизов вручную)" ;;
esac

arch="$(uname -m)"
case "$arch" in
    x86_64|amd64) arch="x86_64" ;;
    aarch64|arm64) arch="arm64" ;;
    *) die "неподдерживаемая архитектура: $arch" ;;
esac

asset="rb-tui-${os}-${arch}.tar.gz"

if [ -n "${RB_TUI_BASE_URL:-}" ]; then
    base="$RB_TUI_BASE_URL"
elif [ "$VERSION" = "latest" ]; then
    base="https://github.com/${REPO}/releases/latest/download"
else
    base="https://github.com/${REPO}/releases/download/v${VERSION}"
fi

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT INT TERM

say "==> скачиваю $asset"
download "$tmp/$asset" "$base/$asset" || die "не удалось скачать $base/$asset"

if download "$tmp/$asset.sha256" "$base/$asset.sha256" 2>/dev/null; then
    if command -v sha256sum >/dev/null 2>&1; then
        (cd "$tmp" && sha256sum -c "$asset.sha256" >/dev/null) \
            || die "контрольная сумма не совпала"
        say "==> контрольная сумма ok"
    fi
else
    say "==> контрольная сумма недоступна, пропускаю проверку"
fi

tar -xzf "$tmp/$asset" -C "$tmp" rb-tui || die "архив повреждён"

mkdir -p "$INSTALL_DIR"
if command -v install >/dev/null 2>&1; then
    install -m 755 "$tmp/rb-tui" "$INSTALL_DIR/rb-tui"
else
    cp "$tmp/rb-tui" "$INSTALL_DIR/rb-tui"
    chmod 755 "$INSTALL_DIR/rb-tui"
fi

say "==> установлено: $INSTALL_DIR/rb-tui"
"$INSTALL_DIR/rb-tui" --version

case ":${PATH}:" in
    *":$INSTALL_DIR:"*) ;;
    *) say "добавь в PATH: export PATH=\"$INSTALL_DIR:\$PATH\"" ;;
esac