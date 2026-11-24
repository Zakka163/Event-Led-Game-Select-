# EmulationStation Event Compatibility Report (Batocera & EmuELEC)

> **Honesty & Verification Policy:** No platform behavior is marked as *live-verified* until tested on physical target hardware. This document separates **official documentation**, **community/ecosystem evidence**, and **unverified items requiring on-device testing**.

---

## 1. Compatibility Summary Matrix

| Platform | Event Hook | Expected Script Directory | Expected Arguments | Documentation Status | Live Hardware Test Status |
| --- | --- | --- | --- | --- | --- |
| **Batocera (v33+)** | `game-selected` | `/userdata/system/configs/emulationstation/scripts/game-selected/` | `$1`: system shortname<br>`$2`: ROM path<br>`$3`: game display name | Documented on official Batocera Wiki (`launch_a_script`) | **Not yet tested on live Batocera device** |
| **Batocera (< v33)** | `game-selected` | N/A | N/A | Not officially documented before v33 | **Unsupported / Unverified** |
| **EmuELEC (4.4+)** | `game-selected` | Candidate: `/storage/.config/emulationstation/scripts/game-selected/` (some community docs mention `/storage/.emulationstation/...`) | Candidate: `$1` system, `$2` ROM path, `$3` game name (**UNCONFIRMED across all builds**) | Referenced by third-party integrations (e.g., Pixelcade); varies by `emuelec-emulationstation` build | **UNVERIFIED — Probe required first** |
| **EmuELEC (< 4.4 / custom builds)** | Unknown | May lack `game-selected` in `Scripting::fireEvent` | Unknown | May only support `game-start` / `game-end` | **UNVERIFIED — Fallback evaluation needed** |

---

## 2. Batocera Findings

### What Official Documentation Confirms
Per the Batocera Wiki ([Launch a script](https://wiki.batocera.org/launch_a_script)):
- EmulationStation fires the `game-selected` event when the user highlights a game in a gamelist (and also during screensaver preview transitions).
- Executable scripts placed in:
  ```text
  /userdata/system/configs/emulationstation/scripts/game-selected/
  ```
  are invoked automatically with:
  - `$1`: `getSourceFileData()->getSystem()->getName()` (system shortname, e.g., `mame`)
  - `$2`: `getPath()` (ROM path, e.g., `/userdata/roms/mame/sf2.zip`)
  - `$3`: `getName()` (display game title, e.g., `Street Fighter II`)

### Operational Caveats to Verify on Target Batocera Version
1. **Synchronous UI Execution Risk:** In `batocera-emulationstation`, `Scripting::fireEvent()` can block the UI thread if a hook script runs slow foreground work. ArcadeLED mitigates this by detaching the call into the background (`&`) inside `host/adapters/batocera/game_selected.sh` and debouncing rapid scrolls in `host/main.py daemon`.
2. **Screensaver Events:** `game-selected` can also fire during EmulationStation's screensaver; verify on-device whether this behavior is desirable or should be filtered in Phase 2.
3. **Version Variance:** Exact parameter formatting (e.g., relative vs absolute ROM paths, quote handling for titles with apostrophes) must be verified on the user's exact Batocera release using `tail -f /userdata/system/arcadeled/host/logs/events.log`.

---

## 3. EmuELEC Investigation & Findings

### Architecture Context
- EmuELEC runs on a minimal LibreELEC/CoreELEC Linux base with a writable `/storage` partition and uses its own EmulationStation fork (`EmuELEC/emuelec-emulationstation`), derived from Batocera/RetroPie lineages.
- Because `emuelec-emulationstation` tracks upstream changes independently across EmuELEC releases, **Batocera's hook path and argument layout must NOT be assumed blindly**.

### What Ecosystem References Indicate (Requires Verification)
- Third-party marquee tools (such as Pixelcade for EmuELEC 4.4+) reference EmulationStation event scripts under `/storage/.config/emulationstation/scripts/game-selected/` (and in some setups `/storage/.emulationstation/configs/scripts`).
- Older or stripped-down EmuELEC builds may:
  - Lack `game-selected` in `es-core/src/Scripting.cpp` (only firing `game-start` / `game-end`).
  - Pass a different number/order of positional arguments (`$1`, `$2`, `$3`).
  - Lack `python3` or ship a minimal Python environment without optional packages.

### On-Device Verification Procedure (Phase 1)
Do **not** install a Batocera adapter directly onto EmuELEC. Instead:
1. Run the read-only probe over SSH on your EmuELEC device:
   ```sh
   sh scripts/install_emuelec.sh
   ```
   This inspects `/etc/release`, candidate EmulationStation script directories, `emulationstation` binary event strings (`game-selected`, `game-select`, `system-selected`), and `python3` availability.
2. If `game-selected` is present in the binary/config, install the non-intrusive probe script:
   ```sh
   sh scripts/install_emuelec.sh --install-probe
   ```
3. Browse games in EmulationStation and inspect raw captured arguments:
   ```sh
   tail -f /tmp/arcadeled_emuelec_probe.log
   ```
4. Record the verified EmuELEC version, directory path, and exact `$1`/`$2`/`$3` values here before promoting `adapter_placeholder.sh` to a production `game_selected.sh` adapter.

### Evaluated Fallbacks If Target EmuELEC Build Lacks `game-selected`
If on-device probing proves that the target EmuELEC EmulationStation binary does **not** fire `game-selected`, the recommended fallback options (ordered from cleanest to most invasive) are:
1. **Upgrade to an EmuELEC version (4.4+) whose `emuelec-emulationstation` includes `Scripting::fireEvent("game-selected", ...)`.**
2. **Minimal C++ Patch to `emuelec-emulationstation`:** Add a debounced `Scripting::fireEvent("game-selected", systemName, romPath, gameName)` call inside `IGameListView::onCursorChanged` (matching Batocera's signature) and rebuild the `emuelec-emulationstation` package cleanly.
3. **Avoid heavy polling:** Do NOT poll RetroArch or scrape screen memory, as that violates ArcadeLED's low-overhead and pre-launch selection goals.
