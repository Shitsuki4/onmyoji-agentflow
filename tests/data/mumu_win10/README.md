Win10 21H2 (10.0.19044.5011), MuMu installed at `C:\Program Files\Netease\MuMu\nx_main`,
adb 1.0.41 (36.0.0). Read-only checks done by the user on their own machine.

- `manager_info_all.json`: `MuMuManager.exe info -v all`, one instance keyed "0". Rebuilt from the
  fields reported (adb_host_ip, adb_port, player_state, hyperv_enabled, vt_enabled, main_wnd,
  render_wnd); window handles and the instance name are placeholders.
- `adb_devices.txt`, `wm_size.txt`, `wm_density.txt`: `adb devices`, `adb shell wm size`, `adb shell wm density`.
