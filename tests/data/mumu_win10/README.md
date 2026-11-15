Win10 21H2 (10.0.19044), MuMu installed under `C:\Program Files\Netease\MuMu` (new `nx_main` layout),
one instance, VBox backend. Read-only output collected on the user's own machine on 2026-11-15.

- `manager_info_all.json`: `nx_main\MuMuManager.exe info -v all`, verbatim (one instance keyed "0").
  `launch_time` is the uptime in ms and changes on every call; `created_timestamp` is in microseconds.
- `manager_info_0.json`: `MuMuManager.exe info -v 0`, verbatim (bare object, no index key).
- `adb_devices.txt`, `wm_size.txt`, `wm_density.txt`: `nx_main\adb.exe devices`, `adb -s 127.0.0.1:16384 shell wm size`,
  `adb -s 127.0.0.1:16384 shell wm density`, verbatim. `emulator-5554` is the same instance as `127.0.0.1:16384`.
- `pm_list_packages.txt`: the game's package on this machine is the channel build
  `com.netease.onmyoji.wyzymnqsd_cps` (taken from `dumpsys window`).

`external_renderer_ipc.dll` exists in three places on this machine: `nx_main\sdk`, `nx_device\12.0\shell\sdk` and
`nx_device\15.0\shell\sdk`; `nx_main\sdk` is tried first.
