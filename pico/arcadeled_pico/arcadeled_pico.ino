#include <Joystick.h>

// ============================================================
// Konfigurasi 1 Pico: 7 Tombol Input (6 Aksi + 1 Start) & 6 LED
//   - Tombol 1..6 (A, B, X, Y, L, R) : GP2, GP3, GP4, GP5, GP10, GP11
//   - Tombol 7    (Start)            : GP12
//   - 6 LED       (A, B, X, Y, L, R) : GP6, GP7, GP8, GP9, GP16, GP17
// ============================================================
#define NUM_BUTTONS 7
#define NUM_LEDS 6

const byte btn[NUM_BUTTONS] = {2, 3, 4, 5, 10, 11, 12};
const byte led[NUM_LEDS] = {6, 7, 8, 9, 16, 17};

// Button debounce
bool last[NUM_BUTTONS];
bool state[NUM_BUTTONS];
unsigned long timer[NUM_BUTTONS] = {0};
const unsigned long debounce = 25;

// Serial command
String cmd = "";

void setup() {
  // Initialize buttons
  for (int i = 0; i < NUM_BUTTONS; i++) {
    pinMode(btn[i], INPUT_PULLUP);
    last[i] = HIGH;
    state[i] = HIGH;
  }

  // Initialize LEDs
  for (int i = 0; i < NUM_LEDS; i++) {
    pinMode(led[i], OUTPUT);
    digitalWrite(led[i], LOW);
  }

  // Initialize USB HID
  Joystick.begin();
  Joystick.useManualSend(true);

  // Initialize USB Serial
  Serial.begin(115200);
}

void loop() {
  readButtons();
  readSerial();
}

// Read arcade buttons
void readButtons() {
  bool changed = false;

  for (int i = 0; i < NUM_BUTTONS; i++) {
    bool r = digitalRead(btn[i]);

    if (r != last[i]) {
      last[i] = r;
      timer[i] = millis();
    }

    if (millis() - timer[i] > debounce && r != state[i]) {
      state[i] = r;
      Joystick.button(i + 1, !r);
      changed = true;
    }
  }

  if (changed) Joystick.send_now();
}

// Read USB Serial commands
void readSerial() {
  while (Serial.available()) {
    char c = Serial.read();

    if (c == '\n' || c == '\r') {
      cmd.trim();
      cmd.toUpperCase();

      if (cmd.length()) processCommand(cmd);

      cmd = "";
    }
    else if (cmd.length() < 40) {
      cmd += c;
    }
  }
}

// Process commands
void processCommand(String command) {

  // Device identification
  if (command == "HELLO") {
    Serial.println("ARCADELED_V1");
    return;
  }

  // All LEDs
  if (command == "ALL ON" || command == "ALL OFF") {
    bool on = command == "ALL ON";

    for (int i = 0; i < NUM_LEDS; i++) {
      digitalWrite(led[i], on);
    }

    Serial.println("OK");
    return;
  }

  // Individual LED (LED1..LED<NUM_LEDS>; channel lebih tinggi diabaikan dengan aman)
  if (command.startsWith("LED") && command.length() >= 6) {
    int spaceIdx = command.indexOf(' ');
    if (spaceIdx > 3) {
      int n = command.substring(3, spaceIdx).toInt();
      String action = command.substring(spaceIdx + 1);

      if (n >= 1 && n <= 16 &&
          (action == "ON" || action == "OFF")) {

        if (n <= NUM_LEDS) {
          digitalWrite(led[n - 1], action == "ON");
        }
        Serial.println("OK");
        return;
      }
    }
  }

  Serial.println("ERROR");
}
