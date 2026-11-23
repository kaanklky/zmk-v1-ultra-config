#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

export ZEPHYR_TOOLCHAIN_VARIANT=zephyr
export ZEPHYR_SDK_INSTALL_DIR="${ZEPHYR_SDK_INSTALL_DIR:-/opt/toolchains/zephyr-sdk-${ZSDK_VERSION}}"
export HOME="${HOME:-/tmp/home}"
mkdir -p "$HOME"

git config --global --add safe.directory '*'

cd "$root"
if [ ! -d .west ]; then
    west init -l config
fi
west update

cd zmk/app
west build -p always -b keychron -d build -- \
    -DSHIELD=keychron_v1_ultra_ansi \
    -DZMK_CONFIG="$root/config" \
    -DZMK_EXTRA_MODULES="$root/zmk-key-loop" \
    -DZephyr_DIR="$root/zephyr/share/zephyr-package/cmake"

commit="$(git -C "$root" rev-parse --short HEAD 2>/dev/null || echo unknown)"
if [ -n "$(git -C "$root" status --porcelain 2>/dev/null)" ]; then
    commit="$commit-dirty"
fi
name="v1ultra-${BUILD_NUMBER:-local}-$commit"

rm -rf "$root/out"
mkdir -p "$root/out"
cp build/zephyr/zmk.bin "$root/out/$name.bin"
cd "$root/out"
sha256sum "$name.bin" > "$name.bin.sha256"
cat "$name.bin.sha256"
