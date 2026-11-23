# kdfu

USB firmware updater for the Keychron V1 Ultra (ZMK, Realtek RTL8762G). It speaks the same
HID protocol as the Keychron Launcher firmware update tab, but takes a file from disk.

The protocol was derived from `app/src/dfu/tdfu.c` and `tdfu_usb.c` of the
`Keychron/zmk` branch `rtl8762g`. It is implemented by the running firmware itself, so no
special bootloader mode is needed: the keyboard only has to be on the USB cable in wired mode.

## Requirements

- Python 3.8 or newer on the machine the keyboard is plugged into. Run it with the Windows
  Python (PowerShell, or `powershell.exe` from inside WSL2). WSL2 itself cannot see USB devices
  without usbipd-win, and attaching the keyboard to WSL2 takes it away from Windows.
- `pip install hidapi`

## Commands

```
python tools/kdfu.py list
python tools/kdfu.py info
python tools/kdfu.py flash IMAGE
python tools/kdfu.py flash IMAGE --yes --no-switch
python tools/kdfu.py flash IMAGE --yes
```

- `list` prints every HID interface of vendor 0x3434 that uses usage page 0x8C, for all
  product ids. Other Keychron devices on the same machine (for example a 2.4G receiver) show up
  here too.
- `info` is read only: model string, firmware version, hardware version, DFU version, build
  date and the Realtek image versions.
- `flash IMAGE` without `--yes` only runs the local checks and the model query, and sends
  nothing that changes the keyboard.
- `--yes --no-switch` uploads the image to the staging area and lets the keyboard verify it,
  but does not ask it to install the image. A power cycle returns to normal.
- `--yes` does the whole update. After the activation request the keyboard reboots and its
  boot code copies the staged image over the running one. Do not unplug it meanwhile.

Options: `--pid` selects the USB product id (default 0x0c10, the V1 Ultra in wired mode),
`--path` selects an interface from `list` and overrides `--pid`, `--report-len` (default 32) is the size
of the DFU HID report, `--chunk` is the data bytes per packet (default `report-len - 8`,
at most 48, at least 16), `--timeout` and `--retries` tune acknowledgement waiting,
`--verbose` prints retries.

## Checks done before anything is written

- the image fits the 356 KB staging area (0x59000 bytes)
- the 8 byte customer name in the image header at offset 0x208 equals the model string the
  keyboard reports (`KCZKV18K` for the V1 Ultra ANSI), which is also what the firmware
  itself checks
- during the upload the keyboard returns a running CRC32 after every packet and the tool
  aborts on the first difference
- the activation request is only sent after the keyboard confirmed both CRC32 and its own
  SHA256 header check

## Protocol summary

Output report id 0xB2, input report id 0xB1, 32 data bytes each. Frame:
`AA 55|56 len ~len sn opcode payload sum16`, where `len` is payload length plus 3, `sum16`
is the little endian 16 bit sum of opcode and payload, and the start opcode must use header
byte `56`. Responses carry `rsp sn_ack cmd status payload` and are split over two reports
when longer than 32 bytes. The CRC32 is the usual reflected 0xEDB88320 CRC with initial value
0xFFFFFFFF and no final inversion. Sequence numbers run 1 to 255 and wrap to 1, and the
keyboard silently ignores a packet whose number is not the expected next one, so a lost
reply is handled by resending the same packet.

| Opcode | Meaning |
| --- | --- |
| 0x60 | model info |
| 0x61 | DFU version and encryption mode |
| 0x62 | set transfer mode, 0 = plain |
| 0x63 | start, opens the update session and lifts flash write protection, sectors are erased while data arrives |
| 0x64 | data packet |
| 0x65 | verify, payload is the CRC32 twice |
| 0x66 | activate, no reply, the keyboard reboots |
| 0x6E | Realtek image versions |
| 0x6F | build date and time |

## Known limits

- It has only been tested against an emulation written from the firmware source, never
  against hardware at the time of writing.
- The firmware has a single application bank. The new image is staged first and copied by the
  boot code after the reboot, so a firmware that boots but no longer offers this DFU interface
  cannot be replaced over USB. Keep the stock image and only flash images built from the
  same tree with `CONFIG_RTK_DFU` and `CONFIG_KEYCHRON_FWU_STRING_NAME` unchanged.
