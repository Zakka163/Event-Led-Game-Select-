# ArcadeLED — Event-Led Game Select Controller

Kontroler tombol arcade berbasis **Raspberry Pi Pico** (USB HID Joystick + USB Serial) yang otomatis menyalakan LED tombol sesuai game yang disorot di **EmulationStation** (**Batocera**).

---

## Fitur Utama

- **Dual Mode di 1 Kabel USB (Raspberry Pi Pico):**
  - **USB HID Joystick:** 4 tombol arcade (`GPIO 2, 3, 4, 5`) dengan debounce `25 ms` terbaca langsung sebagai tombol gamepad `1–4`.
  - **USB Serial (`ARCADELED_V1`):** menerima perintah teks `115200 baud` untuk menyalakan/mematikan 4 LED (`GPIO 6, 7, 8, 9`) secara real-time melalui driver MOSFET N-channel.
- **Deteksi Pico Otomatis (Windows & Linux):**
  - Mengenali USB Vendor ID Raspberry Pi (`0x2E8A`), metadata port, fallback `/dev/serial/by-id` di Linux, serta verifikasi handshake `HELLO` -> `ARCADELED_V1`.
- **Event-Driven & Anti-Duplikasi:**
  - Memetakan game berdasarkan `ROM exact` -> `ROM stem` -> `nama/alias game` -> `fallback sistem` -> `profil default`.
  - Scroll debouncing di mode `daemon` dan deduplikasi agar tidak mengirim perintah berulang saat profil LED sama.
- **Analisis MAME XML & Cabinet Profile (Prototype):**
  - Mengekstrak kebutuhan pemain, jenis kontrol (`joy`, `only_buttons`, `dial`, `trackball`, `paddle`, `pedal`, `lightgun`), `ways`, dan jumlah tombol dari `mame -listxml`, lalu mencocokkannya dengan `CabinetProfile`.
- **Bisa Diuji Tanpa Hardware:**
  - Menyertakan `MockTransport` yang meniru protokol `ARCADELED_V1` secara penuh.

---

## Pemetaan Pin Hardware (Raspberry Pi Pico)

Sesuai firmware teruji di [pico/arcadeled_pico/arcadeled_pico.ino](pico/arcadeled_pico/arcadeled_pico.ino):

| Fungsi | Channel | Pin GPIO Pico | Mode | Keterangan |
| --- | --- | --- | --- | --- |
| Tombol 1 | Joystick Btn 1 | `GPIO 2` | `INPUT_PULLUP` | Hubungkan ke GND saat ditekan |
| Tombol 2 | Joystick Btn 2 | `GPIO 3` | `INPUT_PULLUP` | Hubungkan ke GND saat ditekan |
| Tombol 3 | Joystick Btn 3 | `GPIO 4` | `INPUT_PULLUP` | Hubungkan ke GND saat ditekan |
| Tombol 4 | Joystick Btn 4 | `GPIO 5` | `INPUT_PULLUP` | Hubungkan ke GND saat ditekan |
| LED 1 | `LED1` | `GPIO 6` | `OUTPUT` | Aktif `HIGH` (via MOSFET gate) |
| LED 2 | `LED2` | `GPIO 7` | `OUTPUT` | Aktif `HIGH` (via MOSFET gate) |
| LED 3 | `LED3` | `GPIO 8` | `OUTPUT` | Aktif `HIGH` (via MOSFET gate) |
| LED 4 | `LED4` | `GPIO 9` | `OUTPUT` | Aktif `HIGH` (via MOSFET gate) |

> **Catatan Kelistrikan:** GPIO RP2040 bekerja pada logika **3.3V** (maks 12 mA/pin, total 50 mA seluruh GPIO). Gunakan driver MOSFET N-channel (resistor gate `220 Ω` + pull-down `10 kΩ`) dan satukan GND suplai eksternal LED dengan GND Pico.

---

## Struktur Proyek

```text
Event-Led-Game-Select/
├── README.md                              # Dokumentasi utama proyek
├── requirements.txt                       # Dependensi Python (pyserial)
├── pico/
│   ├── README.md                          # Panduan upload Arduino IDE & hardware
│   └── arcadeled_pico/
│       └── arcadeled_pico.ino             # Firmware Raspberry Pi Pico (teruji)
├── host/
│   ├── main.py                            # CLI & daemon utama host
│   ├── config/
│   │   ├── settings.json                  # Konfigurasi serial, daemon & logging
│   │   └── games.json                     # Profil LED1..LED4 & pemetaan game
│   ├── core/
│   │   ├── event_model.py                 # Normalisasi & validasi event game
│   │   ├── event_logger.py                # Pencatatan log real-time (.log & .jsonl)
│   │   ├── game_resolver.py               # Pencocokan ROM / nama game / sistem
│   │   ├── profile_manager.py             # Penggabungan profil & perintah LED1..LED4
│   │   └── event_processor.py             # Pipeline pemrosesan event & deduplikasi
│   ├── transports/
│   │   ├── base_transport.py              # Antarmuka transport
│   │   ├── pico_discovery.py              # Auto-deteksi Pico (Windows & Linux)
│   │   ├── serial_transport.py            # Komunikasi USB Serial ARCADELED_V1
│   │   └── mock_transport.py              # Emulator ARCADELED_V1 tanpa hardware
│   ├── adapters/
│   │   └── batocera/game_selected.sh      # Hook EmulationStation Batocera
│   └── logs/                              # Output events.log & events.jsonl
├── prototype/
│   ├── mame_analyzer.py                   # Prototype MAME XML -> GameRequirements -> LED
│   ├── sample_mame.xml                    # Sampel MAME 0.285 XML (9 game uji + clone)
│   ├── cabinet_v1.json                    # Profil cabinet ArcadeLED V1 (1P 4-tombol)
│   ├── cabinet_2p_full.json               # Profil cabinet 2P penuh + trackball
│   └── overrides.json                     # Override gameplay buttons & alternating 2P
├── scripts/
│   ├── test_pico.py                       # Skrip uji cepat koneksi & LED Pico
│   └── install_batocera.sh                # Installer non-destruktif untuk Batocera
└── docs/
    ├── ARCHITECTURE.md                    # Arsitektur sistem lengkap
    ├── SERIAL_PROTOCOL.md                 # Spesifikasi protokol ARCADELED_V1
    ├── EVENT_COMPATIBILITY.md             # Matriks kompatibilitas event Batocera
    ├── RESEARCH_REPORT.md                 # Laporan riset Controller & Input Detection
    ├── MAME_METADATA_ANALYSIS.md          # Analisis DTD & input port MAME XML
    ├── EMULATOR_COMPATIBILITY.md          # Kompatibilitas metadata lintas emulator
    ├── CONTROLLER_MAPPING_DESIGN.md       # Rancangan Controller Mapping Engine
    ├── CABINET_PROFILE_SPEC.md            # Spesifikasi profil hardware cabinet
    └── LED_MAPPING_DESIGN.md              # Strategi konversi metadata ke pola LED
```

---

## Protokol Serial (`ARCADELED_V1`)

Baud rate: `115200` (8N1, diakhiri `\n`).

| Perintah (PC -> Pico) | Balasan (Pico -> PC) | Fungsi |
| --- | --- | --- |
| `HELLO` | `ARCADELED_V1` | Verifikasi identitas perangkat |
| `LED1 ON` .. `LED4 ON` | `OK` | Menyalakan LED tertentu (`1`–`4`) |
| `LED1 OFF` .. `LED4 OFF` | `OK` | Mematikan LED tertentu (`1`–`4`) |
| `ALL ON` | `OK` | Menyalakan semua LED (`LED1`–`LED4`) |
| `ALL OFF` | `OK` | Mematikan semua LED (`LED1`–`LED4`) |
| *(perintah tidak valid)* | `ERROR` | Penanda perintah ditolak |

Detail lengkap ada di [docs/SERIAL_PROTOCOL.md](docs/SERIAL_PROTOCOL.md).

---

## Panduan Cepat (Quick Start)

### 1. Upload Firmware ke Raspberry Pi Pico
1. Buka [pico/arcadeled_pico/arcadeled_pico.ino](pico/arcadeled_pico/arcadeled_pico.ino) di **Arduino IDE** (dengan core **Raspberry Pi Pico / RP2040** oleh Earle Philhower).
2. Pilih board Raspberry Pi Pico dan upload firmware.
3. **Tutup Serial Monitor / Serial Plotter** di Arduino IDE setelah selesai upload agar port tidak terkunci.

Lihat panduan lengkap di [pico/README.md](pico/README.md).

### 2. Install Dependensi Python (Host)
```bash
pip install -r requirements.txt
```
*(Untuk simulasi / prototype tanpa hardware, cukup Python 3 bawaan tanpa `pyserial`.)*

### 3. Uji Koneksi & LED pada Hardware Pico
```bash
python3 scripts/test_pico.py
# Atau tentukan port manual:
python3 scripts/test_pico.py /dev/ttyACM0
```

### 4. Simulasi & Prototype MAME XML Analyzer (Tanpa Hardware)
```bash
# Simulasi alur pilih game lengkap dengan MockTransport
python3 host/main.py simulate

# Analisis MAME XML -> Cabinet Profile -> LED Mapping
python3 prototype/mame_analyzer.py --all --cabinet prototype/cabinet_v1.json
python3 prototype/mame_analyzer.py --rom mslug --json
python3 prototype/mame_analyzer.py --rom gt3d --cabinet prototype/cabinet_2p_full.json
```

---

## Instalasi & Pengujian di Batocera (v33+)

```bash
# Preview tanpa mengubah file
bash scripts/install_batocera.sh --dry-run

# Instal host & hook game-selected
bash scripts/install_batocera.sh
```

### Menjalankan Daemon & Memantau Log di Batocera
Jika Pico **belum** tercolok, jalankan daemon dengan `--transport mock`:
```bash
python3 /userdata/system/arcadeled/host/main.py --transport mock daemon >/userdata/system/arcadeled/host/logs/daemon.log 2>&1 &
```
Jika Pico **sudah** tercolok, jalankan tanpa `--transport mock`:
```bash
python3 /userdata/system/arcadeled/host/main.py daemon >/userdata/system/arcadeled/host/logs/daemon.log 2>&1 &
```

Pantau game yang sedang dipilih secara real-time:
```bash
tail -f /userdata/system/arcadeled/host/logs/events.log
# atau format JSON:
tail -f /userdata/system/arcadeled/host/logs/events.jsonl
```

Menghentikan daemon background:
```bash
pkill -f "arcadeled/host/main.py daemon"
```

---

## Troubleshooting

- **`Access is denied` (Windows):** Tutup **Serial Monitor / Serial Plotter** di Arduino IDE atau aplikasi lain yang sedang membuka port `COMx`.
- **`Permission denied` pada `/dev/ttyACM0` (Linux):** Tambahkan user ke grup `dialout`, lalu login ulang:
  ```bash
  sudo usermod -aG dialout $USER
  ```
- **Hook `game-selected` belum terpanggil di Batocera:** Restart EmulationStation sekali lewat menu **Quit → Restart EmulationStation** setelah instalasi agar direktori `scripts/game-selected` dimuat.
- **`Pico tidak ditemukan!`:** Cek kabel USB (harus kabel data, bukan kabel charger saja) atau tentukan port manual lewat argumen CLI / environment variable `PICO_PORT`.
