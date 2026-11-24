# LED_MAPPING_DESIGN — Strategi Konversi Metadata ke Pola LED

Dokumen ini menjelaskan bagaimana hasil pencocokan **Controller Mapping Engine** diterjemahkan menjadi status LED fisik pada Raspberry Pi Pico, dengan membedakan makna setiap indikator LED.

---

## 1. Empat Jenis Makna Pencahayaan LED

Tidak semua tombol yang ada di cabinet harus menyala bersamaan. ArcadeLED memisahkan 4 peran LED:

1. **Tombol Tersedia (*Hardware Available*)**: Seluruh tombol fisik yang terpasang di cabinet (berguna untuk mode *attract/idle* di menu utama, bukan saat game spesifik dipilih).
2. **Tombol Diperlukan Game (*Active Action Buttons*)**: Hanya tombol aksi yang benar-benar dipakai oleh game (misal `LED1..LED3` ON dan `LED4` OFF untuk `mslug`). **Ini adalah mode utama saat browsing game.**
3. **Fungsi / Warna Tombol (*Functional Coloring*)**: Untuk hardware RGB (`WS2812B` di V2+), warna LED merepresentasikan fungsi (mis. Neo Geo: Merah/Kuning/Hijau/Biru; Street Fighter: Punch vs Kick).
4. **Indikator Pemain & Kontrol Khusus (*Player & Special Indicators*)**:
   - Menyalakan `START_P1` saja untuk game 1P atau `START_P1` + `START_P2` untuk game 2P simultan.
   - Menyalakan `COIN` jika `coins > 0` pada metadata MAME.
   - Menyalakan LED Trackball / Spinner / Joystick hanya jika hardware tersebut dipakai oleh game.

---

## 2. Opsi Strategi Pencahayaan (*Lighting Strategies*)

Sistem mendukung pemilihan strategi di konfigurasi tanpa mengubah parser MAME:

| Strategi | Perilaku | Cocok Untuk |
| --- | --- | --- |
| **`minimal_required` (Default)** | Hanya menyalakan sejumlah `min(required_buttons, cabinet_buttons)` untuk pemain aktif. Tombol lain dimatikan (`OFF`). | **ArcadeLED V1** (4 LED single-color) — paling jelas menunjukkan tombol mana yang dipakai. |
| **`active_plus_meta`** | Menyalakan tombol aksi aktif + `START_P1`/`START_P2` sesuai `simultaneous_players` + `COIN` jika `coins > 0` + indikator kontrol khusus (`trackball`/`dial`). | Cabinet 2P lengkap dengan tombol Start/Coin/Trackball ber-LED. |
| **`all_available_on`** | Menyalakan semua tombol yang terpasang pada pemain aktif. | Mode kompatibilitas atau attract mode. |

---

## 3. Contoh Hasil Pemetaan pada ArcadeLED V1 (4 LED: `LED1..LED4`)

Dengan profil **ArcadeLED V1 (1P, 4 tombol)** dan strategi `minimal_required`:

| Game | Kebutuhan Game | Output `LED1..LED4` | Perintah Serial `ARCADELED_V1` | Catatan |
| --- | --- | --- | --- | --- |
| **Metal Slug** (`mslug` + override) | 3 tombol | `ON, ON, ON, OFF` | `LED1 ON`, `LED2 ON`, `LED3 ON`, `LED4 OFF` | Tombol ke-4 mati karena gameplay 3 tombol |
| **Street Fighter II** (`sf2`) | 6 tombol | `ON, ON, ON, ON` | `ALL ON` | Di-clamp ke 4 tombol fisik yang tersedia |
| **Pac-Man** (`pacman`) | 0 tombol (4-way joy) | `OFF, OFF, OFF, OFF` | `ALL OFF` | Tidak ada tombol aksi yang diperlukan |
| **Galaga** (`galaga`) | 1 tombol (2-way joy) | `ON, OFF, OFF, OFF` | `LED1 ON`, `LED2 OFF`, `LED3 OFF`, `LED4 OFF` | Hanya tombol tembak yang menyala |
| **Track & Field** (`trackfld`) | 3 tombol (`only_buttons`) | `ON, ON, ON, OFF` | `LED1 ON`, `LED2 ON`, `LED3 ON`, `LED4 OFF` | Run L, Jump, Run R |
| **Arkanoid** (`arkanoid`) | Dial + 1 tombol | `ON, OFF, OFF, OFF` | `LED1 ON`, `LED2 OFF`, `LED3 OFF`, `LED4 OFF` | Fallback: 1 tombol aksi menyala |
| **Golden Tee 3D** (`gt3d`) | Trackball + 2 tombol | `ON, ON, OFF, OFF` | `LED1 ON`, `LED2 ON`, `LED3 OFF`, `LED4 OFF` | Fallback: 2 tombol aksi menyala |
| **Time Crisis** (`timecris`) | Lightgun + 2 tombol | `ON, ON, OFF, OFF` | `LED1 ON`, `LED2 ON`, `LED3 OFF`, `LED4 OFF` | Fallback: 2 tombol aksi menyala |

---

## 4. Evolusi Protokol Serial Pico (V1 → V2)

- **V1 (Saat ini di [arcadeled_pico.ino](file:///Users/mac/AccessPoint/Event-Led-Game-Select/pico/arcadeled_pico/arcadeled_pico.ino)):**
  - Perintah teks: `HELLO` → `ARCADELED_V1`, `LED1..4 ON/OFF`, `ALL ON`, `ALL OFF`.
  - Sangat stabil dan mudah di-debug untuk 4–8 LED via MOSFET.
- **V2 (Masa depan jika pakai Shift Register / WS2812B):**
  - Tambahkan perintah bitmask atau RGB di firmware tanpa memutus kompatibilitas V1, misalnya:
    - `MASK <hex>` (untuk 8–32 LED on/off sekaligus dalam 1 baris serial).
    - `RGB <index> <rrggbb>` atau `FRAME <hex...>` (untuk WS2812B per tombol).

