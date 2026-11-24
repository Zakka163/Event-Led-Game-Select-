# ArcadeLED Serial Communication Protocol (`ARCADELED_V1`)

Spesifikasi protokol USB Serial yang **terverifikasi** pada firmware [pico/arcadeled_pico/arcadeled_pico.ino](../pico/arcadeled_pico/arcadeled_pico.ino) dan host [host/transports/serial_transport.py](../host/transports/serial_transport.py).

---

## 1. Spesifikasi Transport

| Parameter | Nilai |
| --- | --- |
| Antarmuka | USB CDC Serial (Raspberry Pi Pico, bersamaan dengan USB HID Joystick) |
| USB Vendor ID | `0x2E8A` (Raspberry Pi) |
| Port Windows | `COMx` (contoh: `COM4`, terdeteksi otomatis) |
| Port Linux | `/dev/ttyACM*` atau `/dev/serial/by-id/*` (terdeteksi otomatis) |
| Baud Rate | `115200` bps (`8N1`) |
| Framing | Teks ASCII satu baris, diakhiri `\n` (`0x0A`) atau `\r` (`0x0D`) |
| Panjang Maksimal Baris | `40` karakter pada buffer firmware |
| Case Sensitivity | Case-insensitive (firmware melakukan `trim()` dan `toUpperCase()`) |
| Jeda Inisialisasi Koneksi | `2.0` detik setelah port dibuka sebelum handshake `HELLO` |
| Timeout Default | `2.0` detik |
| Kebijakan Reconnect Host | Hingga `3` percobaan dengan jeda `0.5` detik |

---

## 2. Daftar Perintah (Host -> Pico)

### 2.1 Identifikasi Perangkat (`HELLO`)
Dikirim oleh host setiap kali koneksi dibuka untuk memastikan perangkat adalah controller ArcadeLED yang benar.

- **Request:** `HELLO\n`
- **Response:** `ARCADELED_V1\n`

### 2.2 Kontrol Semua LED (`ALL ON` / `ALL OFF`)
Menyalakan atau mematikan seluruh 4 LED (`LED1`–`LED4` pada `GPIO 6–9`) sekaligus.

- **Request:** `ALL ON\n` -> **Response:** `OK\n`
- **Request:** `ALL OFF\n` -> **Response:** `OK\n`

### 2.3 Kontrol LED Individual (`LED<1-4> ON` / `LED<1-4> OFF`)
Menyalakan atau mematikan satu LED tertentu (`n` bernilai `1` hingga `4`).

- **Request:** `LED1 ON\n` -> **Response:** `OK\n`
- **Request:** `LED1 OFF\n` -> **Response:** `OK\n`
- **Request:** `LED4 ON\n` -> **Response:** `OK\n`
- **Request:** `LED4 OFF\n` -> **Response:** `OK\n`

### 2.4 Respon Error
Jika perintah tidak dikenali, nomor LED di luar `1..4`, atau aksi bukan `ON`/`OFF`:

- **Response:** `ERROR\n`

---

## 3. Contoh Sesi Komunikasi

```text
[PC] HELLO    -> [PICO] ARCADELED_V1
[PC] LED1 ON  -> [PICO] OK
[PC] LED1 OFF -> [PICO] OK
[PC] ALL ON   -> [PICO] OK
[PC] ALL OFF  -> [PICO] OK
```

Saat host memproses perpindahan game:
- Profil semua nyala (`all_on`) -> host mengirim 1 baris ringkas: `ALL ON`
- Profil semua mati (`all_off`) -> host mengirim 1 baris ringkas: `ALL OFF`
- Profil campuran (mis. `three_btn`) -> host mengirim status eksplisit:
  ```text
  LED1 ON
  LED2 ON
  LED3 ON
  LED4 OFF
  ```

---

## 4. Reliabilitas & Deduplikasi

1. **Verifikasi Handshake:** `SerialTransport.connect()` wajib menerima `ARCADELED_V1` dari `HELLO`; jika bukan, port langsung ditutup dengan `TransportProtocolError`.
2. **Deduplikasi di Host:** `EventProcessor` menghitung hash SHA-256 dari status 4 LED. Jika game berikutnya memiliki pola LED yang sama, host melewati pengiriman serial (`SKIPPED_UNCHANGED`).
3. **Scroll Debouncing:** Pada mode `host/main.py daemon`, event scroll cepat dalam jendela `debounce_ms` (default `100 ms`) digabung sehingga hanya game terakhir yang dikirim ke Pico.
4. **Auto-Reconnect:** Jika kabel terputus atau terjadi timeout, `SerialTransport` menutup dan membuka ulang port serta melakukan handshake ulang hingga `reconnect_attempts`.
