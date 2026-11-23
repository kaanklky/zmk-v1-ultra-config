#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
image="${ZMK_BUILD_IMAGE:-ghcr.io/zephyrproject-rtos/ci:v0.26.11}"

exec docker run --rm \
    -u "$(id -u):$(id -g)" \
    -e HOME=/tmp/home \
    -v "$root:/work" \
    -w /work \
    "$image" \
    bash scripts/container-build.sh
