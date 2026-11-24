# Stage2 I²C and GPIO CLI

Export the active profile with `python script/cli/hex-bridge-profile.py --port COM4 --baud 115200 export profile.json`. The exported v6 JSON contains both `i2c` controllers and all fourteen `gpio_lines`. Edit this complete file, then use the existing `check`, `save`, `apply`, and `confirm` profile commands. Only active mappings with successfully initialized topology channels can perform business operations.

Keep I²C OPEN and transfers on the same connection. From PowerShell at the repository root:

```powershell
@'
i2c open --bus 0 --addr-bits 7
i2c read-reg --bus 0 --addr 0x50 --reg 00 --length 4
i2c write-read --bus 0 --addr 0x50 --data 00 --length 4
i2c scan --bus 0
i2c close --bus 0
gpio read --line 1
'@ | python script/cli/hex-bridge-io.py --port COM4 --baud 115200 --batch
```

Replace the address and logical GPIO line with those configured for the connected device. Addresses are raw values: `0x50` is sent without shifting. Register and write bytes are hexadecimal in transmission order (`--reg 0102`, `--data aabb`). Reads with a register prefix and WRITE_READ use repeated START. Scan is explicit and only available for seven-bit addressing. `i2c config --bus 0 --clock-hz 400000 --timeout-ms 1000` changes that open session's parameters; supported clocks are 100/400 kHz and timeouts are 1–1000 ms.

GPIO operations always use logical line numbers, resolving physical pins and group channels from the active mapping:

```powershell
python script/cli/hex-bridge-io.py --port COM4 gpio write --line 0 --level 1
python script/cli/hex-bridge-io.py --port COM4 gpio watch --line 1 --edge both --debounce-ms 10 --seconds 30
```

Batch commands also work as lines inside `--batch` input. JSON must remain one shell argument; these examples show the exact input lines:

```text
gpio plan-write '{"0":1,"2":0}'
gpio write-many '{"0":1,"2":0}'
gpio read-many '[0,1,2]'
```

`plan-write` exposes each group before writing. `write-many` preflights every line, then returns one result per group; one group can succeed while another fails. Each response includes instance, channel, sequence, status and hexadecimal data. A business error makes batch mode exit with a nonzero code. Watch returns events with logical line, physical pin, trigger, sampled level, device timestamp and host overflow count. Its duration defaults to five seconds and can be set explicitly.

Graceful disconnect best-effort closes the buses opened by this client, then discards OPEN state and queued events. Reconnect to discover the new active mapping and explicitly OPEN again. If a previous UART client crashed after OPEN, explicitly run `i2c close --bus 0` before OPEN to recover the device's surviving session. CLOSE is allowed even when this host has no local OPEN record. Transfers are never automatically replayed after a timeout or disconnect.

The desktop tool is `python tool/funcitonPinMap/app.py`. Its I²C / GPIO tab separates local profile editing from business operations. Select a GPIO row's details to edit bias, initial latch, trigger and debounce. Use “连接业务会话” before business operations; profile transactions and device refresh close this session. The batch preview shows separate groups before execution. Initial output level belongs to the profile; the read result reports the sampled electrical level.
