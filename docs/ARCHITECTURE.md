# ArcadeLED Architecture

## 1. Prinsip Desain

1. **Core Engine Lintas-Platform:** Batocera, EmuELEC, dan pengujian lokal (Windows/Linux) berbagi satu core engine Python (`host/core/`). Perbedaan platform hanya ada di `host/adapters/<platform>/`.
2. **Event-Driven (Tanpa Polling Frontend):** LED berubah langsung ketika pengguna menyorot game di EmulationStation, tanpa menunggu game dijalankan dan tanpa polling RetroArch.
3. **Non-Blocking di EmulationStation:** Script adapter selalu berjalan di background (`&`) dan tidak memuat logika pencocokan game atau I/O serial secara langsung.
4. **Satu Firmware Teruji (`ARCADELED_V1`):** Raspberry Pi Pico menjalankan sketch Arduino-Pico ([pico/arcadeled_pico/arcadeled_pico.ino](../pico/arcadeled_pico/arcadeled_pico.ino)) yang sekaligus berfungsi sebagai **USB HID Joystick 4 tombol** dan **USB Serial LED Controller 4 channel**.
5. **Ringan & Mudah Diuji:** Core engine dan `MockTransport` berjalan murni dengan Python 3 standard library; `pyserial` hanya dipakai saat menggunakan `SerialTransport`.

---

## 2. Diagram Alur Sistem

```text
             BATOCERA                               EMUELEC
                 |                                     |
   host/adapters/batocera/               host/adapters/emuelec/
      game_selected.sh                 adapter_placeholder.sh (probe)
                 |                                     |
                 +------------------+------------------+
                                    |
                                    v
                  +------------------------------------+
                  |     host/main.py (CLI / Daemon)    |
                  |   Local TCP IPC + Scroll Debounce  |
                  +-----------------+------------------+
                                    |
                                    v
                  +------------------------------------+
                  |      ARCADELED CORE ENGINE         |
                  |  1. event_model.py (Normalize)     |
                  |  2. event_logger.py (Log .log/.jsonl)
                  |  3. game_resolver.py (Match ROM)   |
                  |  4. profile_manager.py (LED1..4)   |
                  |  5. event_processor.py (Dedup/Tx)  |
                  +-----------------+------------------+
                                    |
                                    v
                  +------------------------------------+
                  |     TRANSPORT ABSTRACTION          |
                  |  pico_discovery.py (Win & Linux)   |
                  |  serial_transport.py (ARCADELED_V1)|
                  |  mock_transport.py   (Simulator)   |
                  +-----------------+------------------+
                                    |  ASCII Serial 115200 8N1
                                    |  HELLO / LED1..4 ON|OFF / ALL ON|OFF
                                    v
                  +------------------------------------+
                  |    RASPBERRY PI PICO FIRMWARE      |
                  |  pico/arcadeled_pico/              |
                  |    arcadeled_pico.ino              |
                  |  - USB HID Joystick (GPIO 2..5)    |
                  |  - LED Output Driver (GPIO 6..9)   |
                  +-----------------+------------------+
                                    |
                                    v
                        4 ARCADE BUTTON LEDs
```

---

## 3. Tanggung Jawab Komponen

### Platform Adapters (`host/adapters/`)
- Menangkap argumen mentah dari EmulationStation (`$1` system, `$2` ROM path, `$3` game name).
- Mengirim event ke `host/main.py emit --forward-to-daemon` di background agar scrolling UI tetap mulus.

### CLI & Local Daemon (`host/main.py`)
- `daemon`: menjalankan TCP server lokal (`127.0.0.1:19876`) yang menjaga koneksi serial tetap terbuka dan melakukan scroll debouncing (`debounce_ms`, default `100 ms`).
- `emit`: mengirim satu event game (mencoba meneruskan ke daemon jika aktif, atau memproses langsung).
- `test-pico`: menjalankan uji koneksi handshake & pola LED pada hardware Pico.
- `simulate`: menjalankan simulasi lengkap tanpa hardware memakai `MockTransport`.
- `stdin`: membaca stream JSON per baris dari stdin.

### Core Engine (`host/core/`)
| Modul | Tanggung Jawab |
| --- | --- |
| `event_model.py` | Memvalidasi dan menormalisasi event ke objek `GameEvent`. |
| `event_logger.py` | Menulis log real-time ke konsol, `host/logs/events.log`, dan `host/logs/events.jsonl`. |
| `game_resolver.py` | Mencocokkan game dengan urutan prioritas: `exact_rom` -> `stem_rom` -> `game_name`/alias -> `system_fallback` -> `default`. |
| `profile_manager.py` | Mengelola profil 4 LED (`LED1`–`LED4`), menggabungkan override per game, membuat signature deduplikasi, dan menyusun baris perintah `ARCADELED_V1`. |
| `event_processor.py` | Menghubungkan resolver, profile manager, logger, deduplikasi, dan transport. |

### Transport Layer (`host/transports/`)
- `pico_discovery.py`: mendeteksi port Pico secara otomatis di Windows (`COMx` via VID `0x2E8A`) dan Linux (`/dev/ttyACM*` & `/dev/serial/by-id`).
- `serial_transport.py`: membuka port serial, melakukan handshake `HELLO` -> `ARCADELED_V1`, mengirim perintah `ALL ON`/`ALL OFF`/`LED1..4 ON|OFF`, serta auto-reconnect saat disconnect/timeout.
- `mock_transport.py`: meniru perilaku `processCommand()` milik `arcadeled_pico.ino` lengkap dengan injeksi error untuk unit test.
