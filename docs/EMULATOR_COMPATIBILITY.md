# EMULATOR_COMPATIBILITY — Matriks Kompatibilitas Batocera, EmuELEC, dan Emulator

Dokumen ini membandingkan mekanisme identifikasi game dan ketersediaan metadata kontrol sebelum game dijalankan pada **Batocera**, **EmuELEC**, **MAME**, **RetroArch**, serta emulator konsol/arcade lainnya.

---

## 1. Perbandingan Batocera vs EmuELEC

| Aspek | Batocera (Terverifikasi di v43.1) | EmuELEC |
| --- | --- | --- |
| **Identifikasi Game di ES** | EmulationStation mengirim `$1` (system), `$2` (full ROM path), `$3` (game display name) ke hook `game-selected` | Fork `emuelec-emulationstation` memiliki `Scripting.cpp` serupa, namun jalur/dukungan hook `game-selected` bergantung versi |
| **Lokasi Hook ES** | `/userdata/system/configs/emulationstation/scripts/game-selected/*.sh` (native sejak v33+) | `/storage/.emulationstation/scripts/game-selected/*.sh` (perlu verifikasi pada target device) |
| **Filesystem Userdata** | `ext4` (mendukung `chmod +x` langsung) | Root OS read-only; partisi `/storage` mendukung script jika permission valid |
| **Binary MAME Lokal** | `/usr/bin/mame/mame` (v0.285) tersedia langsung di sistem | Umumnya hanya mengandalkan core Libretro (`mame2003_plus`, `mame2010`, `fbneo`), tidak selalu ada standalone `mame` |
| **Metadata Kontrol di ES** | `gamelist.xml` **tidak** menyimpan jumlah tombol atau tipe joystick | Sama — `gamelist.xml` tidak menyimpan metadata kontrol |
| **API HTTP ES** | `http://127.0.0.1:1234/runningGame` hanya melapor game yang sedang *berjalan*, bukan yang *disorot* | Tidak ada API kontrol per-game saat browsing |

---

## 2. Klasifikasi Metadata Emulator

Sesuai standar riset, emulator diklasifikasikan ke dalam 4 kategori ketersediaan metadata **sebelum game dijalankan**:

| Emulator / Sistem | Kategori Metadata | Sumber Metadata Terbaik | Detail Input yang Bisa Diperoleh | Keterbatasan |
| --- | --- | --- | --- | --- |
| **MAME** (Standalone & `lr-mame`) | **Tersedia langsung** (via pre-built index `mame -listxml`) | `mame -listxml` + `controls.xml` | `players`, `control@type`, `ways`, `buttons`, `coins`, `service` | Tidak ada label tombol di XML; `buttons` = port hardware |
| **FBNeo / FinalBurn Alpha** | **Tersedia melalui database eksternal** (relasi ke MAME) | Indeks `mame -listxml` (mayoritas shortname ROM identik) + override `games.json` | Sama seperti MAME untuk romset arcade | Beberapa konsol di FBNeo (PCE, MD, Coleco) atau hack ROM tidak ada di MAME XML |
| **RetroArch** (Frontend) | **Hanya dari konfigurasi / saat runtime** | `retroarch.cfg`, core remap `.rmp`, atau `retro_input_descriptor` (saat game jalan) | Mapping RetroPad ke input host | `retro_input_descriptor` hanya aktif setelah `retro_load_game()` dipanggil; tidak tersedia saat browsing ES |
| **NES** (`nestopia`, `fceumm`) | **Tidak tersedia per-game → Profil sistem + manual** | Profil default sistem `nes` | 2 pemain, D-Pad (4/8-way), 2 tombol aksi (`B`, `A`) + Start/Select | Game khusus (Zapper Light Gun, Power Pad) perlu override manual |
| **SNES** (`snes9x`, `bsnes`) | **Tidak tersedia per-game → Profil sistem + manual** | Profil default sistem `snes` | 2 pemain, D-Pad, 4 face buttons + 2 shoulder (`L/R`) | Game Super Scope / Mouse perlu override manual |
| **Mega Drive / Genesis** (`genesisplusgx`) | **Tidak tersedia per-game → Profil sistem + manual** | Profil default sistem `megadrive` | 2 pemain, D-Pad, 3 tombol (`A, B, C`) atau 6 tombol (`X, Y, Z`) | Game 6-button (SF2 SCE, MK) perlu override profil `six_btn` |
| **PlayStation** (`pcsx_rearmed`, `duckstation`) | **Tidak tersedia per-game → Profil sistem + manual** | Profil default sistem `psx` | 2 pemain, D-Pad/DualShock, 4 face + 4 shoulder | Game Light Gun (Time Crisis PS1) / Steering perlu override |
| **Flycast** (Dreamcast / Naomi / Atomiswave) | **Campuran (Database eksternal + Profil sistem)** | Untuk Naomi/Atomiswave bisa cocokkan ke MAME XML; Dreamcast pakai profil sistem | Dreamcast: Analog + D-Pad + 4 face + 2 trigger | Tidak ada metadata per-game otomatis untuk Dreamcast ISO |
| **Dolphin** (GameCube / Wii) | **Profil sistem + konfigurasi** | Profil sistem + file `.ini` GameConfig Dolphin (jika ada) | GC: 2 analog + D-Pad + 4 face + Z + L/R | Wii memiliki variasi Wiimote/Nunchuk/Classic Controller per game |
| **PCSX2** (PS2) | **Profil sistem + manual** | Profil sistem `ps2` | DualShock 2 (analog + face + shoulder) | Tidak ada API metadata kontrol sebelum game jalan |
| **PPSSPP** (PSP) | **Profil sistem + manual** | Profil sistem `psp` | 1 pemain, Analog/D-Pad, 4 face + 2 shoulder | Single-player portabel; tidak ada metadata per-game di ES |

---

## 3. Kesimpulan Strategi Lintas Emulator

1. **Jangan memaksakan satu metode untuk semua emulator.**
2. **Arcade (`mame`, `fbneo`, `neogeo`, `cps1/2/3`, `naomi`, `atomiswave`):** Gunakan **MAME XML Index** offline sebagai tulang punggung utama, diperkaya dengan `controls.xml` / `games.json`.
3. **Konsol & Handheld (`nes`, `snes`, `megadrive`, `psx`, `psp`, `dreamcast`, `ps2`, `gc`):** Gunakan **System Default Profile** sebagai baseline yang konsisten dan cepat, dengan **Game Override** untuk judul spesial (Light Gun, 6-button fighting di Mega Drive, dsb.).
4. **Indeks Pre-Built Offline:** Karena EmuELEC dan banyak instalasi Batocera ARM tidak selalu menyertakan binary standalone `mame` yang cepat, indeks `mame_controls.json` sebaiknya **di-generate sekali** dari `mame -listxml` dan didistribusikan bersama ArcadeLED agar berjalan 100% offline di Batocera maupun EmuELEC.

