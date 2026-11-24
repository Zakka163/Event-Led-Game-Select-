# MAME_METADATA_ANALYSIS — Analisis MAME XML & Input Port System

Dokumen ini membedah struktur aktual output `mame -listxml` berdasarkan **MAME 0.285** yang diverifikasi langsung di Batocera 43.1, serta hubungannya dengan sistem internal `ioport` MAME.

---

## 1. DTD Aktual Elemen `<input>` dan `<control>` (MAME 0.285)

Hasil ekstraksi langsung dari `/usr/bin/mame/mame -listxml sf2`:

```xml
<!ELEMENT input (control*)>
    <!ATTLIST input service (yes|no) "no">
    <!ATTLIST input tilt (yes|no) "no">
    <!ATTLIST input players CDATA #REQUIRED>
    <!ATTLIST input coins CDATA #IMPLIED>
    <!ELEMENT control EMPTY>
        <!ATTLIST control type CDATA #REQUIRED>
        <!ATTLIST control player CDATA #IMPLIED>
        <!ATTLIST control buttons CDATA #IMPLIED>
        <!ATTLIST control minimum CDATA #IMPLIED>
        <!ATTLIST control maximum CDATA #IMPLIED>
        <!ATTLIST control sensitivity CDATA #IMPLIED>
        <!ATTLIST control keydelta CDATA #IMPLIED>
        <!ATTLIST control reverse (yes|no) "no">
        <!ATTLIST control ways CDATA #IMPLIED>
        <!ATTLIST control ways2 CDATA #IMPLIED>
        <!ATTLIST control ways3 CDATA #IMPLIED>
```

### Temuan Penting dari DTD:
1. **Atribut `buttons` ada di `<control>`, bukan di `<input>`** pada MAME modern (0.285).
2. **`<control>` bersifat opsional untuk atribut `player` dan `buttons`**:
   - Jika game hanya 1 pemain (mis. `daytona`, `timecris`), atribut `player` sering **tidak ditulis** (implisit Player 1).
   - Jika game tidak memiliki tombol aksi (mis. `pacman`), atribut `buttons` **tidak ditulis** (implisit `0`).
3. **Atribut `name`, `mask`, `seq`, `analog` TIDAK ada di `-listxml`**:
   - Field-field tersebut berada di sistem internal **Input Port (`ioport.h`)** dan file konfigurasi runtime `.cfg`, bukan di output `-listxml`.

---

## 2. Makna Teknis Tipe Kontrol (`control@type`) di MAME

Berdasarkan `infoxml.cpp` dan hasil verifikasi game nyata:

| `control@type` | Makna Teknis di MAME | Atribut Khas | Contoh Game (MAME 0.285) |
| --- | --- | --- | --- |
| `joy` | Joystick digital (atau 2/4/8-way) | `ways` (`2`, `4`, `8`, `3`, `5`), `ways2`/`ways3` (double/triple joy), `buttons` | `sf2` (`ways="8" buttons="6"`), `pacman` (`ways="4"`), `galaga` (`ways="2" buttons="1"`) |
| `only_buttons` | Kontrol murni tombol tanpa joystick/axis | `buttons` | `trackfld` (`players="4"`, `buttons="3"`) |
| `dial` | Rotary encoder / spinner relatif (putaran tak terbatas) | `minimum`, `maximum`, `sensitivity`, `keydelta` | `arkanoid` (`buttons="1" min="0" max="255"`) |
| `paddle` | Potensiometer absolut (sudut terbatas, termasuk setir analog) | `minimum`, `maximum`, `sensitivity`, `keydelta` | `daytona` (`buttons="9" min="0" max="255"`) |
| `trackball` | Bola trackball 2-axis relatif | `minimum`, `maximum`, `sensitivity`, `keydelta`, `reverse` | `gt3d` (`buttons="2" min="0" max="255" reverse="yes"`) |
| `lightgun` | Sensor posisi X/Y layar absolut | `buttons`, `minimum`, `maximum`, `sensitivity` | `timecris` (`buttons="2" min="43" max="284"`) |
| `pedal` | Pedal analog (gas/rem) | `minimum`, `maximum`, `sensitivity` | `daytona` (muncul sebagai `<control>` terpisah) |
| `stick` | Joystick analog (potensiometer X/Y) | `minimum`, `maximum`, `buttons` | Game flight/star wars (mis. `starwars`) |
| `positional` | Tuas/switch posisi diskret (rotary/gear) | `ways`, `buttons` | Game dengan rotary switch mekanik |

---

## 3. MAME Input Port System (`ioport`) vs `-listxml`

Di dalam source code driver MAME (C++), setiap game mendefinisikan input menggunakan makro `INPUT_PORTS_START` dan `PORT_BIT`:
- `PORT_BIT( mask, active_low, IPT_BUTTON1 ) PORT_PLAYER(1) PORT_NAME("Light Punch")`
- `PORT_START` mengelompokkan port hardware.
- `infoxml.cpp` mengagregasi semua `ioport_field` tersebut menjadi ringkasan `<input>` dan `<control>` di `-listxml`.

**Mengapa detail `PORT_NAME` hilang di `-listxml`?**
Karena `-listxml` didesain sebagai katalog metadata mesin secara ringkas. Akibatnya:
- Kita tahu `sf2` punya `buttons="6"`, tetapi tidak tahu mana `Light Punch` dan mana `Heavy Kick` hanya dari `-listxml`.
- Untuk mendapatkan `PORT_NAME` langsung dari MAME, satu-satunya cara adalah membaca source code driver C++ atau menjalankan MAME dengan **Lua script** (`manager.machine.ioport.ports`) saat game di-load — yang tidak praktis saat user hanya menyorot game di EmulationStation.

---

## 4. Identifikasi ROM: Parent, Clone, dan Software List

Di XML `<machine>`:
```xml
<machine name="pacman" sourcefile="pacman/pacman.cpp" cloneof="puckman" romof="puckman" isbios="no" isdevice="no" runnable="yes">
```
- `name`: Shortname ROM (mis. `sf2ce`, `pacman`).
- `cloneof`: Jika ada, menunjuk ke parent ROM (`puckman`).
- `romof`: Menunjuk ke parent ROM atau BIOS (`neogeo` pada `mslug`).
- `isdevice="yes"` / `runnable="no"`: Perangkat internal (CPU, sound chip, cart slot) yang **harus diabaikan** saat mengindeks game.

**Aturan Resolusi Clone untuk ArcadeLED:**
1. Cari exact match berdasarkan `machine@name` (mis. `sf2ce` langsung ada di `-listxml` lengkap dengan `<input>`-nya).
2. Jika sebuah ROM kustom/hack tidak ada di indeks, fallback ke `cloneof` atau `romof` jika tersedia di metadata eksternal (mis. `controls.xml` sering hanya mendata *parent* ROM seperti `puckman` atau `sf2`, bukan semua klonnya).
3. **Software List** (untuk konsol/komputer di MAME seperti `nes`, `snes`, `megadrive`): `-listxml` hanya mendeskripsikan *mesin* konsolnya (mis. NES controller), bukan kebutuhan kontrol per cartridge di software list XML (`hash/*.xml`). Oleh karena itu, game konsol ditangani lewat layer profil sistem/game terpisah.

---

## 5. Data Aktual 9 Game Uji (MAME 0.285)

1. **`sf2`** — *Street Fighter II: The World Warrior*
   ```xml
   <input players="2" coins="2" service="yes" tilt="no">
       <control type="joy" player="1" buttons="6" ways="8" reverse="no" />
       <control type="joy" player="2" buttons="6" ways="8" reverse="no" />
   </input>
   ```
2. **`mslug`** — *Metal Slug - Super Vehicle-001* (`romof="neogeo"`)
   ```xml
   <input players="2" coins="2" service="yes" tilt="no">
       <control type="joy" player="1" buttons="4" ways="8" reverse="no" />
       <control type="joy" player="2" buttons="4" ways="8" reverse="no" />
   </input>
   ```
3. **`pacman`** — *Pac-Man (Midway)* (`cloneof="puckman"`)
   ```xml
   <input players="2" coins="2" service="no" tilt="no">
       <control type="joy" player="1" ways="4" reverse="no" />
       <control type="joy" player="2" ways="4" reverse="no" />
   </input>
   ```
4. **`galaga`** — *Galaga (Namco rev. B)*
   ```xml
   <input players="2" coins="2" service="no" tilt="no">
       <control type="joy" player="1" buttons="1" ways="2" reverse="no" />
       <control type="joy" player="2" buttons="1" ways="2" reverse="no" />
   </input>
   ```
5. **`trackfld`** — *Track & Field*
   ```xml
   <input players="4" coins="2" service="no" tilt="no">
       <control type="only_buttons" player="1" buttons="3" reverse="no" />
       <control type="only_buttons" player="2" buttons="3" reverse="no" />
       <control type="only_buttons" player="3" buttons="3" reverse="no" />
       <control type="only_buttons" player="4" buttons="3" reverse="no" />
   </input>
   ```
6. **`arkanoid`** — *Arkanoid (World, older)*
   ```xml
   <input players="2" coins="2" tilt="yes" service="no">
       <control type="dial" player="1" buttons="1" minimum="0" maximum="255" sensitivity="30" keydelta="15" reverse="no" />
       <control type="dial" player="2" buttons="1" minimum="0" maximum="255" sensitivity="30" keydelta="15" reverse="no" />
   </input>
   ```
7. **`gt3d`** — *Golden Tee 3D Golf (v1.93N)* (Catatan: `gtg` adalah versi Joystick 8-way)
   ```xml
   <input players="2" coins="3" service="yes">
       <control type="trackball" player="1" buttons="2" minimum="0" maximum="255" sensitivity="25" keydelta="32" reverse="yes"/>
       <control type="trackball" player="2" buttons="2" minimum="0" maximum="255" sensitivity="25" keydelta="32" reverse="yes"/>
   </input>
   ```
8. **`daytona`** — *Daytona USA (Revision A)*
   ```xml
   <input players="1" coins="2" service="yes" tilt="no">
       <control type="paddle" buttons="9" minimum="0" maximum="255" sensitivity="30" keydelta="10" reverse="no" />
       <control type="pedal" minimum="0" maximum="255" sensitivity="30" keydelta="10" reverse="no" />
   </input>
   ```
9. **`timecris`** — *Time Crisis (World, TS2 Ver.B)*
   ```xml
   <input players="1" coins="1" service="no" tilt="no">
       <control type="lightgun" buttons="2" minimum="43" maximum="284" sensitivity="64" keydelta="4" reverse="no" />
   </input>
   ```

