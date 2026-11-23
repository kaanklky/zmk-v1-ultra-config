# zmk-key-loop

Zephyr module for the Keychron ZMK fork. It adds the behavior `zmk,behavior-key-loop`: the
first press starts a loop that presses and releases one key every `delay-ms` milliseconds, the
next press of the same binding stops it. The module is built through `ZMK_EXTRA_MODULES` in
`scripts/container-build.sh`, so the fork is not patched.

## Use

Define the behavior in the keymap and use it like a key press:

```
key_loop: key_loop {
    compatible = "zmk,behavior-key-loop";
    #binding-cells = <1>;
    delay-ms = <1>;
};
```

`&key_loop SPACE` starts and stops the loop of the Space key. The Windows Fn layer of
`config/keychron_v1_ultra_ansi.keymap` has it on Fn + Space.

## How it works

- The behavior owns one delayed work item. Every run of the work item flips the key state
  (press, then release, then press) through the normal keycode event path and schedules the next
  run after `delay-ms`.
- A press of the binding only changes a flag and schedules the work item immediately. The key
  state changes happen only inside the work item, so a stop never leaves the key held down: the
  work item releases the key before it ends.
- The loop keeps running when the Fn key is released, and it does not depend on the layer.

## Limits

- The delay is measured in kernel ticks of 1 ms (`CONFIG_SYS_CLOCK_TICKS_PER_SEC=1000`), so 1 ms
  is the smallest step and the real period can jitter by one tick.
- The host sees the key only as fast as the keyboard sends HID reports. USB polls every 1 ms,
  2.4G and Bluetooth are slower, so with `delay-ms = <1>` presses can be merged or queued. Raise
  `delay-ms` if keys go missing or if the input keeps going for a while after the stop.
- Nothing stops the loop besides the same binding, including the keyboard going idle. A loop of
  1 ms floods the host with key events.
- The Keychron Launcher cannot represent this behavior and shows an empty key there. After
  flashing a keymap with a new behavior use the Launcher keymap reset and power cycle the
  keyboard, as described in the main README.
