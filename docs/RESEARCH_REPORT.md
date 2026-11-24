# RESEARCH REPORT — ArcadeLED Controller & Input Detection System

**Tanggal Riset:** 2026-11-20  
**Target Sistem:** Batocera, EmuELEC, EmulationStation, MAME, RetroArch, Raspberry Pi Pico (`ARCADELED_V1`)

---

## 1. Ringkasan Eksekutif

Riset ini menginvestigasi metode otomatis terbaik bagi **ArcadeLED** untuk mendeteksi kebutuhan kontrol setiap game **sebelum game dijalankan** (saat pengguna menyorot game di daftar EmulationStation), memetakkannya terhadap kemampuan fisik cabinet, dan menghasilkan pola pencahayaan LED tombol melalui Raspberry Pi Pico.

Temuan utama berdasarkan inspeksi langsung pada **Batocera.linux 43.1** (`MAME 0.285`), dokumentasi resmi MAME, Libretro API, serta arsitektur EmulationStation:

1. **Deteksi otomatis untuk game MAME/Arcade sangat layak dilakukan secara offline** menggunakan output `mame -listxml` yang di-cache secara lokal, namun **MAME XML saja tidak cukup** untuk membedakan tombol yang *tersedia di hardware board* vs tombol yang *benar-benar dipakai oleh game* (contoh: `mslug` melaporkan `buttons="4"` karena standar Neo Geo MVS memiliki 4 tombol, padahal gameplay hanya memakai 3 tombol) serta tidak menyediakan label fungsi tombol (`Jump`, `Fire`, `Punch`).
2. **EmulationStation (`gamelist.xml`) tidak menyimpan metadata kontrol/tombol**, melainkan hanya path ROM, nama game, dan deskripsi umum. Namun Batocera (v33+) dan fork EmuELEC yang mendukung `Scripting.cpp` menyediakan hook `game-selected` yang mengirim argumen sistem dan path ROM secara real-time saat user menggeser daftar game.
3. **Lima konsep yang wajib dipisahkan** dalam arsitektur data:
   - *Players supported* (jumlah pemain yang didukung game, termasuk bergantian/alternating seperti Pac-Man).
   - *Controllers required* (jumlah kontroler fisik yang dibutuhkan bersamaan).
   - *Cabinet controllers installed* (kontroler yang benar-benar terpasang di cabinet).
   - *Buttons available per controller* (jumlah tombol fisik di cabinet).
   - *Inputs actually used by the game* (jumlah dan fungsi tombol yang dipakai game).
4. **Arsitektur terbaik untuk MVP dan jangka panjang** adalah **Hybrid Resolver**: `MAME XML (offline cache)` + `Controls Override / Database (controls.xml / overrides.json)` + `System Default Profiles` (untuk konsol NES/SNES/Mega Drive/PS1/dll), dipadukan dengan `Cabinet Hardware Profile` terpisah dan `LED Mapping Strategy` yang menghasilkan perintah serial ke Raspberry Pi Pico.

---

## 2. Perbandingan Konsep Inti (5 Dimensi Berbeda)

| Dimensi | Contoh Kasus Nyata (`MAME 0.285`) | Implikasi untuk ArcadeLED |
| --- | --- | --- |
| **Players Supported** | `pacman` memiliki `players="2"` | Game 2 pemain *bergantian*, bukan 2 pemain simultan. |
| **Controllers Required** | `pacman` (upright) cukup 1 joystick dipakai bergantian; `sf2` butuh 2 controller simultan | Jangan langsung menyalakan LED Player 2 hanya karena `players="2"`. |
| **Cabinet Controllers Installed** | Cabinet hanya punya 2 joystick 8-way | Jika game `trackfld` (`players="4"`), cabinet hanya memetakan P1 & P2. |
| **Buttons Available per Controller** | Cabinet punya 6 tombol per player | Pada game 3 tombol, 3 tombol sisanya harus bisa dimatikan/redup. |
| **Inputs Used by Game** | `mslug` di MAME XML tercatat `buttons="4"` (hardware MVS), tapi gameplay hanya memakai 3 tombol (Shoot, Jump, Bomb) | Perlu layer override/database fungsi tombol agar akurasi LED tidak sekadar menyalakan port hardware kosong. |

---

## 3. Evaluasi Database Eksternal

| Sumber / Database | Data yang Tersedia | Format & Akses | Akurasi & Kelengkapan | Lisensi & Offline | Catatan Kritis |
| --- | --- | --- | --- | --- | --- |
| **MAME `-listxml`** | `players`, `control@type`, `ways`, `buttons`, `coins`, `service`, `cloneof` | XML dari binary `mame` | Sangat lengkap untuk semua mesin MAME; akurat secara *hardware port* | GPL-2.0+ (binary MAME); **100% offline** | Tidak ada label fungsi tombol; `buttons` mencerminkan wiring board (mis. Neo Geo = 4). |
| **`controls.dat` / `controls.xml`** | Label fungsi per tombol (`P1_BUTTON1="Light Punch"`), `numPlayers`, `alternating`, `mirrored`, `miscDetails` | XML / INI komunitas (fork GitHub seperti `AndyHazz/controls.xml-with-extra-buttons`) | Sangat akurat untuk game klasik, namun stagnan untuk game MAME baru | Dibagikan bebas / Apache-2.0 pada fork komunitas; **100% offline** | Situs asli offline; cocok dijadikan layer pengaya (*enrichment*) di atas MAME XML. |
| **Arcade Database (ADB)** (`adb.arcadeitalia.net`) | `players`, `nplayers`, `input_controls`, `input_buttons`, `buttons_colors` | REST API (`service_scraper.php`) | Tinggi untuk MAME (menggabungkan MAME XML + `nplayers.ini` + `colors.ini`) | Layanan web; **butuh internet** (1 koneksi/IP) | Tidak cocok untuk runtime offline tanpa pre-cache/export lokal. |
| **Libretro Database (`libretro-database`)** | `name`, `users`/`players`, `genre`, CRC32/SHA1 (`.dat` / `.rdb`) | Clrmamepro `.dat` & biner `.rdb` | Baik untuk identifikasi ROM konsol & jumlah `users` di sebagian sistem | MIT / CC0 / Data komunitas; **100% offline** | **Tidak menyimpan jumlah tombol atau jenis kontrol arcade** secara konsisten; tidak cukup untuk LED mapping. |
| **RetroArch `retro_input_descriptor`** | Deskripsi label tombol per port (`port`, `device`, `id`, `description`) | C struct runtime di core Libretro | Akurat sesuai core yang berjalan | GPL/MIT tergantung core | **Hanya tersedia saat core sudah me-load game** (`retro_load_game()`), tidak tersedia sebelum game dijalankan. |

---

## 4. Analisis Hardware Raspberry Pi Pico & Pendekatan LED

Berdasarkan datasheet RP2040 (Raspberry Pi Ltd):
- **Batas arus per pin GPIO:** Drive strength dapat dikonfigurasi 2 mA, 4 mA, 8 mA, atau **maksimal 12 mA** per pin untuk menjaga level tegangan logika valid (3.3 V).
- **Batas arus total GPIO + QSPI:** Maksimal **50 mA kumulatif** pada seluruh pin VDD/VSS chip RP2040.
- **Implikasi langsung:** GPIO RP2040 **tidak boleh** menggerakkan lampu tombol arcade 5 V / 12 V secara langsung. Diperlukan driver eksternal (MOSFET N-channel logic-level seperti 2N7002/IRLZ44N dengan resistor gate 220 Ω + pull-down 10 kΩ, atau IC driver seperti ULN2803A) dengan suplai eksternal yang ground-nya disatukan ke GND Pico.

### Perbandingan 3 Pendekatan Pengendalian LED

| Kriteria | 1. GPIO Langsung + MOSFET | 2. Shift Register (`74HC595`) + Driver | 3. Addressable RGB (`WS2812B` / NeoPixel) |
| --- | --- | --- | --- |
| **Pin Pico yang dibutuhkan** | 1 GPIO per LED (saat ini GP6–GP9 = 4 LED) | 3 GPIO (`DATA`, `CLOCK`, `LATCH`) untuk 8–32+ LED | 1 GPIO (`DATA`) untuk puluhan/ratusan LED |
| **Jumlah LED realistis** | 4–16 LED (terbatas sisa GPIO setelah tombol) | 8–32+ LED (daisy-chain 74HC595 + ULN2803A) | 10–100+ LED (RGB per tombol + marquee) |
| **Kontrol warna & animasi** | On/Off (atau PWM terbatas) | On/Off (atau PWM software) | Penuh RGB 24-bit per tombol (warna Neo Geo / SF2) |
| **Kebutuhan daya** | Suplai eksternal 5V/12V sesuai lampu tombol | Suplai eksternal 5V/12V sesuai beban LED | **Wajib suplai 5V eksternal** (maks ~60 mA/LED putih penuh; 10 LED = 600 mA) + level shifter 3.3V→5V disarankan |
| **Kompleksitas PCB & Firmware** | Sangat sederhana (cocok untuk **ArcadeLED V1**) | Menengah (butuh IC 74HC595 + array driver) | Sederhana di PCB, butuh library PIO/NeoPixel di Pico |

**Rekomendasi Hardware:**
- Untuk **ArcadeLED V1 (4–8 tombol single-color 5V/12V):** Pendekatan **GPIO langsung + MOSFET N-channel** (yang sudah Anda rancang) adalah paling tepat, minim komponen, dan terisolasi aman dari batas 50 mA RP2040.
- Untuk **V2 (Cabinet 2P × 6–8 tombol + Start/Coin + warna per tombol):** Gunakan **WS2812B** (1 pin GPIO) atau **74HC595 + ULN2803A** (3 pin GPIO). Protokol serial di sisi host dapat tetap abstrak (`LED1 ON` atau `SET_LEDS ...` / `SET_RGB ...`).

---

## 5. Test Matrix Verifikasi (MAME 0.285 Aktual di Batocera 43.1)

Semua data berikut diekstrak langsung dari `/usr/bin/mame/mame -listxml <shortname>` (MAME `0.285`) pada mesin Batocera `192.168.1.66`:

| Game (Shortname) | Jenis Kontrol | Sumber Metadata | Data Input Aktual MAME 0.285 XML | Pemain | Kontrol & Tombol | Keterbatasan Metadata | Keyakinan |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **Street Fighter II** (`sf2`) | Fighting | MAME 0.285 `-listxml sf2` | `players="2" coins="2" service="yes"`, P1 & P2 `type="joy" buttons="6" ways="8"` | 2 | Joystick 8-way, 6 tombol/pemain | Tidak ada nama pukulan/tendangan (LP/MP/HP/LK/MK/HK) | **Tinggi** |
| **Metal Slug** (`mslug`) | Run and gun | MAME 0.285 `-listxml mslug` | `players="2" coins="2" service="yes"`, P1 & P2 `type="joy" buttons="4" ways="8"` | 2 | Joystick 8-way, XML lapor 4 tombol/pemain | MAME lapor 4 tombol (standar MVS), game sebenarnya hanya pakai 3 tombol aksi | **Sedang-Tinggi** (perlu override 3 tombol) |
| **Pac-Man** (`pacman`) | Maze | MAME 0.285 `-listxml pacman` | `cloneof="puckman"`, `players="2" coins="2"`, P1 & P2 `type="joy" ways="4"` (tanpa `buttons`) | 2 (bergantian) | Joystick 4-way, 0 tombol aksi | `players="2"` tidak membedakan simultan vs bergantian | **Tinggi** |
| **Galaga** (`galaga`) | Shooter | MAME 0.285 `-listxml galaga` | `players="2" coins="2"`, P1 & P2 `type="joy" buttons="1" ways="2"` | 2 (bergantian) | Joystick 2-way (kiri/kanan), 1 tombol | `players="2"` tidak membedakan simultan vs bergantian | **Tinggi** |
| **Track & Field** (`trackfld`) | Button-based | MAME 0.285 `-listxml trackfld` | `players="4" coins="2"`, P1–P4 `type="only_buttons" buttons="3"` | 4 | Tanpa joystick (`only_buttons`), 3 tombol/pemain | Tidak menjelaskan fungsi tombol (Run L, Jump, Run R) | **Tinggi** |
| **Arkanoid** (`arkanoid`) | Paddle/Dial | MAME 0.285 `-listxml arkanoid` | `players="2" coins="2" tilt="yes"`, P1 & P2 `type="dial" buttons="1" min="0" max="255"` | 2 (bergantian) | Dial/Spinner (`dial`), 1 tombol | MAME menamainya `dial` (bukan `paddle`); 2P bergantian | **Tinggi** |
| **Golden Tee 3D Golf** (`gt3d`) | Trackball | MAME 0.285 `-listxml gt3d` | `players="2" coins="3" service="yes"`, P1 & P2 `type="trackball" buttons="2" min="0" max="255"` | 2 (bergantian) | Trackball, 2 tombol | Catatan: `gtg` adalah versi joystick (`ways="8"`), bukan trackball | **Tinggi** |
| **Daytona USA** (`daytona`) | Steering | MAME 0.285 `-listxml daytona` | `players="1" coins="2" service="yes"`, `type="paddle" buttons="9"` + `type="pedal"` (tanpa `player`) | 1 | Steering (`paddle` di MAME), `pedal`, 9 tombol | MAME pakai `paddle` untuk setir; `buttons="9"` mencakup shifter 4-speed & view | **Tinggi** |
| **Time Crisis** (`timecris`) | Light gun | MAME 0.285 `-listxml timecris` | `players="1" coins="1"`, `type="lightgun" buttons="2" min="43" max="284"` | 1 | Light gun, 2 tombol (Trigger + Pedal) | Pedal cover digabung sebagai button ke-2 di XML | **Tinggi** |

---

## 6. Jawaban Tegas atas 10 Pertanyaan Akhir

1. **Apakah ArcadeLED bisa mendeteksi jumlah pemain dan tombol secara otomatis?**  
   **Ya, untuk mayoritas game arcade (MAME/FBNeo)** melalui parsing `mame -listxml` offline, dan untuk konsol melalui profil per-sistem + override per-game. Namun deteksi *fungsi spesifik tombol* dan *tombol yang benar-benar dipakai vs wiring board* tetap membutuhkan database pengaya (`controls.xml` / file override).
2. **Apakah MAME XML cukup untuk kebutuhan tersebut?**  
   **Cukup untuk MVP deteksi kontrol arcade** (jenis kontrol, `ways`, jumlah pemain, ada/tidaknya coin/service, perkiraan jumlah tombol), **tetapi tidak cukup untuk akurasi 100%** pada kasus seperti Neo Geo (`buttons="4"` padahal pakai 3), game 2P bergantian (`pacman`, `galaga`), dan label fungsi tombol.
3. **Informasi apa yang tidak bisa didapatkan dari MAME XML?**  
   - Label/fungsi tiap tombol (`Jump`, `Punch`, `Kick`).
   - Apakah `players="2"` bersifat **simultan** atau **bergantian (alternating)**.
   - Tombol yang *aktif dipakai gameplay* vs tombol yang sekadar *terhubung di PCB/JAMMA* (kasus Neo Geo).
   - Warna tombol asli cabinet.
   - Input dari `dipswitch` atau kontrol khusus yang digabung ke `buttons` (mis. shifter Daytona USA).
4. **Apakah ada database eksternal yang lebih lengkap?**  
   **Tidak ada satu database tunggal yang sempurna dan aktif.** Kombinasi terbaik adalah **MAME `-listxml`** (paling lengkap & akurat secara teknis) + **`controls.xml` / `nplayers.ini`** (untuk label tombol & info simultan/bergantian) + **override lokal** (`games.json`).
5. **Bagaimana cara mendukung emulator selain MAME?**  
   Gunakan pendekatan berlapis per kategori emulator (lihat [EMULATOR_COMPATIBILITY.md](EMULATOR_COMPATIBILITY.md)):
   - **FBNeo:** Peta ke MAME XML (mayoritas shortname ROM identik).
   - **Konsol klasik (NES, SNES, Mega Drive, PS1):** Tidak ada metadata kontrol per-game di emulator; gunakan **profil default per sistem** (mis. NES = 2 tombol, SNES = 4/6 tombol, Mega Drive = 3/6 tombol) + override manual untuk game khusus (mis. game Light Gun / Mouse).
   - **Dolphin / PCSX2 / PPSSPP / Flycast:** Gunakan profil standar controller sistem tersebut (atau baca config mapping emulator jika tersedia).
6. **Bagaimana cara mendeteksi kebutuhan controller tanpa menjalankan game?**  
   Dengan mengekstrak **indeks JSON ringan** satu kali dari `mame -listxml` (pre-built index) + `controls.xml` + `games.json` lokal. Saat hook `game-selected` dari EmulationStation mengirim `system` dan `rom_path`, ArcadeLED Host cukup melakukan lookup O(1) di memori tanpa pernah menjalankan emulator.
7. **Bagaimana cara mencocokkan kebutuhan game dengan hardware cabinet?**  
   Melalui **Controller Mapping Engine** yang membandingkan `GameRequirements` vs `CabinetProfile` (jumlah pemain maksimum cabinet, jenis joystick, keberadaan trackball/spinner/lightgun, jumlah tombol fisik per pemain) dan menerapkan aturan *degradation/mapping* (lihat [CONTROLLER_MAPPING_DESIGN.md](CONTROLLER_MAPPING_DESIGN.md)).
8. **Bagaimana menangani game dengan kontrol khusus?**  
   Pisahkan tipe kontrol di internal schema (`dial`, `trackball`, `paddle`, `pedal`, `lightgun`, `only_buttons`). Jika cabinet **memiliki** hardware khusus tersebut, nyalakan LED indikator/tombolnya; jika **tidak memiliki**, terapkan kebijakan `fallback_policy` (misal: tetap nyalakan tombol aksi yang bisa di-remap ke joystick/mouse, atau nyalakan pola indikator khusus/peringatan).
9. **Apa metode paling realistis untuk MVP?**  
   - Tetap gunakan **hook `game-selected` EmulationStation (Batocera)** → **ArcadeLED Daemon**.
   - Tambahkan **MAME XML Indexer** (skrip offline yang mengubah `mame -listxml` menjadi `mame_controls.json` ringkas, dengan resolusi `cloneof` otomatis).
   - Gabungkan dengan `cabinet_profile.json` dan `games.json` (untuk override seperti `mslug` = 3 tombol, dan profil default konsol).
   - Kirim perintah serial sederhana ke Pico (`ARCADELED_V1` dengan MOSFET driver).
10. **Apa arsitektur terbaik untuk pengembangan jangka panjang?**  
    Arsitektur **4-Layer Decoupled Pipeline**:
    1. **Frontend Event Adapter** (Batocera ES hook, EmuELEC ES hook, dll)
    2. **Metadata Resolver** (`Override JSON` → `MAME/FBNeo Prebuilt Index` → `controls.xml/nplayers` → `System Default`)
    3. **Capability Matcher** (`GameRequirements` × `CabinetProfile` → `LogicalControlPlan`)
    4. **LED Strategy & Transport** (`LEDMappingStrategy` → `Serial/WS2812B/HID` ke Pico).

---

## 7. Daftar Sumber Resmi & Teknis

| Judul Sumber | URL | Bagian Relevan | Informasi Diperoleh | Tanggal Akses |
| --- | --- | --- | --- | --- |
| MAME Official Documentation — Command-line & Input System | https://docs.mamedev.org/commandline/commandline-all.html | `-listxml`, Input System | Spesifikasi output XML dan konsep `ioport`/control | 2026-11-20 |
| MAME Source Code (`infoxml.cpp`, `ioport.h`) | https://github.com/mamedev/mame | `src/frontend/mame/infoxml.cpp`, `src/emu/ioport.h` | Mekanisme serialisasi `<input>` dan `<control>` dari `ioport` | 2026-11-20 |
| MAME 0.285 Binary (Inspeksi Langsung di Batocera 43.1) | `/usr/bin/mame/mame` (`192.168.1.66`) | `-listxml` DTD & 9 game uji | DTD aktual `<input>`/`<control>` dan XML nyata 9 game | 2026-11-20 |
| Batocera Wiki — Launch a script | https://wiki.batocera.org/launch_a_script | EmulationStation `game-selected` | Lokasi `/userdata/system/configs/emulationstation/scripts/` dan argumen `$1`, `$2`, `$3` | 2026-11-20 |
| Libretro API (`libretro.h`) | https://github.com/libretro/libretro-common/blob/master/include/libretro.h | `retro_input_descriptor` | Keterbatasan bahwa label tombol baru tersedia saat core `retro_load_game()` | 2026-11-20 |
| Libretro Database | https://github.com/libretro/libretro-database | `.dat` & `.rdb` metadata | Ketersediaan field `users`/ROM hash dan ketiadaan detail tombol arcade | 2026-11-20 |
| Arcade Database (ADB) Scraper API | https://adb.arcadeitalia.net/service_scraper.php | `input_controls`, `input_buttons`, `nplayers` | Ketersediaan metadata input MAME via REST API | 2026-11-20 |
| Controls.dat / Community Forks | https://github.com/AndyHazz/controls.xml-with-extra-buttons | `controls.xml` | Label fungsi tombol & status `alternating`, lisensi komunitas | 2026-11-20 |
| Raspberry Pi RP2040 Datasheet | https://datasheets.raspberrypi.com/rp2040/rp2040-datasheet.pdf | Electrical Characteristics (GPIO) | Drive strength max 12 mA/pin, batas total 50 mA seluruh GPIO | 2026-11-20 |

