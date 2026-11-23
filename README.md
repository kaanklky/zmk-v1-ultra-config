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
(git ignored). The result is `out/v1ultra-<build>-<commit>.bin` with a `.sha256` file next to
it. `<build>` is the GitHub Actions run number, or `local` for a local build, and `<commit>`
is the short commit hash with `-dirty` added when the working tree has uncommitted changes.
The same name is used for the artifact in Actions, which is named `v1ultra-firmware-<run>.<attempt>`.
The toolchain is the
Zephyr CI image `ghcr.io/zephyrproject-rtos/ci:v0.26.11`, the same one Keychron builds with.

## Flash

Run on the machine the keyboard is plugged into with a cable (Windows Python, not WSL):

```
python tools/kdfu.py info
python tools/kdfu.py flash out/v1ultra-local-<commit>.bin
python tools/kdfu.py flash out/v1ultra-local-<commit>.bin --yes
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
  After flashing a new keymap, use the Launcher keymap reset once and then power cycle the
  keyboard: unplug the cable and move the mode switch to the cable position, which turns the
  keyboard off when no cable is attached, then switch back to 2.4G or Bluetooth. Replugging the
  cable alone does not reboot a keyboard that runs on 2.4G or Bluetooth. The reset deletes the stored keys and
  knobs, so the keymap of this file is active after the reboot. Until the reboot the knob of the
  Windows layer is empty, so a turn falls through to the volume binding of the Mac layer.
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
