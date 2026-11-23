# zmk-v1-ultra-config

Firmware configuration for the Keychron V1 Ultra 8K (ANSI, Realtek RTL8762G). It builds
the vendor ZMK fork `Keychron/zmk` with our own keymap in `config/`, so the keymap lives in
git instead of only inside the keyboard.

## Layout

- `config/west.yml`: west manifest. `zmk`, `zephyr` and `hal_realtek` are pinned to the exact
  commits of the build that was verified on the keyboard.
- `config/keychron_v1_ultra_ansi.keymap`: the keymap. It replaces the keymap of the shield
  `keychron_v1_ultra_ansi` of the fork (`ZMK_CONFIG`).
- `scripts/build.sh`: builds in Docker on the machine. Needs Docker only.
- `scripts/container-build.sh`: the actual build steps, also used by GitHub Actions.
- `.github/workflows/build.yml`: builds on every push and uploads `out/` as an artifact.
- `tools/kdfu.py`: USB firmware updater, see `tools/README.md`.

## Build

```
./scripts/build.sh
```

The first run downloads about 2 GB of west projects into `zmk/`, `zephyr/` and `modules/`
(git ignored). The result is `out/zmk.bin` with `out/zmk.bin.sha256`. The toolchain is the
Zephyr CI image `ghcr.io/zephyrproject-rtos/ci:v0.26.11`, the same one Keychron builds with.

## Flash

Run on the machine the keyboard is plugged into with a cable (Windows Python, not WSL):

```
python tools/kdfu.py info
python tools/kdfu.py flash out/zmk.bin
python tools/kdfu.py flash out/zmk.bin --yes
```

Keep a known good image to go back to. The updater can flash it again as long as the running
firmware still answers on USB.

## Keymap notes

- The keymap file is the whole keymap, copied from the shield of the fork and then changed.
  Matrix positions are the order of the `RC(row,col)` entries in the shield overlay (87 keys
  per layer, the last 5 are the hardware mode keys).
- Layers: 0 mac, 1 mac Fn, 2 Windows, 3 Windows Fn.
- Right Alt + knob changes the RGB brightness and Right Alt + knob press toggles the RGB
  (Windows layer), through `mod-morph` behaviors defined at the top of the keymap.
- The Keychron Launcher stores its own keymap in the keyboard. At boot the firmware applies a
  stored Launcher key only where it differs from the key generated from this file, so a Launcher
  value wins over this file. Behaviors the Launcher cannot represent (the mod-morph ones)
  show up as empty keys there, and an old Launcher value stored for the same key hides them.
  After flashing a new keymap, use the Launcher keymap reset once and unplug and replug the
  keyboard. The reset deletes the stored keys and knobs, so the keymap of this file is active
  after the power cycle. Until the power cycle the mod-morph keys act as empty keys.
- Launcher macros (M1 to M5 on Fn + 1 to 5) are kept in the keyboard, not in this repository.
  A Launcher factory reset or a change of `ZMK_BUILDDATE` in `launcher.h` of the fork deletes them.

## Updating the pinned versions

Change the revisions in `config/west.yml` to the new commits, run `./scripts/build.sh`, flash and
check that the keyboard and its Launcher still work before committing.

## Licenses

ZMK is MIT. The Keychron fork contains files under GPL headers and the `hal_realtek` module
ships Realtek libraries under their own terms, so the fork and its modules are fetched by
west and are not copied into this repository. Keep this repository private unless that has
been checked.
