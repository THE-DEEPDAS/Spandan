// ============================================================
//  FINAL_POC  –  ESP32-C6 Supermini  [WRIST MODE v13]
//  Sensors   : MAX30102 | MPU-6050 | GY-906 (MLX90614)
//  BLE       : Heart-Rate, SpO2, Temp, IMU (compact notify)
//
//  v8 fixes (from quantitative analysis — output__2_.txt):
//
//  ROOT CAUSE CONFIRMED:
//    HR valid only 7% of lines. SpO2 only 4%.
//    Simulation revealed DC_ALPHA=0.95 was the primary cause.
//
//  FIX 1 — DC_ALPHA raised: 0.95 → 0.98
//    At 0.95, filter time-constant τ=20 samples ≈ beat period
//    (15 samples at 100 BPM). DC was partially tracking the
//    heartbeat wave, reducing irAC amplitude.
//    Simulation: median |irAC| was 479 at 0.95 vs 783 at 0.98.
//    Samples passing MIN_SIGNAL_AMPLITUDE=250: 65% → 98%.
//    DC fast-reset on motion (dcInitialized=false) already
//    handles re-settling after motion — no drawback to 0.98.
//
//  FIX 2 — MIN_SIGNAL_AMPLITUDE lowered: 250 → 100
//    Belt-and-suspenders below the now-larger irAC signal.
//    Ensures weak peripheral pulses aren't silently dropped.
//    Still well above baseline noise (~20–40 counts).
//
//  FIX 3 — HR timeout: preserve beatCount on timeout
//    Old: hrValid=false AND beatCount=0 on 5s timeout.
//    Problem: device needed 4 NEW beats from scratch after
//    every brief signal loss. At 95 BPM = 4 beats in 2.5s —
//    any interruption within that window reset everything.
//    New: hrValid=false but beatCount and intervals KEPT.
//    Recovery happens on the NEXT single beat instead of 4.
//    beatCount only resets on contact loss or sustained motion.
//
//  FIX 4 — SpO2 minimum window lowered: 30 → 20 samples
//    With DC_ALPHA=0.98, AC terms are larger so RMS is more
//    stable at fewer samples. 20 samples (~0.8 s) is valid.
//    Allows SpO2 to compute ~50% more frequently.
//
//  v7 fixes retained:
//    – GYRO_MOTION_THRESH = 30°/s, CONSEC = 5
//    – SPO2_MOTION_FLUSH_AT = 10 (flush only on sustained)
//    – MIN_RR_MS = 500 ms, HR_TIMEOUT_MS = 5000 ms
//    – Wrist SpO2 formula: 112.5 − 25R
//    – R acceptance: 0.40–1.30, stability gate 0.15
// ============================================================
//
//  WRIST MODE — why all thresholds differ from finger mode:
//    Wrist PPG is reflective; the radial artery sits ~5–10 mm
//    below the skin surface vs ~1–2 mm in a fingertip. The
//    returned photon count is 10–20× weaker than finger.
//    Changes made vs finger version:
//
//    Hardware (initMAX):
//      LED current  : 0x24 (7.2 mA) → 0xFF (51 mA, absolute max)
//        Drives the most photons possible into deeper tissue.
//      SMP_AVE      : 4 → 8   (reg 0x08: 0x4F → 0x7F)
//        8-sample hardware averaging improves SNR ~40%.
//      Base SR      : 100 → 200 SPS (reg 0x0A: 0x27 → 0x2B)
//        Keeps effective rate at 200/8 = 25 SPS after averaging.
//
//    Software thresholds:
//      MIN_SKIN_IR        : 85000 → 8000
//        Finger at 7 mA gives 80k–200k; wrist at 51 mA gives
//        3k–30k. 8000 is a safe floor above ambient noise.
//      MAX_RAW_CHANGE     : 35000 → 6000
//        Motion deltas are proportionally smaller on weak signal.
//      MAX_BAD_MOTION_STREAK : 3 → 5
//        Wrist naturally has more micro-motion; more tolerance
//        before resetting accumulators.
//      WARMUP_SAMPLES     : 50 → 100
//        Weak DC takes longer to settle via the IIR filter.
//      MIN_SIGNAL_AMPLITUDE : 2000 → 250
//        Wrist AC pulsatile amplitude is ~100–500 counts vs
//        5000–15000 on finger. Gate set just above noise floor.
//      DC_ALPHA           : 0.95 → 0.98
//        Slower DC tracking preserves the proportionally small
//        AC component; prevents DC subtraction from eating beats.
//      MIN_SPO2_AC_DC_RATIO : 0.003 → 0.001
//        Wrist perfusion index is lower; lower gate prevents
//        valid but weak windows from being discarded as noise.
//
//  Output columns (1 Hz via Serial + BLE):
//    S1_IR  | S1_RED | HR | SpO2 | ObjT | AmbT
//    accX   | accY   | accZ | gX | gY | gZ | ST
// ============================================================

#include <Wire.h>
#include <math.h>
#include <string.h>
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>

// ─────────────────────── PINS ───────────────────────────────
#define SDA_PIN        15   // GP15
#define SCL_PIN        14   // GP14
#define MPU_INT_PIN    18   // GP18 – MPU-6050 data-ready IRQ
#define MAX_INT_PIN     7   // GP7  – MAX30102 FIFO/data-ready IRQ

// ─────────────────────── I2C ADDRESSES ──────────────────────
#define MAX30102_ADDR  0x57
#define MPU_ADDR       0x68
#define MLX90614_ADDR  0x5A

// ─────────────────────── BLE UUIDs ──────────────────────────
#define SERVICE_UUID        "4fafc201-1fb5-459e-8fcc-c5c9c331914b"
#define CHARACTERISTIC_UUID "beb5483e-36e1-4688-b7f5-ea07361b26a8"

BLECharacteristic *pCharacteristic;
bool deviceConnected = false;

class MyServerCallbacks : public BLEServerCallbacks {
  void onConnect(BLEServer *pServer)    { deviceConnected = true; }
  void onDisconnect(BLEServer *pServer) {
    deviceConnected = false;
    BLEDevice::startAdvertising();
  }
};

TwoWire I2Cbus = TwoWire(0);

// ─────────────────────── INTERRUPT FLAGS ────────────────────
volatile bool mpuDataReady = false;
volatile bool maxDataReady = false;
void IRAM_ATTR onMPUInterrupt() { mpuDataReady = true; }
void IRAM_ATTR onMAXInterrupt() { maxDataReady = true; }

// ─────────────────────── SIGNAL QUALITY CONSTANTS ───────────
// All values tuned for WRIST reflective PPG.
// Original finger values shown in comments for reference.

// DC_ALPHA = 0.98 (restored to v9 value, v12).
// v10 adaptive (0.95→0.98) doubled HR via dicrotic notch.
// v11 fixed at 0.99 caused AC to collapse (median 62 counts)
// because τ=100 samples is too slow — wrist drift appears as
// large irAC offset, giving false beats.
// 0.98 (τ=50 samples) is the confirmed sweet spot:
//   τ >> beat period (26 samples at 57 BPM) → no DC tracking of beat
//   τ fast enough that dcInitialized=false hard-reset after motion
//   snaps DC to new wrist position within ~2 seconds.
// This matches the v9 configuration that the reviewer confirmed
// gave better readings.
const float    DC_ALPHA               = 0.98f;

// Wrist contact floor.
// Must be ABOVE the ambient no-skin reading (~4000 counts at 5 mA).
// Ambient reads ~4000; wrist contact at 5 mA should read 30,000–180,000.
// Set to 6000 = safely above ambient, well below real wrist contact.
// If you see NO_CONTACT with skin on: lower toward 4500.
// If you see OK with sensor lifted: raise toward 8000.
const uint32_t MIN_SKIN_IR            = 6000;

// Saturation ceiling – unchanged; clipping behaviour is the same.
const uint32_t MAX_VALID_ADC          = 250000;

// Max sample-to-sample jump before flagging motion.
// Wrist signal is ~10–20× weaker, so valid physiological swings
// and motion deltas are both proportionally smaller.
// Finger original: 35000
const float    MAX_RAW_CHANGE         = 6000.0f;

// Optical motion streak reset. Back to 3 — real data showed the wrist
// can stay in a "slow motion" state for many samples and accumulate
// garbage SpO2 windows. Reset faster.
// Finger original: 3
const int      MAX_BAD_MOTION_STREAK  = 3;

// Warmup: 75 samples. With DC_ALPHA=0.95 the DC settles in ~20 samples,
// so 75 gives ample margin without making the user wait 4 seconds.
// Finger original: 50
const int      WARMUP_SAMPLES         = 75;

// Minimum AC peak to accept as a real heartbeat.
// Lowered 250 → 100 (v8): with DC_ALPHA=0.98 the irAC signal
// is now larger (median ~783 vs ~479 at 0.95). Setting floor
// at 100 catches weak peripheral pulses while still rejecting
// baseline noise which is typically 20–40 counts.
// Finger original: 2000
const int      MIN_SIGNAL_AMPLITUDE   = 100;

// Lower perfusion index floor for SpO2 window acceptance.
// Wrist AC/DC ratio is much smaller than finger.
// Finger original: 0.003
// Lowered 0.001 → 0.0005 (v10): at weak wrist contact the
// perfusion index can drop to ~0.003 — keep floor well below
// that so valid low-perfusion windows are not rejected.
const float    MIN_SPO2_AC_DC_RATIO   = 0.0005f;

// Upper gate unchanged; clipping / motion still disqualifies window.
const float    MAX_SPO2_AC_DC_RATIO   = 0.20f;

// IMU motion gate threshold (°/s) and debounce count.
// GYRO_MOTION_THRESH raised 20 → 30°/s:
//   Data showed 31% of still-wear lines at 5–20°/s. The old
//   threshold was inside the normal wrist micro-tremor envelope.
//   30°/s is clearly above micro-tremor, catches real movement.
// GYRO_MOTION_CONSEC raised 3 → 5:
//   63/64 post-IMU_MOTION prints had |gyro|<20°/s, proving
//   3-sample debounce was still catching brief spikes.
//   5 samples at 25 SPS = 200 ms of sustained motion required.
const float    GYRO_MOTION_THRESH    = 30.0f;
const int      GYRO_MOTION_CONSEC    = 5;

// SpO2 flush threshold: consecutive IMU_MOTION samples before
// the accumulator is fully wiped.
// Raised from 1 → 10 (= 400 ms of continuous motion).
// Brief motion now skips the sample but KEEPS accumulated sums.
// Data: median clean run = 1 sample; old flush-on-1 meant SpO2
// never reached 50 samples → showed "--" 74% of the time.
const int      SPO2_MOTION_FLUSH_AT  = 10;
// Minimum ms between two accepted beats.
// Raised from 500 → 650 ms (v13).
// Zero-crossing analysis showed true HR=77.6 BPM but code reported
// 114.9 BPM. A secondary radial artery resonance peak on wrist PPG
// arrives ~520ms after systole. The old 500ms gate allowed it through.
// 650ms blocks the 520ms peak. Max detectable HR = 60000/650 = 92 BPM.
// Appropriate for resting wristband. Lower to 400ms for exercise mode.
const uint32_t MIN_RR_MS             = 650;

// ── HR: Stale reading timeout ────────────────────────────────
// If no new confirmed beat arrives within this window,
// hrValid is set false and HR output returns "--".
// Prevents old HR value from displaying indefinitely through
// motion breaks or signal loss.
// Data showed HR locked for 9–18 seconds with no update.
// 5000 ms = 5 seconds: enough for 1 beat at 60 BPM.
const uint32_t HR_TIMEOUT_MS         = 5000;

// ── SpO2: Wrist-specific R ratio bounds ─────────────────────
// On wrist reflective PPG the RED DC is ~40–50% of IR DC because
// red light (~660 nm) penetrates shallower than IR (~940 nm).
// This skews R toward higher values than finger transmissive mode.
// Empirical wrist R range for SpO2 95–100%: 0.5 – 0.85
// Empirical wrist R range for SpO2 85–95%:  0.85 – 1.10
// Reject windows where R falls outside 0.4–1.3 (physiological range
// for wrist; anything outside is motion or contact artifact).
const float    WRIST_R_MIN           = 0.40f;
const float    WRIST_R_MAX           = 1.30f;

// SpO2 formula coefficients tuned for wrist reflective PPG.
// Finger formula: SpO2 = 110 - 25*R
// The RED/IR DC imbalance shifts the effective R upward. Using the
// wrist-corrected two-point calibration:
//   R=0.50 → SpO2~100%,  R=1.10 → SpO2~85%
//   Slope: (85-100)/(1.10-0.50) = -25   Intercept: 100 + 25*0.50 = 112.5
// Coefficient A=112.5, B=25 — same slope, higher intercept vs finger.
const float    SPO2_COEFF_A          = 112.5f;
const float    SPO2_COEFF_B          = 25.0f;


// ─────────────────────── DC TRACKING ────────────────────────
float irDC  = 0, redDC = 0;
float prevIrDC = 0, prevRedDC = 0;
bool  dcInitialized = false;

// ─────────────────────── SIGNAL STATE ───────────────────────
uint32_t prevAdcIR  = 0, prevAdcRed = 0;
bool     hasPrevSample = false;
bool     isSignalValid = false;
int      sampleCounter = 0;
int      motionStreak  = 0;
uint32_t lastStatusMs  = 0;
char     statusMsg[24] = "WARMUP";


// ─────────────────────── HEART RATE ─────────────────────────
float    irPrev     = 0, irPrevPrev = 0;
bool     rising     = false;
uint32_t lastBeatMs = 0;
uint32_t beatIntervals[8];
int      beatCount        = 0;
float    heartRate        = 0;
bool     hrValid          = false;
int      inconsistentBeats = 0;

// ─────────────────────── SPO2 ───────────────────────────────
float sumIR_sq = 0, sumRed_sq = 0;
float sumIR    = 0, sumRed    = 0;
int   spo2Count = 0;
float spO2      = 0;
bool  spo2Valid = false;
float prevR     = 0;
int   rOutliers = 0;

// ─────────────────────── IMU ────────────────────────────────
float accX = 0, accY = 0, accZ = 0;
float gyroX = 0, gyroY = 0, gyroZ = 0;
// gyroMotion: set true only after GYRO_MOTION_CONSEC consecutive
// samples exceed GYRO_MOTION_THRESH. Clears after 1 clean sample.
// Prevents single-sample micro-tremor spikes from gating the signal.
bool  gyroMotion      = false;
int   gyroHighCount   = 0;    // consecutive above-threshold sample count
// Counts consecutive confirmed IMU_MOTION samples for SpO2 flush.
int   imuMotionStreak = 0;

// ─────────────────────── MLX90614 ───────────────────────────
float mlxObjectTemp  = 0.0f;
float mlxAmbientTemp = 0.0f;
float mlxFiltered    = 0.0f;
bool  mlxInitialized = false;
unsigned long lastTempRead = 0;

// ─────────────────────── PRINT TIMING ───────────────────────
unsigned long lastPrint = 0;


// ════════════════════════════════════════════════════════════
//  I2C HELPERS  (MAX30102 raw register access)
// ════════════════════════════════════════════════════════════
void writeReg(uint8_t reg, uint8_t val) {
  I2Cbus.beginTransmission(MAX30102_ADDR);
  I2Cbus.write(reg);
  I2Cbus.write(val);
  I2Cbus.endTransmission();
}

uint8_t readReg(uint8_t reg) {
  I2Cbus.beginTransmission(MAX30102_ADDR);
  I2Cbus.write(reg);
  I2Cbus.endTransmission(false);
  I2Cbus.requestFrom(MAX30102_ADDR, (uint8_t)1);
  return I2Cbus.read();
}


// ════════════════════════════════════════════════════════════
//  MEDIAN FILTER  (sorts a copy, returns middle value)
//  Used for HR – one bad RR interval won't skew the result.
// ════════════════════════════════════════════════════════════
uint32_t getMedianInterval(uint32_t arr[], int count) {
  if (count <= 0) return 0;
  uint32_t tmp[8];
  for (int i = 0; i < count; i++) tmp[i] = arr[i];
  for (int i = 0; i < count - 1; i++)
    for (int j = 0; j < count - i - 1; j++)
      if (tmp[j] > tmp[j + 1]) {
        uint32_t t = tmp[j]; tmp[j] = tmp[j + 1]; tmp[j + 1] = t;
      }
  return tmp[count / 2];
}


// ════════════════════════════════════════════════════════════
//  WRIST CONTACT CHECK
//  Rejects: no contact (IR too low) AND sensor clipping (IR too high).
//  MIN_SKIN_IR=8000 is calibrated for wrist reflective PPG at
//  51 mA LED drive. Ambient light noise typically stays below 4000.
// ════════════════════════════════════════════════════════════
bool hasContact(uint32_t adcIR, uint32_t adcRed) {
  return adcIR  > MIN_SKIN_IR   && adcRed > MIN_SKIN_IR &&
         adcIR  < MAX_VALID_ADC && adcRed < MAX_VALID_ADC;
}


// ════════════════════════════════════════════════════════════
//  SOFTWARE MOTION ARTIFACT DETECTION
//  Checks both raw sample-to-sample delta AND DC slope.
//  Raw delta catches sudden jolts; DC slope catches sustained
//  movement (slower vibration that raw delta misses).
//  Wrist dcThresh = 6000 × (1−0.98) × 2 = 240 (tighter than finger).
// ════════════════════════════════════════════════════════════
bool detectMotionArtifact(uint32_t adcIR, uint32_t adcRed) {
  if (!hasPrevSample || sampleCounter < WARMUP_SAMPLES) return false;

  float irRawChange  = fabsf((float)adcIR  - (float)prevAdcIR);
  float redRawChange = fabsf((float)adcRed - (float)prevAdcRed);
  float irDcChange   = fabsf(irDC  - prevIrDC);
  float redDcChange  = fabsf(redDC - prevRedDC);

  // DC threshold: any single sample can shift DC by at most (1-alpha)*delta
  // so 2× that threshold on the derivative catches sustained motion
  // DC slope threshold: 6000×(1-0.98)×2 = 240
  float dcThresh = MAX_RAW_CHANGE * (1.0f - DC_ALPHA) * 2.0f;

  return irRawChange  > MAX_RAW_CHANGE ||
         redRawChange > MAX_RAW_CHANGE ||
         irDcChange   > dcThresh       ||
         redDcChange  > dcThresh;
}


// ════════════════════════════════════════════════════════════
//  THROTTLED STATUS HELPER  (avoids serial spam)
// ════════════════════════════════════════════════════════════
void setStatus(const char *msg) {
  strncpy(statusMsg, msg, sizeof(statusMsg) - 1);
  statusMsg[sizeof(statusMsg) - 1] = '\0';
}

void printStatusThrottled(const char *msg) {
  setStatus(msg);
  uint32_t now = millis();
  if (now - lastStatusMs >= 500) {
    Serial.println(msg);
    lastStatusMs = now;
  }
}


// ════════════════════════════════════════════════════════════
//  FULL SIGNAL RESET
//  Called on finger-off or sustained motion streak.
// ════════════════════════════════════════════════════════════
void resetDerivedReadings() {
  irPrev = irPrevPrev = 0;
  rising = false;
  lastBeatMs = 0;
  beatCount  = 0;
  heartRate  = 0;
  hrValid    = false;
  inconsistentBeats = 0;
  sumIR_sq = sumRed_sq = sumIR = sumRed = 0;
  spo2Count = 0;
  spO2      = 0;
  spo2Valid = false;
  // v9: force DC re-init on next sample so stale DC from previous
  // wrist position doesn't generate spurious irAC transients that
  // confuse the beat detector and trigger inconsistentBeats resets.
  dcInitialized = false;
  prevR     = 0;
  rOutliers = 0;
}


// ════════════════════════════════════════════════════════════
//  INIT MAX30102  [WRIST MODE]
// ════════════════════════════════════════════════════════════
void initMAX() {
  writeReg(0x09, 0x40);  // soft reset
  delay(500);

  // FIFO config: SMP_AVE=8 (bits[7:5]=011), FIFO_ROLLOVER_EN, FIFO_A_FULL=15
  // 8-sample hardware averaging improves SNR ~40% vs original SMP_AVE=4.
  // Original finger value: 0x4F (SMP_AVE=4)
  writeReg(0x08, 0x7F);

  // Mode: SpO2 (Red + IR both active)
  writeReg(0x09, 0x03);

  // SpO2 config: ADC_RGE=4096nA, SR=200SPS, PW=411µs (18-bit)
  // 200 SPS base with SMP_AVE=8 → 25 effective SPS (same as original
  // 100 SPS / SMP_AVE=4 = 25 SPS) but with double the hardware averaging.
  // Bit layout: [7]=0, [6:5]=01(4096nA), [4:2]=010(200SPS), [1:0]=11(18-bit)
  //             = 0b00101011 = 0x2B
  // Original finger value: 0x27 (100 SPS, SMP_AVE=4)
  writeReg(0x0A, 0x2B);

  // LED currents – WRIST TUNING NOTE:
  // At 51 mA (0xFF) the wrist saturates the ADC to 262143 (18-bit max).
  // Wrist reflective PPG at zero air gap is highly efficient; much less
  // current is needed than finger transmissive mode.
  // Starting value: 0x19 = 25 × 0.2 mA = 5.0 mA
  //
  // HOW TO TUNE IF STILL SATURATING OR TOO WEAK:
  //   Still NO_CONTACT (IR=262143) → lower current: try 0x0F (3.0 mA), 0x0A (2.0 mA)
  //   NO_CONTACT but IR very low  → raise current: try 0x24 (7.2 mA), 0x30 (9.6 mA)
  //   Target DC baseline: IR counts between 30,000 and 180,000 on wrist contact.
  writeReg(0x0C, 0x19);  // Red LED – 5.0 mA
  writeReg(0x0D, 0x19);  // IR  LED – 5.0 mA

  // Interrupts: A_FULL + PPG_RDY → drives MAX_INT_PIN LOW
  writeReg(0x02, 0xC0);

  Serial.print("MAX30102 PART ID: 0x");
  Serial.println(readReg(0xFF), HEX);  // expect 0x15
}


// ════════════════════════════════════════════════════════════
//  INIT MPU-6050
// ════════════════════════════════════════════════════════════
void initMPU() {
  I2Cbus.beginTransmission(MPU_ADDR);
  I2Cbus.write(0x6B);
  I2Cbus.write(0x00);  // clear SLEEP bit → wake up
  I2Cbus.endTransmission();
  delay(50);

  // Set gyro full-scale: ±250 °/s (0x00 = default, 131 LSB/°/s)
  I2Cbus.beginTransmission(MPU_ADDR);
  I2Cbus.write(0x1B);
  I2Cbus.write(0x00);
  I2Cbus.endTransmission();

  // Set accel full-scale: ±2 g (0x00 = default, 16384 LSB/g)
  I2Cbus.beginTransmission(MPU_ADDR);
  I2Cbus.write(0x1C);
  I2Cbus.write(0x00);
  I2Cbus.endTransmission();

  // Enable DATA_RDY interrupt
  I2Cbus.beginTransmission(MPU_ADDR);
  I2Cbus.write(0x38);
  I2Cbus.write(0x01);
  I2Cbus.endTransmission();

  Serial.println("MPU-6050 OK");
}


// ════════════════════════════════════════════════════════════
//  INIT MLX90614 (GY-906)
//  I²C clock MUST stay at 100 kHz (SMBus spec).
// ════════════════════════════════════════════════════════════
bool initMLX90614() {
  I2Cbus.beginTransmission(MLX90614_ADDR);
  uint8_t err = I2Cbus.endTransmission();
  if (err != 0) {
    Serial.print("MLX90614 not found! err="); Serial.println(err);
    return false;
  }
  Serial.println("MLX90614 OK");
  return true;
}


// ════════════════════════════════════════════════════════════
//  READ MLX90614
//  RAM 0x06 = ambient Tа  |  RAM 0x07 = object Tobj1
//  Formula: raw × 0.02 − 273.15  (unit = 0.02 K)
// ════════════════════════════════════════════════════════════
static float mlxReadCelsius(uint8_t ramAddr) {
  I2Cbus.beginTransmission(MLX90614_ADDR);
  I2Cbus.write(ramAddr);
  uint8_t err = I2Cbus.endTransmission(false);  // repeated-start
  if (err != 0) return NAN;

  uint8_t count = I2Cbus.requestFrom((uint8_t)MLX90614_ADDR, (uint8_t)3);
  if (count < 3) return NAN;

  uint8_t lsb = I2Cbus.read();
  uint8_t msb = I2Cbus.read();
  I2Cbus.read();  // PEC – discard

  if (msb & 0x80) return NAN;  // error flag

  uint16_t raw = ((uint16_t)msb << 8) | lsb;
  return (raw * 0.02f) - 273.15f;
}

void updateTempMLX() {
  const unsigned long READ_INTERVAL_MS = 500;
  const float VALID_MIN_C = 20.0f, VALID_MAX_C = 43.0f;

  if (millis() - lastTempRead < READ_INTERVAL_MS) return;
  lastTempRead = millis();

  float objTemp = mlxReadCelsius(0x07);
  float ambTemp = mlxReadCelsius(0x06);

  if (!isnan(ambTemp)) mlxAmbientTemp = ambTemp;

  if (isnan(objTemp) || objTemp < VALID_MIN_C || objTemp > VALID_MAX_C) return;

  if (!mlxInitialized) {
    mlxFiltered   = objTemp;
    mlxInitialized = true;
    mlxObjectTemp  = objTemp;
    return;
  }

  // Adaptive IIR: faster tracking when reading jumps (re-placement event)
  float diff = fabsf(objTemp - mlxFiltered);
  float alpha = (diff > 1.0f) ? 0.35f : (diff > 0.4f) ? 0.20f : 0.08f;
  mlxFiltered  += alpha * (objTemp - mlxFiltered);
  mlxObjectTemp = mlxFiltered;
}


// ════════════════════════════════════════════════════════════
//  READ MPU-6050
//  Reads 14 bytes from 0x3B (accel X/Y/Z, temp, gyro X/Y/Z)
//  Converts to SI units: g and °/s.
//  Sets gyroMotion=true when gyro magnitude > GYRO_MOTION_THRESH.
//  This catches wrist movement that the optical guard misses (e.g.
//  slow DC shifts that don't exceed MAX_RAW_CHANGE sample-to-sample).
// ════════════════════════════════════════════════════════════
void updateIMU() {
  I2Cbus.beginTransmission(MPU_ADDR);
  I2Cbus.write(0x3B);
  I2Cbus.endTransmission(false);
  I2Cbus.requestFrom(MPU_ADDR, 14);

  int16_t ax = (I2Cbus.read() << 8) | I2Cbus.read();
  int16_t ay = (I2Cbus.read() << 8) | I2Cbus.read();
  int16_t az = (I2Cbus.read() << 8) | I2Cbus.read();
  I2Cbus.read(); I2Cbus.read();  // internal temp – skip
  int16_t gx = (I2Cbus.read() << 8) | I2Cbus.read();
  int16_t gy = (I2Cbus.read() << 8) | I2Cbus.read();
  int16_t gz = (I2Cbus.read() << 8) | I2Cbus.read();

  accX  = ax / 16384.0f;   // ±2 g  → 16384 LSB/g
  accY  = ay / 16384.0f;
  accZ  = az / 16384.0f;
  gyroX = gx / 131.0f;     // ±250°/s → 131 LSB/(°/s)
  gyroY = gy / 131.0f;
  gyroZ = gz / 131.0f;

  // Gyro debounce: only declare motion after GYRO_MOTION_CONSEC
  // consecutive above-threshold samples. Clears on first clean sample.
  // Single-sample spikes (normal wrist micro-tremor) are ignored.
  float gyroMag = sqrtf(gyroX*gyroX + gyroY*gyroY + gyroZ*gyroZ);
  if (gyroMag > GYRO_MOTION_THRESH) {
    gyroHighCount++;
    if (gyroHighCount >= GYRO_MOTION_CONSEC) {
      gyroMotion = true;
    }
  } else {
    gyroHighCount = 0;   // reset immediately on any clean sample
    gyroMotion    = false;
  }

  mpuDataReady = false;
}


// ════════════════════════════════════════════════════════════
//  SETUP
// ════════════════════════════════════════════════════════════
void setup() {
  Serial.begin(115200);
  delay(200);

  pinMode(MPU_INT_PIN, INPUT);
  pinMode(MAX_INT_PIN, INPUT);
  attachInterrupt(digitalPinToInterrupt(MPU_INT_PIN), onMPUInterrupt, RISING);
  attachInterrupt(digitalPinToInterrupt(MAX_INT_PIN), onMAXInterrupt, FALLING);

  // 100 kHz – required by MLX90614 SMBus spec
  I2Cbus.begin(SDA_PIN, SCL_PIN);
  I2Cbus.setClock(100000);

  initMAX();
  initMPU();
  initMLX90614();

  // BLE setup
  BLEDevice::init("FINAL_POC_WRIST");
  BLEServer *pServer = BLEDevice::createServer();
  pServer->setCallbacks(new MyServerCallbacks());
  BLEService *pService = pServer->createService(SERVICE_UUID);
  pCharacteristic = pService->createCharacteristic(
    CHARACTERISTIC_UUID,
    BLECharacteristic::PROPERTY_NOTIFY
  );
  pCharacteristic->addDescriptor(new BLE2902());
  pService->start();
  BLEDevice::startAdvertising();

  Serial.println("\nFINAL_POC_WRIST READY");
  Serial.println("Columns: S1_IR,S1_RED,HR,SpO2,ObjT,AmbT,accX,accY,accZ,gX,gY,gZ,ST");
}


// ════════════════════════════════════════════════════════════
//  LOOP
// ════════════════════════════════════════════════════════════
void loop() {

  // ── IMU + Temp: always run, independent of optical signal ──
  updateIMU();
  updateTempMLX();

  // ── Read MAX30102 FIFO (6 bytes: Red[3] + IR[3]) ───────────
  I2Cbus.beginTransmission(MAX30102_ADDR);
  I2Cbus.write(0x07);  // FIFO_DATA register
  I2Cbus.endTransmission(false);
  if (I2Cbus.requestFrom(MAX30102_ADDR, (uint8_t)6) != 6) return;

  uint32_t red = ((uint32_t)I2Cbus.read() << 16) |
                 ((uint32_t)I2Cbus.read() <<  8) |
                  I2Cbus.read();
  uint32_t ir  = ((uint32_t)I2Cbus.read() << 16) |
                 ((uint32_t)I2Cbus.read() <<  8) |
                  I2Cbus.read();
  red &= 0x3FFFF;  // mask to 18-bit
  ir  &= 0x3FFFF;
  maxDataReady = false;

  uint32_t adcIR  = ir;
  uint32_t adcRed = red;

  // ── Stage 1: reconstruct raw FIFO hex bytes ─────────────────
  uint8_t irB0  = (ir  >> 16) & 0x03;
  uint8_t irB1  = (ir  >>  8) & 0xFF;
  uint8_t irB2  =  ir         & 0xFF;
  uint8_t redB0 = (red >> 16) & 0x03;
  uint8_t redB1 = (red >>  8) & 0xFF;
  uint8_t redB2 =  red        & 0xFF;
  char s1ir[12], s1red[12];
  snprintf(s1ir,  sizeof(s1ir),  "%02X %02X %02X", irB0,  irB1,  irB2);
  snprintf(s1red, sizeof(s1red), "%02X %02X %02X", redB0, redB1, redB2);

  sampleCounter++;

  // ── DC tracking ─────────────────────────────────────────────
  // Save BEFORE updating so detectMotionArtifact can compare
  if (dcInitialized) {
    prevIrDC  = irDC;
    prevRedDC = redDC;
  }
  if (!dcInitialized) {
    irDC  = (float)adcIR;
    redDC = (float)adcRed;
    dcInitialized = true;
  } else {
    // Fixed DC_ALPHA=0.99: τ=100 samples >> beat period at any HR.
    // dcInitialized=false on reset hard-sets DC to raw value,
    // so post-motion settling is instant without adaptive alpha.
    irDC  = DC_ALPHA * irDC  + (1.0f - DC_ALPHA) * (float)adcIR;
    redDC = DC_ALPHA * redDC + (1.0f - DC_ALPHA) * (float)adcRed;
  }

  float irAC  = (float)adcIR  - irDC;
  float redAC = (float)adcRed - redDC;

  // ── Guard 1: Wrist contact + saturation check ───────────────
  if (!hasContact(adcIR, adcRed)) {
    isSignalValid = false;
    // Print raw counts every 500 ms so threshold can be calibrated.
    // Watch these values with skin touching the sensor; set MIN_SKIN_IR
    // to ~60–70% of the lowest stable value you see during contact.
    uint32_t nowMs = millis();
    if (nowMs - lastStatusMs >= 500) {
      Serial.print("NO_CONTACT  IR=");
      Serial.print(adcIR);
      Serial.print("  RED=");
      Serial.println(adcRed);
      lastStatusMs = nowMs;
    }
    setStatus("NO_CONTACT");
    resetDerivedReadings();
    dcInitialized  = false;
    hasPrevSample  = false;
    sampleCounter  = 0;
    motionStreak   = 0;
    delay(50);
    return;
  }

  // ── Guard 2: Warmup – let DC settle before trusting signal ──
  if (sampleCounter < WARMUP_SAMPLES) {
    isSignalValid = false;
    printStatusThrottled("WARMUP");
    prevAdcIR  = adcIR;
    prevAdcRed = adcRed;
    hasPrevSample = true;
    return;
  }

  // ── Guard 3: Software motion artifact detection ──────────────
  if (detectMotionArtifact(adcIR, adcRed)) {
    motionStreak++;
    isSignalValid = false;
    printStatusThrottled("MOTION");
    if (motionStreak >= MAX_BAD_MOTION_STREAK) {
      resetDerivedReadings();
      // Also flush SpO2 window – stale sums from before motion
      // corrupt the R ratio after the streak clears.
      sumIR_sq  = sumRed_sq = sumIR = sumRed = 0;
      spo2Count = 0;
      rOutliers = 0;
      prevR     = 0;
      spo2Valid = false;
    }
    prevAdcIR  = adcIR;
    prevAdcRed = adcRed;
    hasPrevSample = true;
    return;
  }

  // ── Signal is clean ─────────────────────────────────────────
  motionStreak  = 0;
  isSignalValid = true;
  setStatus("OK");
  prevAdcIR  = adcIR;
  prevAdcRed = adcRed;
  hasPrevSample = true;

  // ════════════════════════════════════════════════════════════
  //  IMU MOTION GATE
  //  gyroMotion = true only after GYRO_MOTION_CONSEC (5)
  //  consecutive samples above GYRO_MOTION_THRESH (30°/s).
  //
  //  When gyroMotion is true:
  //    1. HR slope state is reset (irPrev, rising cleared)
  //    2. SpO2 sample is SKIPPED (sums not updated)
  //    3. SpO2 window is FLUSHED only if imuMotionStreak
  //       reaches SPO2_MOTION_FLUSH_AT (10 samples = 400 ms).
  //       Brief motion keeps accumulated sums intact.
  //
  //  v7 change: data showed SpO2 window NEVER completed
  //  (0/126 runs ≥50 samples). Flush-on-1 was the cause.
  // ════════════════════════════════════════════════════════════
  if (gyroMotion) {
    imuMotionStreak++;
    printStatusThrottled("IMU_MOTION");

    // Reset HR slope state immediately
    irPrevPrev = irPrev = 0;
    rising = false;

    // Flush SpO2 window completely — stale sums from before motion
    // would corrupt the R ratio calculation after motion clears.
    if (imuMotionStreak >= SPO2_MOTION_FLUSH_AT) {
      sumIR_sq  = sumRed_sq = sumIR = sumRed = 0;
      spo2Count = 0;
      rOutliers = 0;
      prevR     = 0;
      spo2Valid = false;
      // v10: also wipe stale beat intervals on sustained motion.
      // Without this, beats during motion pair with pre-motion
      // timestamps → wrong RR → HR jumps after motion ends.
      beatCount = 0;
      inconsistentBeats = 0;
      memset(beatIntervals, 0, sizeof(beatIntervals));
      // Refresh lastBeatMs so timeout clock starts from motion end.
      lastBeatMs = millis();
    }

    prevAdcIR  = adcIR;
    prevAdcRed = adcRed;
    hasPrevSample = true;
    delay(2);
    return;
  }

  // Motion cleared — reset IMU streak counter
  imuMotionStreak = 0;

  // ════════════════════════════════════════════════════════════
  //  HEART RATE  –  slope-reversal + amplitude gate + median

  // ════════════════════════════════════════════════════════════
  bool beatDetected = false;

  // v9: changed from 3-sample to 2-sample ascending check.
  // Original (3-sample): irAC > irPrev && irPrev > irPrevPrev
  // At low wrist AC amplitude (~273 counts) a single noisy sample
  // breaks the 3-consecutive chain, preventing rising=true entirely.
  // 2-sample check is resilient to single-sample noise.
  // Safety: MIN_RR_MS=500ms refractory still guards dicrotic notch.
  if (irAC > irPrev) {
    rising = true;
  } else if (rising && irAC < irPrev) {
    // Amplitude gate: reject noise spikes that look like peaks
    if (fabsf(irPrev) > MIN_SIGNAL_AMPLITUDE) {
      rising       = false;
      beatDetected = true;

      uint32_t now = millis();
      if (lastBeatMs > 0) {
        uint32_t rr = now - lastBeatMs;

        // Refractory period guard: reject peaks arriving sooner than
        // MIN_RR_MS (500 ms). This blocks the dicrotic notch (~250–350 ms
        // after the systolic peak) from being counted as a second beat.
        // Real data: HR=68→124 BPM transition confirmed notch doubling
        // was slipping through at 481 ms. Raised to 500 ms.
        if (rr < MIN_RR_MS) {
          // Too soon – dicrotic notch or noise. Don't update lastBeatMs
          // so the next real peak gets measured from the correct anchor.
          rising = false;
          // fall through without recording this interval
        } else if (rr <= 1500) {
          // Valid RR interval (40–150 BPM after refractory guard)
          beatIntervals[beatCount % 8] = rr;
          beatCount++;
          inconsistentBeats = 0;
          lastBeatMs = now;

          if (beatCount >= 4) {
            uint32_t tmpArr[8];
            int n = min(beatCount, 8);
            for (int i = 0; i < n; i++) tmpArr[i] = beatIntervals[i];
            uint32_t medianRR = getMedianInterval(tmpArr, n);
            heartRate = 60000.0f / (float)medianRR;
            hrValid   = true;
          }
        } else {
          // RR > 1500 ms: too slow or contact break
          inconsistentBeats++;
          if (inconsistentBeats > 3) {
            beatCount         = 0;
            hrValid           = false;
            inconsistentBeats = 0;
          }
          lastBeatMs = now;
        }
      } else {
        lastBeatMs = now;  // first beat anchor
      }
    } else {
      rising = false;  // sub-threshold peak: noise spike, ignore
    }
  }

  irPrevPrev = irPrev;
  irPrev     = irAC;

  // ════════════════════════════════════════════════════════════
  //  SPO2  –  RMS-based R ratio with wrist-specific gates
  //
  //  R = (rmsAC_red / dcAvg_red) / (rmsAC_ir / dcAvg_ir)
  //
  //  Wrist formula: SpO2 = 112.5 − 25 × R
  //  (vs finger formula 110 − 25R; intercept raised because the
  //   RED/IR DC imbalance at ~0.44 ratio shifts R upward on wrist)
  //
  //  R physiological bounds for wrist reflective PPG:
  //    SpO2 95–100%  →  R ≈ 0.50–0.85
  //    SpO2 85–95%   →  R ≈ 0.85–1.10
  //    Outside 0.40–1.30 = motion artifact or bad contact
  // ════════════════════════════════════════════════════════════
  sumIR_sq  += irAC  * irAC;
  sumRed_sq += redAC * redAC;
  sumIR     += irDC;
  sumRed    += redDC;
  spo2Count++;

  float R = 0;
  // Reduced from 30 → 20 samples (v8):
  // With DC_ALPHA=0.98 the AC terms are larger and more stable,
  // so valid RMS can be computed at fewer samples.
  // 20 samples = ~0.8 s at 25 SPS — still covers >1 full beat
  // cycle at resting HR (60+ BPM = 1.0 s period).
  // v9: window reduced 20 → 15 (= 0.6 s at 25 SPS).
  // With DC_ALPHA=0.98 the AC terms are stable enough at 15 samples.
  if (spo2Count >= 15 && sumIR_sq > 0 && irDC > 0 && redDC > 0) {
    float rmsIR  = sqrtf(sumIR_sq  / spo2Count);
    float rmsRed = sqrtf(sumRed_sq / spo2Count);
    float avgIR  = sumIR  / spo2Count;
    float avgRed = sumRed / spo2Count;

    float irPerf  = rmsIR  / avgIR;
    float redPerf = rmsRed / avgRed;
    R = redPerf / irPerf;

    // Window quality gate: perfusion index bounds + wrist R range
    bool windowGood =
      irPerf  >= MIN_SPO2_AC_DC_RATIO && irPerf  <= MAX_SPO2_AC_DC_RATIO &&
      redPerf >= MIN_SPO2_AC_DC_RATIO && redPerf <= MAX_SPO2_AC_DC_RATIO &&
      R >= WRIST_R_MIN && R <= WRIST_R_MAX;

    // R stability gate: reject sudden jumps (motion or re-placement).
    // Tightened from 0.35 → 0.15 based on real data analysis.
    float rChange = fabsf(R - prevR);
    if (!windowGood) {
      spo2Valid = false;
      rOutliers++;
    // v9: stability gate loosened 0.15 → 0.20.
    // Natural beat-to-beat R variation on wrist exceeds 0.15,
    // causing valid windows to be rejected. 0.20 passes natural
    // variation while still blocking large motion-induced jumps.
    } else if (prevR > 0 && rChange > 0.20f) {
      rOutliers++;
      spo2Valid = false;
    } else {
      rOutliers = 0;
      // Wrist-corrected SpO2 formula
      spO2 = SPO2_COEFF_A - SPO2_COEFF_B * R;
      spO2 = constrain(spO2, 80.0f, 100.0f);  // floor raised: <80% = sensor error on wrist
      spo2Valid = true;
    }
    if (windowGood) prevR = R;

    // Slide window every 150 clean samples (~6 s)
    if (spo2Count >= 150) {
      sumIR_sq = sumRed_sq = sumIR = sumRed = 0;
      spo2Count = 0;
      rOutliers = 0;
    }
  }

  // ════════════════════════════════════════════════════════════
  //  HR TIMEOUT — hide stale display but KEEP beat history
  //  Old: hrValid=false AND beatCount=0 → needed 4 fresh beats.
  //  New: hrValid=false only → recovery happens on next single
  //  beat since the interval buffer is still populated.
  //  beatCount and intervals are only reset on contact loss or
  //  sustained motion (resetDerivedReadings), not here.
  //  v8: prevents the 7%-HR-valid problem where brief signal
  //  gaps triggered full resets requiring 4-beat re-lock.
  // ════════════════════════════════════════════════════════════
  // HR TIMEOUT: hrValid=false AND wipe stale intervals.
  // v10 fix: keeping old intervals caused 42 jumps >15 BPM —
  // new beat paired with a stale pre-timeout timestamp giving
  // wildly wrong RR. Clear intervals so the next 4 beats
  // build a fresh, correct baseline.
  if (lastBeatMs > 0 && (millis() - lastBeatMs) > HR_TIMEOUT_MS) {
    hrValid    = false;
    beatCount  = 0;
    inconsistentBeats = 0;
    memset(beatIntervals, 0, sizeof(beatIntervals));
    // Don't reset lastBeatMs — keeps the timeout from re-firing
    // every loop iteration once triggered.
  }

  // ════════════════════════════════════════════════════════════
  //  OUTPUT  –  1 Hz via Serial + BLE notify
  //  Format: Stage1 hex | Stage5 vitals | IMU | Temp | Status
  // ════════════════════════════════════════════════════════════
  if (millis() - lastPrint > 1000) {

    String data =
      // ── Stage 1: raw FIFO hex bytes ────────────────────────
      "S1_IR="   + String(s1ir)  +
      ",S1_RED=" + String(s1red) +

      // ── Stage 5: validated vitals ──────────────────────────
      ",HR="   + (hrValid && heartRate > 0
                    ? String(heartRate, 1) + (beatDetected ? "*" : "")
                    : String("--")) +
      ",SpO2=" + (spo2Valid && spO2 > 0
                    ? String(spO2, 1) + "%"
                    : String("--")) +

      // ── MLX90614 temperature ───────────────────────────────
      ",ObjT=" + String(mlxObjectTemp,  1) +
      ",AmbT=" + String(mlxAmbientTemp, 1) +

      // ── MPU-6050 IMU ───────────────────────────────────────
      ",accX=" + String(accX,  3) +
      ",accY=" + String(accY,  3) +
      ",accZ=" + String(accZ,  3) +
      ",gX="   + String(gyroX, 2) +
      ",gY="   + String(gyroY, 2) +
      ",gZ="   + String(gyroZ, 2) +

      // ── Signal quality status ──────────────────────────────
      ",ST="   + String(gyroMotion ? "IMU_MOTION" : statusMsg);

    Serial.println(data);

    if (deviceConnected) {
      pCharacteristic->setValue(data.c_str());
      pCharacteristic->notify();
    }

    lastPrint = millis();
  }

  delay(2);
}//  v13 fixes (from quantitative analysis of output9.txt + output12.txt):
//
//  CONFIRMED: HR=114.9 BPM locked in BOTH v9 AND v12.
//  Zero-crossing analysis: true cardiac period = 773ms (77.6 BPM).
//  A secondary radial artery resonance peak arrives ~520ms after
//  systole (distinct from dicrotic notch at ~280ms). The 500ms
//  refractory gate allowed the 522ms peak through → double HR.
//
//  FIX — MIN_RR_MS raised: 500 → 650 ms
//    Blocks the ~520ms resonance peak.
//    Caps max detected HR at 60000/650 = 92 BPM.
//    Appropriate for resting wristband monitoring.
//    Both v9 and v12 had this same underlying error.
//
//  BASE: v12 (DC_ALPHA=0.98, no 3-tap MA, stale interval clear,
//  GYRO_MOTION_THRESH=30, CONSEC=5, FLUSH_AT=10)

//  v8 fixes (from quantitative analysis — output__2_.txt):
//
//  ROOT CAUSE CONFIRMED:
//    HR valid only 7% of lines. SpO2 only 4%.
//    Simulation revealed DC_ALPHA=0.95 was the primary cause.
//
//  FIX 1 — DC_ALPHA raised: 0.95 → 0.98
//    At 0.95, filter time-constant τ=20 samples ≈ beat period
//    (15 samples at 100 BPM). DC was partially tracking the
//    heartbeat wave, reducing irAC amplitude.
//    Simulation: median |irAC| was 479 at 0.95 vs 783 at 0.98.
//    Samples passing MIN_SIGNAL_AMPLITUDE=250: 65% → 98%.
//    DC fast-reset on motion (dcInitialized=false) already
//    handles re-settling after motion — no drawback to 0.98.
//
//  FIX 2 — MIN_SIGNAL_AMPLITUDE lowered: 250 → 100
//    Belt-and-suspenders below the now-larger irAC signal.
//    Ensures weak peripheral pulses aren't silently dropped.
//    Still well above baseline noise (~20–40 counts).
//
//  FIX 3 — HR timeout: preserve beatCount on timeout
//    Old: hrValid=false AND beatCount=0 on 5s timeout.
//    Problem: device needed 4 NEW beats from scratch after
//    every brief signal loss. At 95 BPM = 4 beats in 2.5s —
//    any interruption within that window reset everything.
//    New: hrValid=false but beatCount and intervals KEPT.
//    Recovery happens on the NEXT single beat instead of 4.
//    beatCount only resets on contact loss or sustained motion.
//
//  FIX 4 — SpO2 minimum window lowered: 30 → 20 samples
//    With DC_ALPHA=0.98, AC terms are larger so RMS is more
//    stable at fewer samples. 20 samples (~0.8 s) is valid.
//    Allows SpO2 to compute ~50% more frequently.
//
//  v7 fixes retained:
//    – GYRO_MOTION_THRESH = 30°/s, CONSEC = 5
//    – SPO2_MOTION_FLUSH_AT = 10 (flush only on sustained)
//    – MIN_RR_MS = 500 ms, HR_TIMEOUT_MS = 5000 ms
//    – Wrist SpO2 formula: 112.5 − 25R
//    – R acceptance: 0.40–1.30, stability gate 0.15
// ============================================================
//
//  WRIST MODE — why all thresholds differ from finger mode:
//    Wrist PPG is reflective; the radial artery sits ~5–10 mm
//    below the skin surface vs ~1–2 mm in a fingertip. The
//    returned photon count is 10–20× weaker than finger.
//    Changes made vs finger version:
//
//    Hardware (initMAX):
//      LED current  : 0x24 (7.2 mA) → 0xFF (51 mA, absolute max)
//        Drives the most photons possible into deeper tissue.
//      SMP_AVE      : 4 → 8   (reg 0x08: 0x4F → 0x7F)
//        8-sample hardware averaging improves SNR ~40%.
//      Base SR      : 100 → 200 SPS (reg 0x0A: 0x27 → 0x2B)
//        Keeps effective rate at 200/8 = 25 SPS after averaging.
//
//    Software thresholds:
//      MIN_SKIN_IR        : 85000 → 8000
//        Finger at 7 mA gives 80k–200k; wrist at 51 mA gives
//        3k–30k. 8000 is a safe floor above ambient noise.
//      MAX_RAW_CHANGE     : 35000 → 6000
//        Motion deltas are proportionally smaller on weak signal.
//      MAX_BAD_MOTION_STREAK : 3 → 5
//        Wrist naturally has more micro-motion; more tolerance
//        before resetting accumulators.
//      WARMUP_SAMPLES     : 50 → 100
//        Weak DC takes longer to settle via the IIR filter.
//      MIN_SIGNAL_AMPLITUDE : 2000 → 250
//        Wrist AC pulsatile amplitude is ~100–500 counts vs
//        5000–15000 on finger. Gate set just above noise floor.
//      DC_ALPHA           : 0.95 → 0.98
//        Slower DC tracking preserves the proportionally small
//        AC component; prevents DC subtraction from eating beats.
//      MIN_SPO2_AC_DC_RATIO : 0.003 → 0.001
//        Wrist perfusion index is lower; lower gate prevents
//        valid but weak windows from being discarded as noise.
//
//  Output columns (1 Hz via Serial + BLE):
//    S1_IR  | S1_RED | HR | SpO2 | ObjT | AmbT
//    accX   | accY   | accZ | gX | gY | gZ | ST
// ============================================================

#include <Wire.h>
#include <math.h>
#include <string.h>
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>

// ─────────────────────── PINS ───────────────────────────────
#define SDA_PIN        15   // GP15
#define SCL_PIN        14   // GP14
#define MPU_INT_PIN    18   // GP18 – MPU-6050 data-ready IRQ
#define MAX_INT_PIN     7   // GP7  – MAX30102 FIFO/data-ready IRQ

// ─────────────────────── I2C ADDRESSES ──────────────────────
#define MAX30102_ADDR  0x57
#define MPU_ADDR       0x68
#define MLX90614_ADDR  0x5A

// ─────────────────────── BLE UUIDs ──────────────────────────
#define SERVICE_UUID        "4fafc201-1fb5-459e-8fcc-c5c9c331914b"
#define CHARACTERISTIC_UUID "beb5483e-36e1-4688-b7f5-ea07361b26a8"

BLECharacteristic *pCharacteristic;
bool deviceConnected = false;

class MyServerCallbacks : public BLEServerCallbacks {
  void onConnect(BLEServer *pServer)    { deviceConnected = true; }
  void onDisconnect(BLEServer *pServer) {
    deviceConnected = false;
    BLEDevice::startAdvertising();
  }
};

TwoWire I2Cbus = TwoWire(0);

// ─────────────────────── INTERRUPT FLAGS ────────────────────
volatile bool mpuDataReady = false;
volatile bool maxDataReady = false;
void IRAM_ATTR onMPUInterrupt() { mpuDataReady = true; }
void IRAM_ATTR onMAXInterrupt() { maxDataReady = true; }

// ─────────────────────── SIGNAL QUALITY CONSTANTS ───────────
// All values tuned for WRIST reflective PPG.
// Original finger values shown in comments for reference.

// DC_ALPHA = 0.98 (restored to v9 value, v12).
// v10 adaptive (0.95→0.98) doubled HR via dicrotic notch.
// v11 fixed at 0.99 caused AC to collapse (median 62 counts)
// because τ=100 samples is too slow — wrist drift appears as
// large irAC offset, giving false beats.
// 0.98 (τ=50 samples) is the confirmed sweet spot:
//   τ >> beat period (26 samples at 57 BPM) → no DC tracking of beat
//   τ fast enough that dcInitialized=false hard-reset after motion
//   snaps DC to new wrist position within ~2 seconds.
// This matches the v9 configuration that the reviewer confirmed
// gave better readings.
const float    DC_ALPHA               = 0.98f;

// Wrist contact floor.
// Must be ABOVE the ambient no-skin reading (~4000 counts at 5 mA).
// Ambient reads ~4000; wrist contact at 5 mA should read 30,000–180,000.
// Set to 6000 = safely above ambient, well below real wrist contact.
// If you see NO_CONTACT with skin on: lower toward 4500.
// If you see OK with sensor lifted: raise toward 8000.
const uint32_t MIN_SKIN_IR            = 6000;

// Saturation ceiling – unchanged; clipping behaviour is the same.
const uint32_t MAX_VALID_ADC          = 250000;

// Max sample-to-sample jump before flagging motion.
// Wrist signal is ~10–20× weaker, so valid physiological swings
// and motion deltas are both proportionally smaller.
// Finger original: 35000
const float    MAX_RAW_CHANGE         = 6000.0f;

// Optical motion streak reset. Back to 3 — real data showed the wrist
// can stay in a "slow motion" state for many samples and accumulate
// garbage SpO2 windows. Reset faster.
// Finger original: 3
const int      MAX_BAD_MOTION_STREAK  = 3;

// Warmup: 75 samples. With DC_ALPHA=0.95 the DC settles in ~20 samples,
// so 75 gives ample margin without making the user wait 4 seconds.
// Finger original: 50
const int      WARMUP_SAMPLES         = 75;

// Minimum AC peak to accept as a real heartbeat.
// Lowered 250 → 100 (v8): with DC_ALPHA=0.98 the irAC signal
// is now larger (median ~783 vs ~479 at 0.95). Setting floor
// at 100 catches weak peripheral pulses while still rejecting
// baseline noise which is typically 20–40 counts.
// Finger original: 2000
const int      MIN_SIGNAL_AMPLITUDE   = 100;

// Lower perfusion index floor for SpO2 window acceptance.
// Wrist AC/DC ratio is much smaller than finger.
// Finger original: 0.003
// Lowered 0.001 → 0.0005 (v10): at weak wrist contact the
// perfusion index can drop to ~0.003 — keep floor well below
// that so valid low-perfusion windows are not rejected.
const float    MIN_SPO2_AC_DC_RATIO   = 0.0005f;

// Upper gate unchanged; clipping / motion still disqualifies window.
const float    MAX_SPO2_AC_DC_RATIO   = 0.20f;

// IMU motion gate threshold (°/s) and debounce count.
// GYRO_MOTION_THRESH raised 20 → 30°/s:
//   Data showed 31% of still-wear lines at 5–20°/s. The old
//   threshold was inside the normal wrist micro-tremor envelope.
//   30°/s is clearly above micro-tremor, catches real movement.
// GYRO_MOTION_CONSEC raised 3 → 5:
//   63/64 post-IMU_MOTION prints had |gyro|<20°/s, proving
//   3-sample debounce was still catching brief spikes.
//   5 samples at 25 SPS = 200 ms of sustained motion required.
const float    GYRO_MOTION_THRESH    = 30.0f;
const int      GYRO_MOTION_CONSEC    = 5;

// SpO2 flush threshold: consecutive IMU_MOTION samples before
// the accumulator is fully wiped.
// Raised from 1 → 10 (= 400 ms of continuous motion).
// Brief motion now skips the sample but KEEPS accumulated sums.
// Data: median clean run = 1 sample; old flush-on-1 meant SpO2
// never reached 50 samples → showed "--" 74% of the time.
const int      SPO2_MOTION_FLUSH_AT  = 10;

// ── HR: Stale reading timeout ────────────────────────────────
// If no new confirmed beat arrives within this window,
// hrValid is set false and HR output returns "--".
// Prevents old HR value from displaying indefinitely through
// motion breaks or signal loss.
// Data showed HR locked for 9–18 seconds with no update.
// 5000 ms = 5 seconds: enough for 1 beat at 60 BPM.
const uint32_t HR_TIMEOUT_MS         = 5000;

// ── SpO2: Wrist-specific R ratio bounds ─────────────────────
// On wrist reflective PPG the RED DC is ~40–50% of IR DC because
// red light (~660 nm) penetrates shallower than IR (~940 nm).
// This skews R toward higher values than finger transmissive mode.
// Empirical wrist R range for SpO2 95–100%: 0.5 – 0.85
// Empirical wrist R range for SpO2 85–95%:  0.85 – 1.10
// Reject windows where R falls outside 0.4–1.3 (physiological range
// for wrist; anything outside is motion or contact artifact).
const float    WRIST_R_MIN           = 0.40f;
const float    WRIST_R_MAX           = 1.30f;

// SpO2 formula coefficients tuned for wrist reflective PPG.
// Finger formula: SpO2 = 110 - 25*R
// The RED/IR DC imbalance shifts the effective R upward. Using the
// wrist-corrected two-point calibration:
//   R=0.50 → SpO2~100%,  R=1.10 → SpO2~85%
//   Slope: (85-100)/(1.10-0.50) = -25   Intercept: 100 + 25*0.50 = 112.5
// Coefficient A=112.5, B=25 — same slope, higher intercept vs finger.
const float    SPO2_COEFF_A          = 112.5f;
const float    SPO2_COEFF_B          = 25.0f;


// ─────────────────────── DC TRACKING ────────────────────────
float irDC  = 0, redDC = 0;
float prevIrDC = 0, prevRedDC = 0;
bool  dcInitialized = false;

// ─────────────────────── SIGNAL STATE ───────────────────────
uint32_t prevAdcIR  = 0, prevAdcRed = 0;
bool     hasPrevSample = false;
bool     isSignalValid = false;
int      sampleCounter = 0;
int      motionStreak  = 0;
uint32_t lastStatusMs  = 0;
char     statusMsg[24] = "WARMUP";


// ─────────────────────── HEART RATE ─────────────────────────
float    irPrev     = 0, irPrevPrev = 0;
bool     rising     = false;
uint32_t lastBeatMs = 0;
uint32_t beatIntervals[8];
int      beatCount        = 0;
float    heartRate        = 0;
bool     hrValid          = false;
int      inconsistentBeats = 0;

// ─────────────────────── SPO2 ───────────────────────────────
float sumIR_sq = 0, sumRed_sq = 0;
float sumIR    = 0, sumRed    = 0;
int   spo2Count = 0;
float spO2      = 0;
bool  spo2Valid = false;
float prevR     = 0;
int   rOutliers = 0;

// ─────────────────────── IMU ────────────────────────────────
float accX = 0, accY = 0, accZ = 0;
float gyroX = 0, gyroY = 0, gyroZ = 0;
// gyroMotion: set true only after GYRO_MOTION_CONSEC consecutive
// samples exceed GYRO_MOTION_THRESH. Clears after 1 clean sample.
// Prevents single-sample micro-tremor spikes from gating the signal.
bool  gyroMotion      = false;
int   gyroHighCount   = 0;    // consecutive above-threshold sample count
// Counts consecutive confirmed IMU_MOTION samples for SpO2 flush.
int   imuMotionStreak = 0;

// ─────────────────────── MLX90614 ───────────────────────────
float mlxObjectTemp  = 0.0f;
float mlxAmbientTemp = 0.0f;
float mlxFiltered    = 0.0f;
bool  mlxInitialized = false;
unsigned long lastTempRead = 0;

// ─────────────────────── PRINT TIMING ───────────────────────
unsigned long lastPrint = 0;


// ════════════════════════════════════════════════════════════
//  I2C HELPERS  (MAX30102 raw register access)
// ════════════════════════════════════════════════════════════
void writeReg(uint8_t reg, uint8_t val) {
  I2Cbus.beginTransmission(MAX30102_ADDR);
  I2Cbus.write(reg);
  I2Cbus.write(val);
  I2Cbus.endTransmission();
}

uint8_t readReg(uint8_t reg) {
  I2Cbus.beginTransmission(MAX30102_ADDR);
  I2Cbus.write(reg);
  I2Cbus.endTransmission(false);
  I2Cbus.requestFrom(MAX30102_ADDR, (uint8_t)1);
  return I2Cbus.read();
}


// ════════════════════════════════════════════════════════════
//  MEDIAN FILTER  (sorts a copy, returns middle value)
//  Used for HR – one bad RR interval won't skew the result.
// ════════════════════════════════════════════════════════════
uint32_t getMedianInterval(uint32_t arr[], int count) {
  if (count <= 0) return 0;
  uint32_t tmp[8];
  for (int i = 0; i < count; i++) tmp[i] = arr[i];
  for (int i = 0; i < count - 1; i++)
    for (int j = 0; j < count - i - 1; j++)
      if (tmp[j] > tmp[j + 1]) {
        uint32_t t = tmp[j]; tmp[j] = tmp[j + 1]; tmp[j + 1] = t;
      }
  return tmp[count / 2];
}


// ════════════════════════════════════════════════════════════
//  WRIST CONTACT CHECK
//  Rejects: no contact (IR too low) AND sensor clipping (IR too high).
//  MIN_SKIN_IR=8000 is calibrated for wrist reflective PPG at
//  51 mA LED drive. Ambient light noise typically stays below 4000.
// ════════════════════════════════════════════════════════════
bool hasContact(uint32_t adcIR, uint32_t adcRed) {
  return adcIR  > MIN_SKIN_IR   && adcRed > MIN_SKIN_IR &&
         adcIR  < MAX_VALID_ADC && adcRed < MAX_VALID_ADC;
}


// ════════════════════════════════════════════════════════════
//  SOFTWARE MOTION ARTIFACT DETECTION
//  Checks both raw sample-to-sample delta AND DC slope.
//  Raw delta catches sudden jolts; DC slope catches sustained
//  movement (slower vibration that raw delta misses).
//  Wrist dcThresh = 6000 × (1−0.98) × 2 = 240 (tighter than finger).
// ════════════════════════════════════════════════════════════
bool detectMotionArtifact(uint32_t adcIR, uint32_t adcRed) {
  if (!hasPrevSample || sampleCounter < WARMUP_SAMPLES) return false;

  float irRawChange  = fabsf((float)adcIR  - (float)prevAdcIR);
  float redRawChange = fabsf((float)adcRed - (float)prevAdcRed);
  float irDcChange   = fabsf(irDC  - prevIrDC);
  float redDcChange  = fabsf(redDC - prevRedDC);

  // DC threshold: any single sample can shift DC by at most (1-alpha)*delta
  // so 2× that threshold on the derivative catches sustained motion
  // DC slope threshold: 6000×(1-0.98)×2 = 240
  float dcThresh = MAX_RAW_CHANGE * (1.0f - DC_ALPHA) * 2.0f;

  return irRawChange  > MAX_RAW_CHANGE ||
         redRawChange > MAX_RAW_CHANGE ||
         irDcChange   > dcThresh       ||
         redDcChange  > dcThresh;
}


// ════════════════════════════════════════════════════════════
//  THROTTLED STATUS HELPER  (avoids serial spam)
// ════════════════════════════════════════════════════════════
void setStatus(const char *msg) {
  strncpy(statusMsg, msg, sizeof(statusMsg) - 1);
  statusMsg[sizeof(statusMsg) - 1] = '\0';
}

void printStatusThrottled(const char *msg) {
  setStatus(msg);
  uint32_t now = millis();
  if (now - lastStatusMs >= 500) {
    Serial.println(msg);
    lastStatusMs = now;
  }
}


// ════════════════════════════════════════════════════════════
//  FULL SIGNAL RESET
//  Called on finger-off or sustained motion streak.
// ════════════════════════════════════════════════════════════
void resetDerivedReadings() {
  irPrev = irPrevPrev = 0;
  rising = false;
  lastBeatMs = 0;
  beatCount  = 0;
  heartRate  = 0;
  hrValid    = false;
  inconsistentBeats = 0;
  sumIR_sq = sumRed_sq = sumIR = sumRed = 0;
  spo2Count = 0;
  spO2      = 0;
  spo2Valid = false;
  // v9: force DC re-init on next sample so stale DC from previous
  // wrist position doesn't generate spurious irAC transients that
  // confuse the beat detector and trigger inconsistentBeats resets.
  dcInitialized = false;
  prevR     = 0;
  rOutliers = 0;
}


// ════════════════════════════════════════════════════════════
//  INIT MAX30102  [WRIST MODE]
// ════════════════════════════════════════════════════════════
void initMAX() {
  writeReg(0x09, 0x40);  // soft reset
  delay(500);

  // FIFO config: SMP_AVE=8 (bits[7:5]=011), FIFO_ROLLOVER_EN, FIFO_A_FULL=15
  // 8-sample hardware averaging improves SNR ~40% vs original SMP_AVE=4.
  // Original finger value: 0x4F (SMP_AVE=4)
  writeReg(0x08, 0x7F);

  // Mode: SpO2 (Red + IR both active)
  writeReg(0x09, 0x03);

  // SpO2 config: ADC_RGE=4096nA, SR=200SPS, PW=411µs (18-bit)
  // 200 SPS base with SMP_AVE=8 → 25 effective SPS (same as original
  // 100 SPS / SMP_AVE=4 = 25 SPS) but with double the hardware averaging.
  // Bit layout: [7]=0, [6:5]=01(4096nA), [4:2]=010(200SPS), [1:0]=11(18-bit)
  //             = 0b00101011 = 0x2B
  // Original finger value: 0x27 (100 SPS, SMP_AVE=4)
  writeReg(0x0A, 0x2B);

  // LED currents – WRIST TUNING NOTE:
  // At 51 mA (0xFF) the wrist saturates the ADC to 262143 (18-bit max).
  // Wrist reflective PPG at zero air gap is highly efficient; much less
  // current is needed than finger transmissive mode.
  // Starting value: 0x19 = 25 × 0.2 mA = 5.0 mA
  //
  // HOW TO TUNE IF STILL SATURATING OR TOO WEAK:
  //   Still NO_CONTACT (IR=262143) → lower current: try 0x0F (3.0 mA), 0x0A (2.0 mA)
  //   NO_CONTACT but IR very low  → raise current: try 0x24 (7.2 mA), 0x30 (9.6 mA)
  //   Target DC baseline: IR counts between 30,000 and 180,000 on wrist contact.
  writeReg(0x0C, 0x19);  // Red LED – 5.0 mA
  writeReg(0x0D, 0x19);  // IR  LED – 5.0 mA

  // Interrupts: A_FULL + PPG_RDY → drives MAX_INT_PIN LOW
  writeReg(0x02, 0xC0);

  Serial.print("MAX30102 PART ID: 0x");
  Serial.println(readReg(0xFF), HEX);  // expect 0x15
}


// ════════════════════════════════════════════════════════════
//  INIT MPU-6050
// ════════════════════════════════════════════════════════════
void initMPU() {
  I2Cbus.beginTransmission(MPU_ADDR);
  I2Cbus.write(0x6B);
  I2Cbus.write(0x00);  // clear SLEEP bit → wake up
  I2Cbus.endTransmission();
  delay(50);

  // Set gyro full-scale: ±250 °/s (0x00 = default, 131 LSB/°/s)
  I2Cbus.beginTransmission(MPU_ADDR);
  I2Cbus.write(0x1B);
  I2Cbus.write(0x00);
  I2Cbus.endTransmission();

  // Set accel full-scale: ±2 g (0x00 = default, 16384 LSB/g)
  I2Cbus.beginTransmission(MPU_ADDR);
  I2Cbus.write(0x1C);
  I2Cbus.write(0x00);
  I2Cbus.endTransmission();

  // Enable DATA_RDY interrupt
  I2Cbus.beginTransmission(MPU_ADDR);
  I2Cbus.write(0x38);
  I2Cbus.write(0x01);
  I2Cbus.endTransmission();

  Serial.println("MPU-6050 OK");
}


// ════════════════════════════════════════════════════════════
//  INIT MLX90614 (GY-906)
//  I²C clock MUST stay at 100 kHz (SMBus spec).
// ════════════════════════════════════════════════════════════
bool initMLX90614() {
  I2Cbus.beginTransmission(MLX90614_ADDR);
  uint8_t err = I2Cbus.endTransmission();
  if (err != 0) {
    Serial.print("MLX90614 not found! err="); Serial.println(err);
    return false;
  }
  Serial.println("MLX90614 OK");
  return true;
}


// ════════════════════════════════════════════════════════════
//  READ MLX90614
//  RAM 0x06 = ambient Tа  |  RAM 0x07 = object Tobj1
//  Formula: raw × 0.02 − 273.15  (unit = 0.02 K)
// ════════════════════════════════════════════════════════════
static float mlxReadCelsius(uint8_t ramAddr) {
  I2Cbus.beginTransmission(MLX90614_ADDR);
  I2Cbus.write(ramAddr);
  uint8_t err = I2Cbus.endTransmission(false);  // repeated-start
  if (err != 0) return NAN;

  uint8_t count = I2Cbus.requestFrom((uint8_t)MLX90614_ADDR, (uint8_t)3);
  if (count < 3) return NAN;

  uint8_t lsb = I2Cbus.read();
  uint8_t msb = I2Cbus.read();
  I2Cbus.read();  // PEC – discard

  if (msb & 0x80) return NAN;  // error flag

  uint16_t raw = ((uint16_t)msb << 8) | lsb;
  return (raw * 0.02f) - 273.15f;
}

void updateTempMLX() {
  const unsigned long READ_INTERVAL_MS = 500;
  const float VALID_MIN_C = 20.0f, VALID_MAX_C = 43.0f;

  if (millis() - lastTempRead < READ_INTERVAL_MS) return;
  lastTempRead = millis();

  float objTemp = mlxReadCelsius(0x07);
  float ambTemp = mlxReadCelsius(0x06);

  if (!isnan(ambTemp)) mlxAmbientTemp = ambTemp;

  if (isnan(objTemp) || objTemp < VALID_MIN_C || objTemp > VALID_MAX_C) return;

  if (!mlxInitialized) {
    mlxFiltered   = objTemp;
    mlxInitialized = true;
    mlxObjectTemp  = objTemp;
    return;
  }

  // Adaptive IIR: faster tracking when reading jumps (re-placement event)
  float diff = fabsf(objTemp - mlxFiltered);
  float alpha = (diff > 1.0f) ? 0.35f : (diff > 0.4f) ? 0.20f : 0.08f;
  mlxFiltered  += alpha * (objTemp - mlxFiltered);
  mlxObjectTemp = mlxFiltered;
}


// ════════════════════════════════════════════════════════════
//  READ MPU-6050
//  Reads 14 bytes from 0x3B (accel X/Y/Z, temp, gyro X/Y/Z)
//  Converts to SI units: g and °/s.
//  Sets gyroMotion=true when gyro magnitude > GYRO_MOTION_THRESH.
//  This catches wrist movement that the optical guard misses (e.g.
//  slow DC shifts that don't exceed MAX_RAW_CHANGE sample-to-sample).
// ════════════════════════════════════════════════════════════
void updateIMU() {
  I2Cbus.beginTransmission(MPU_ADDR);
  I2Cbus.write(0x3B);
  I2Cbus.endTransmission(false);
  I2Cbus.requestFrom(MPU_ADDR, 14);

  int16_t ax = (I2Cbus.read() << 8) | I2Cbus.read();
  int16_t ay = (I2Cbus.read() << 8) | I2Cbus.read();
  int16_t az = (I2Cbus.read() << 8) | I2Cbus.read();
  I2Cbus.read(); I2Cbus.read();  // internal temp – skip
  int16_t gx = (I2Cbus.read() << 8) | I2Cbus.read();
  int16_t gy = (I2Cbus.read() << 8) | I2Cbus.read();
  int16_t gz = (I2Cbus.read() << 8) | I2Cbus.read();

  accX  = ax / 16384.0f;   // ±2 g  → 16384 LSB/g
  accY  = ay / 16384.0f;
  accZ  = az / 16384.0f;
  gyroX = gx / 131.0f;     // ±250°/s → 131 LSB/(°/s)
  gyroY = gy / 131.0f;
  gyroZ = gz / 131.0f;

  // Gyro debounce: only declare motion after GYRO_MOTION_CONSEC
  // consecutive above-threshold samples. Clears on first clean sample.
  // Single-sample spikes (normal wrist micro-tremor) are ignored.
  float gyroMag = sqrtf(gyroX*gyroX + gyroY*gyroY + gyroZ*gyroZ);
  if (gyroMag > GYRO_MOTION_THRESH) {
    gyroHighCount++;
    if (gyroHighCount >= GYRO_MOTION_CONSEC) {
      gyroMotion = true;
    }
  } else {
    gyroHighCount = 0;   // reset immediately on any clean sample
    gyroMotion    = false;
  }

  mpuDataReady = false;
}


// ════════════════════════════════════════════════════════════
//  SETUP
// ════════════════════════════════════════════════════════════
