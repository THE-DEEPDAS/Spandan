# Real-Time CSV Data Structure Visualizer

## Data Flow Architecture

```
STARTUP SEQUENCE:
┌──────────────────────────────────────────────────────────┐
│ 1. Start API: uvicorn police_health_api:app              │
└──────────────────────────────────────────────────────────┘
                         ▼
┌──────────────────────────────────────────────────────────┐
│ 2. CSVDataLoader initializes                            │
│    - Scans ../police-personnel-data-realtime/           │
│    - Finds all .csv files                               │
└──────────────────────────────────────────────────────────┘
                         ▼
┌──────────────────────────────────────────────────────────┐
│ 3. Load CSV files into memory                           │
│    - 0498 - Officer_A - ...csv       (47 rows)         │
│    - 699 - Officer_B - ...csv        (98 rows)         │
│    - 949 - Officer_C - ...csv        (52 rows)         │
│    ─────────────────────────────────────────            │
│    Total: 197 rows (all in RAM)                         │
└──────────────────────────────────────────────────────────┘
                         ▼
┌──────────────────────────────────────────────────────────┐
│ 4. Initialize index = 0                                │
│    Ready to cycle through rows                         │
└──────────────────────────────────────────────────────────┘
```

## Runtime Data Cycling

```
EACH API REQUEST:
┌──────────────────────────────────────────────────────────┐
│ API Receives: GET /api/telemetry/current               │
└──────────────────────────────────────────────────────────┘
                         ▼
┌──────────────────────────────────────────────────────────┐
│ Current Index: 0                                        │
│ Get Row[0] from CSV array:                             │
│   {HeartRate: 77.3, SpO2: 90.0, Temp: 33.4, ...}      │
└──────────────────────────────────────────────────────────┘
                         ▼
┌──────────────────────────────────────────────────────────┐
│ Parse CSV row → RawData object                          │
│ Calculate derived metrics (Physical Load, Stability)    │
│ Create TelemetryPoint with timestamp                    │
└──────────────────────────────────────────────────────────┘
                         ▼
┌──────────────────────────────────────────────────────────┐
│ Increment Index: 0 → 1                                  │
│ (wraps around: 196 → 0 when reaching end)              │
└──────────────────────────────────────────────────────────┘
                         ▼
┌──────────────────────────────────────────────────────────┐
│ Return JSON telemetry data to Dashboard                 │
└──────────────────────────────────────────────────────────┘
```

## Dashboard Update Cycle

```
TIME          DASHBOARD ACTION           CSV INDEX   DATA SOURCE
─────────────────────────────────────────────────────────────
00:00  →  GET /api/telemetry/current  →  [0]  →  77.3 HR
00:02  →  GET /api/telemetry/current  →  [1]  →  76.8 HR
00:04  →  GET /api/telemetry/current  →  [2]  →  78.1 HR
  ▲
  └─ Dashboard updates every 2 seconds

...continuing...

06:34  →  GET /api/telemetry/current  →  [196]  →  75.2 HR
06:36  →  GET /api/telemetry/current  →  [0]  →  77.3 HR (cycles back)
06:38  →  GET /api/telemetry/current  →  [1]  →  76.8 HR

One complete cycle: 197 rows × 2 seconds = 394 seconds ≈ 6.5 minutes
```

## CSV Structure Example

```
Your CSV files contain rows like:

┌───────────────────────────────────────────────────────────────┐
│ CSV Row Index 0                                               │
├───────────────────────────────────────────────────────────────┤
│ Date: 2026-03-27                                             │
│ Time: 13:31:52                                               │
│ HeartRate: 77.3 BPM          ← Used in dashboard            │
│ SpO2: 90.0 %                 ← Used in dashboard            │
│ Temperature: 33.4 °C         ← Used in dashboard            │
│ Acc_X: 0.766                 ← Used for metrics             │
│ Acc_Y: -0.259                ← Used for metrics             │
│ Acc_Z: -0.636                ← Used for metrics             │
│ Gyro_X: -6.58                ← Used for metrics             │
│ Gyro_Y: 6.97                 ← Used for metrics             │
│ Gyro_Z: 3.9                  ← Used for metrics             │
│ Health_Status: HEALTHY       ← Available if needed          │
│ Latitude: 20.978             ← Available if needed          │
│ Longitude: 73.106            ← Available if needed          │
│ Battery_Pct: 86.0            ← Available if needed          │
└───────────────────────────────────────────────────────────────┘
```

## Data Processing Pipeline

```
┌─────────────────────┐
│   CSV Row (Dict)    │ {HeartRate:77.3, SpO2:90, Temp:33.4, ...}
└──────────┬──────────┘
           │
           ▼
┌─────────────────────────────────────────┐
│ _generate_raw_data_from_csv()          │
│ - Extract numeric values                │
│ - Clamp to valid ranges                │
│   HeartRate: 60-180 BPM                │
│   SpO2: 85-100%                        │
│   Temp: 36-40°C                        │
└──────────┬──────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────┐
│ RawData Object                          │
│ heartRate: 77.3                        │
│ spo2: 90.0                             │
│ temp: 33.4                             │
│ accel: {x:0.766, y:-0.259, z:-0.636}  │
│ gyro: {x:-6.58, y:6.97, z:3.9}        │
└──────────┬──────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────┐
│ _calculate_derived_metrics()            │
│ - Physical Load (accel magnitude)      │
│ - Rotational Stress (gyro magnitude)   │
│ - Metabolic Strain (HR + Temp index)   │
│ - Stability Score (movement variance)  │
└──────────┬──────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────┐
│ TelemetryPoint                         │
│ timestamp: 2026-03-27T13:31:52Z        │
│ raw: {RawData}                         │
│ derived: {DerivedMetrics}              │
└──────────┬──────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────┐
│ JSON Response to Dashboard              │
│ {"timestamp": "...", "raw": {...}, ... │
└─────────────────────────────────────────┘
```

## Memory Usage Breakdown

```
On Startup (197 rows × avg 200 bytes per row):
┌─────────────────────────────────────┐
│ CSV Data in Memory:     ~40 KB      │
│ Python Object Headers:  ~2 KB       │
│ API Runtime:            ~1-2 MB     │
│ FastAPI Framework:      ~2-3 MB     │
├─────────────────────────────────────┤
│ TOTAL:                  ~5-6 MB     │
└─────────────────────────────────────┘

Per Request Performance:
┌─────────────────────────────────────┐
│ CSV lookup:             <1 ms       │
│ Data parsing:           <2 ms       │
│ Metric calculation:     <1 ms       │
│ JSON serialization:     <2 ms       │
│ Network latency:        5-20 ms     │
├─────────────────────────────────────┤
│ TOTAL REQUEST TIME:     10-30 ms    │
└─────────────────────────────────────┘
```

## Fallback Behavior

```
CSV Data Loading Priority:
┌──────────────────────────────────────────────┐
│ 1. Try to load CSV files                     │
│    ├─ Path: ../police-personnel-data-realtime/
│    ├─ Pattern: *.csv                         │
│    └─ Result: Found 3 files (197 rows) ✓    │
│                           OR                 │
│       Result: No files found ✗              │
├──────────────────────────────────────────────┤
│ 2. If CSV loaded (✓):                        │
│    └─ Use CSV data cycling                   │
│                           OR                 │
│       If no CSV (✗):                         │
│       └─ Fall back to random data generation │
└──────────────────────────────────────────────┘

API will work either way, but with real data
you get authentic officer health metrics!
```

---

**This visualization shows how your real CSV data flows through the system** once per 2-second dashboard refresh cycle! 🔄
