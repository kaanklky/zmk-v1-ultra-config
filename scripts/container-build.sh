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
    -DZephyr_DIR="$root/zephyr/share/zephyr-package/cmake"

mkdir -p "$root/out"
cp build/zephyr/zmk.bin "$root/out/zmk.bin"
cd "$root/out"
sha256sum zmk.bin > zmk.bin.sha256
cat zmk.bin.sha256
