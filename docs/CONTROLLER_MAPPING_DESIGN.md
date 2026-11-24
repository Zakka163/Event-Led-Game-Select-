# CONTROLLER_MAPPING_DESIGN — Rancangan Controller Mapping Engine

Dokumen ini merancang **Controller Mapping Engine** yang mengubah metadata mentah (MAME XML, override lokal, profil sistem) menjadi spesifikasi kebutuhan kontrol game yang terstruktur, lalu mencocokkannya dengan kemampuan fisik cabinet.

---

## 1. Alur Pipeline Pemetaan

```text
[Event ES: system, rom_path, game_name]
                  │
                  ▼
      1. ROM & Game Identifier
   (shortname, stem, cloneof fallback)
                  │
                  ▼
      2. Metadata Resolver Chain
   Override (games.json) → MAME Index → System Default → Fallback
                  │
                  ▼
      3. Standard GameRequirements (JSON)
   (players_supported, simultaneous, controls[], coin, service)
                  │
                  ▼
      4. Capability Matcher (vs CabinetProfile)
   (cek jumlah player, tipe kontrol, jumlah tombol, fallback policy)
                  │
                  ▼
      5. LogicalControlPlan → LED Mapping Strategy → Pico
```

---

## 2. Schema Standar Internal (`GameRequirements`)

Format internal dirancang agar kompatibel dengan variasi MAME XML (termasuk atribut opsional seperti `player` atau `buttons` yang tidak selalu muncul):

```json
{
  "game": "Street Fighter II: The World Warrior (World 910522)",
  "system": "mame",
  "rom": "sf2",
  "cloneof": null,
  "metadata_source": "mame_xml",
  "confidence": "high",
  "players_supported": 2,
  "simultaneous_players": true,
  "controllers_required": 2,
  "coins": 2,
  "service": true,
  "controls": [
    {
      "player": 1,
      "type": "joy",
      "input_mode": "digital",
      "ways": 8,
      "buttons": 6,
      "button_labels": []
    },
    {
      "player": 2,
      "type": "joy",
      "input_mode": "digital",
      "ways": 8,
      "buttons": 6,
      "button_labels": []
    }
  ]
}
```

### Aturan Normalisasi dari MAME XML:
1. **`player` tidak ada** (contoh: `daytona`, `timecris`): isi otomatis `"player": 1`.
2. **`buttons` tidak ada** (contoh: `pacman`, atau `<control type="pedal">` pada `daytona`): isi otomatis `"buttons": 0`.
3. **Banyak `<control>` untuk 1 pemain** (contoh: `daytona` punya `paddle` + `pedal`): simpan semuanya di array `controls[]` agar tidak ada jenis kontrol khusus yang tertimpa.
4. **Klasifikasi `input_mode`**:
   - `digital`: `joy` (dengan `ways`), `only_buttons`, `positional`.
   - `analog`: `stick`, `paddle`, `pedal`.
   - `relative_optical`: `dial`, `trackball`.
   - `lightgun`: `lightgun`.
5. **Resolusi Clone**:
   - Cek `rom_stem` langsung di indeks MAME.
   - Jika tidak ditemukan di override lokal, cek `cloneof` (mis. `pacman` → `puckman`) saat mencari di database pengaya seperti `controls.xml`.

---

## 3. Penanganan Kasus Khusus & Data Tidak Lengkap

| Kasus | Contoh | Cara Engine Menangani |
| --- | --- | --- |
| **Hardware Port > Gameplay Buttons** | `mslug` (`buttons="4"` di MAME XML, gameplay 3 tombol) | Layer `games.json` / `controls_override` menimpa `buttons: 3` dengan `metadata_source: "mame_xml+override"`. |
| **Game 2P Bergantian** | `pacman`, `galaga`, `arkanoid`, `gt3d` | `players_supported = 2`, namun `simultaneous_players = false` dan `controllers_required = 1` (jika info `alternating` tersedia; jika tidak, default konservatif atau ikut kebijakan cabinet). |
| **Tanpa Tombol Aksi** | `pacman` (`buttons` tidak ada → `0`) | `buttons = 0`; LED tombol aksi bisa dimatikan semua (atau hanya menyalakan Start/Coin/Joystick indicator jika ada). |
| **Kontrol Khusus Tanpa Joystick** | `trackfld` (`only_buttons`, `buttons=3`) | Tandai `type: "only_buttons"` agar strategi LED tidak menyalakan indikator joystick jika cabinet punya LED joystick. |
| **ROM Konsol / Tidak Dikenal** | `snes/Super Mario World.sfc` | Resolver langsung turun ke `system_defaults["snes"]`, lalu `default_profile` jika sistem juga tidak dikenal. |

---

## 4. Capability Matching (`GameRequirements` vs `CabinetProfile`)

Engine membandingkan setiap kebutuhan kontrol game terhadap perangkat yang benar-benar terpasang di cabinet:

1. **Player Cap**: `active_players = min(game.controllers_required, cabinet.players)`.
   - Contoh: `trackfld` (`players=4`) pada cabinet 2-pemain → hanya memproses P1 & P2, mencatat `unmapped_players: [3, 4]`.
2. **Control Type Check**:
   - Cek apakah `control.type` tersedia pada slot pemain di `cabinet.controllers`.
   - Contoh: `gt3d` membutuhkan `trackball`. Jika cabinet punya `extra_controls: ["trackball"]`, status = `matched_special`. Jika tidak punya, status = `missing_special_control` dan terapkan `fallback_policy` cabinet (misal tetap petakan `buttons` ke tombol aksi P1 agar game masih bisa dimainkan via joystick/mouse).
3. **Button Cap**:
   - `mapped_buttons = min(control.buttons, cabinet_player.buttons)`.
   - Jika `control.buttons > cabinet_player.buttons` (mis. `sf2` butuh 6 tombol, cabinet hanya punya 4 tombol seperti ArcadeLED V1), nyalakan seluruh tombol yang tersedia (`4`) dan catat `truncated_buttons: 2` pada laporan diagnostik.

