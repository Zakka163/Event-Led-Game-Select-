# ArcadeLED — Firmware Raspberry Pi Pico (`ARCADELED_V1`)

Direktori ini berisi firmware Arduino-Pico yang **sudah diuji langsung pada perangkat Raspberry Pi Pico**.

- File sketch: [arcadeled_pico/arcadeled_pico.ino](arcadeled_pico/arcadeled_pico.ino)

---

## 1. Kebutuhan Arduino IDE

1. Install **Arduino IDE 2.x**.
2. Tambahkan Board Manager URL core RP2040 (Earle Philhower):
   ```text
   https://github.com/earlephilhower/arduino-pico/releases/download/global/package_rp2040_index.json
   ```
3. Install board package **Raspberry Pi Pico/RP2040** melalui Boards Manager.
4. Library `<Joystick.h>` sudah termasuk bawaan di core `arduino-pico`.
5. Buka [arcadeled_pico/arcadeled_pico.ino](arcadeled_pico/arcadeled_pico.ino), pilih board **Raspberry Pi Pico**, lalu klik **Upload**.

---

## 2. Pemetaan Pin GPIO (7 Tombol Input & 6 LED)

Firmware [arcadeled_pico.ino](arcadeled_pico/arcadeled_pico.ino) dikonfigurasi untuk **7 tombol input** (`6` tombol aksi + `1` tombol Start) dan **6 output LED** (`LED1`–`LED6` untuk `A, B, X, Y, L, R`):

| Fungsi | Channel / HID | Pin GPIO Pico | Keterangan |
| --- | --- | --- | --- |
| **A, B, X, Y, L, R** | `Joystick.button(1..6)` | `GP2, GP3, GP4, GP5, GP10, GP11` | `INPUT_PULLUP` (debounce 25 ms) |
| **Start** | `Joystick.button(7)` | `GP12` | `INPUT_PULLUP` (debounce 25 ms, tanpa LED) |
| **LED A, B, X, Y, L, R** | `LED1`–`LED6` | `GP6, GP7, GP8, GP9, GP16, GP17` | `OUTPUT` (aktif `HIGH`) |

---

## 3. Catatan Keamanan Kelistrikan

- Pin GPIO RP2040 bekerja pada **3.3V** dengan batas aman **≤ 12 mA per pin** dan total arus seluruh pin GPIO **≤ 50 mA**.
- Untuk LED indikator 3.3V biasa, selalu pasang resistor seri (misalnya `220 Ω` – `330 Ω`).
- Jika memakai lampu tombol arcade **5V** atau **12V**, jangan hubungkan langsung ke pin GPIO; gunakan transistor/MOSFET logic-level (mis. `2N7002` / `IRLZ44N`) atau IC driver (`ULN2803A`).

---

## 4. Perintah Serial (`115200` baud, diakhiri `\n` atau `\r`)

| Perintah | Balasan | Keterangan |
| --- | --- | --- |
| `HELLO` | `ARCADELED_V1` | Identifikasi perangkat |
| `ALL ON` | `OK` | Menyalakan `LED1`–`LED6` |
| `ALL OFF` | `OK` | Mematikan `LED1`–`LED6` |
| `LED1 ON` .. `LED6 ON` | `OK` | Menyalakan LED spesifik |
| `LED1 OFF` .. `LED6 OFF` | `OK` | Mematikan LED spesifik |
| *(lainnya)* | `ERROR` | Perintah tidak dikenali |

---

## 5. Pengujian Cepat

Tutup **Serial Monitor** di Arduino IDE terlebih dahulu, lalu jalankan dari root proyek:

```bash
python3 host/main.py test-pico
```
