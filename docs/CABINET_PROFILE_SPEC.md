# CABINET_PROFILE_SPEC — Spesifikasi Konfigurasi Hardware Cabinet

Dokumen ini mendefinisikan format **Cabinet Hardware Profile** yang memisahkan kapabilitas fisik mesin arcade dari metadata game.

---

## 1. Tujuan Pemisahan

Metadata game bersifat **universal** (Street Fighter II selalu 2 pemain, 6 tombol), sedangkan **Cabinet Profile** bersifat **spesifik per perangkat milik user**:
- Prototipe **ArcadeLED V1** saat ini memiliki **1 set kontrol (4 tombol aksi, GP2–GP5, dan 4 LED, GP6–GP9)**.
- Cabinet arcade 2-pemain penuh umumnya memiliki **2 joystick 8-way, 6 tombol/pemain, Start P1/P2, Coin**, serta opsional **trackball / spinner**.

Dengan memisahkan `cabinet_profile.json`, logika analisis game tidak perlu diubah ketika hardware berkembang dari V1 (4 LED) ke V2 (16+ LED / WS2812B).

---

## 2. Contoh Konfigurasi: ArcadeLED V1 (Prototipe Saat Ini)

```json
{
  "cabinet": {
    "name": "ArcadeLED V1 Prototype (1P 4-Button)",
    "players": 1,
    "controllers": [
      {
        "player": 1,
        "joystick": "digital_8way",
        "buttons": 4,
        "led_channels": ["LED1", "LED2", "LED3", "LED4"]
      }
    ],
    "extra_controls": [],
    "extra_buttons": [],
    "fallback_policy": {
      "when_missing_special_control": "map_action_buttons_only",
      "when_buttons_exceed_cabinet": "clamp_to_available",
      "when_zero_action_buttons": "all_off"
    }
  }
}
```

---

## 3. Contoh Konfigurasi: Cabinet 2-Player Standar + Trackball

```json
{
  "cabinet": {
    "name": "Full 2P Cabinet + Trackball",
    "players": 2,
    "controllers": [
      {
        "player": 1,
        "joystick": "digital_8way",
        "buttons": 6,
        "led_channels": ["P1_B1", "P1_B2", "P1_B3", "P1_B4", "P1_B5", "P1_B6"]
      },
      {
        "player": 2,
        "joystick": "digital_8way",
        "buttons": 6,
        "led_channels": ["P2_B1", "P2_B2", "P2_B3", "P2_B4", "P2_B5", "P2_B6"]
      }
    ],
    "extra_controls": [
      {
        "type": "trackball",
        "led_channels": ["TRACKBALL_LED"]
      }
    ],
    "extra_buttons": [
      { "id": "START_P1", "led_channel": "LED_START_1" },
      { "id": "START_P2", "led_channel": "LED_START_2" },
      { "id": "COIN", "led_channel": "LED_COIN" }
    ],
    "fallback_policy": {
      "when_missing_special_control": "map_action_buttons_only",
      "when_buttons_exceed_cabinet": "clamp_to_available",
      "when_zero_action_buttons": "indicator_only"
    }
  }
}
```

---

## 4. Matriks Penanganan Ketidakcocokan (*Mismatch Handling*)

| Skenario Ketidakcocokan | Contoh | Kebijakan Penanganan |
| --- | --- | --- |
| **Game > Players Cabinet** | `trackfld` (4P) di cabinet 1P/2P | Ambil P1..`cabinet.players`; pemain ekstra diabaikan tanpa error. |
| **Game > Buttons Cabinet** | `sf2` (6 tombol) di ArcadeLED V1 (4 tombol) | `clamp_to_available`: aktifkan 4 tombol yang tersedia + catat warning `missing_2_buttons`. |
| **Game Butuh Trackball/Dial/Lightgun, Cabinet Tidak Punya** | `gt3d`, `arkanoid`, `timecris` di cabinet joystick biasa | `map_action_buttons_only`: tetap nyalakan LED tombol aksi (`buttons`), catat `missing_hardware: trackball/dial/lightgun`. |
| **Game 0 Tombol Aksi** | `pacman` (`buttons=0`) | `all_off` pada ArcadeLED V1 (karena tidak ada LED Start/Joystick), atau `indicator_only` (nyalakan `START_P1`/`COIN`/Joystick LED) pada cabinet penuh. |
| **Game Steering + Pedal** | `daytona` (`paddle` + `pedal`, `buttons=9`) | Jika tidak ada setir/pedal, `clamp_to_available` pada tombol aksi dan beri catatan bahwa kontrol analog tidak tersedia. |

