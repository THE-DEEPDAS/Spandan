# Real-Time CSV Data Integration - Testing Guide

## Quick Start

### 1. Run the API

```bash
cd Police-Project-Data-Science
python -m pip install -r requirements.txt
uvicorn police_health_api:app --reload --port 8000
```

Or use the batch script (Windows):

```bash
start-api.bat
```

Expected output:

```
Loaded 47 rows from 0498 - PankilKumar Arjunbhai Patel - 1051DB1C7222 - 2026-03-27.csv
Loaded 98 rows from 699 - Ashvinbhai chinmanbhai chaudhari - 1051DB1C72AE - 2026-03-27.csv
Loaded 52 rows from 949 - Gamit Suneshbhai Chimanbhai - 1051DB1C6ECE - 2026-03-27.csv
Total rows loaded: 197
INFO:     Uvicorn running on http://127.0.0.1:8000
```

### 2. Verify CSV Data Loading

```bash
curl http://localhost:8000/api/system/csv-status
```

Response (should show real data):

```json
{
  "hasData": true,
  "totalRows": 197,
  "currentIndex": 0,
  "dataSource": "real-time CSV"
}
```

### 3. Check Current Data

```bash
curl http://localhost:8000/api/telemetry/current
```

You should see real values like:

```json
{
  "timestamp": "2026-03-27T13:31:52Z",
  "raw": {
    "heartRate": 77.3,
    "spo2": 90.0,
    "temp": 33.4,
    "accel": {"x": 0.766, "y": -0.259, "z": -0.636},
    "gyro": {"x": -6.58, "y": 6.97, "z": 3.9}
  },
  "derived": {...}
}
```

### 4. Open Dashboard & Watch Real-Time Updates

Navigate to: `http://localhost:3000` (or wherever your Next.js dashboard runs)

You should see:

- Charts updating every 2 seconds
- Heart rate, SpO2, temperature varying continuously
- Acceleration and gyro data changing
- All values from actual CSV files from police personnel

## Testing Real-Time Updates

### Test 1: Data Cycling

```bash
# First call - gets row 0
curl http://localhost:8000/api/telemetry/current | jq '.raw.heartRate'
# Output: 77.3

# Wait 2 seconds
sleep 2

# Second call - gets row 1 (different heart rate)
curl http://localhost:8000/api/telemetry/current | jq '.raw.heartRate'
# Output: 75.1
```

### Test 2: History Endpoint

```bash
# Get 30 data points (which means 30 CSV rows will be iterated)
curl http://localhost:8000/api/telemetry/history?limit=30 | jq '.items | length'
# Output: 30
```

### Test 3: Real-Time Dashboard Loop

Monitor the dashboard for 2-3 minutes and verify:

- ✓ Charts are continuously updating
- ✓ Values change every 2 seconds
- ✓ No "Loading..." or error messages
- ✓ Heart rate stays in 60-180 range
- ✓ SpO2 stays in 85-100 range
- ✓ Temperature stays in 36-40°C range

## Data Update Timeline

**Simulated Real-Time Rate:**

- Dashboard polls every 2 seconds
- Each poll gets 1 new CSV row
- With 197 total rows: cycles through all data every 394 seconds (~6.5 minutes)
- Creates continuous seamless looping

**To adjust update rate, modify Dashboard.tsx:**

```tsx
// Current: 2000ms (2 seconds)
const interval = setInterval(() => {
  // Update code
}, 2000); // Change this value
```

**To adjust the CSV cycling rate on API side:**

```python
# Each endpoint call advances the CSV row
# Faster/slower based on how frequently dashboard makes requests
# Default: 1 row per API call
```

## Troubleshooting

### Issue: `"dataSource": "random fallback"`

**Solution:** CSV files not found

- Verify path: `../police-personnel-data-realtime/` from the API file location
- Check that CSV files exist with correct names
- Ensure CSV has header row with column names: HeartRate, SpO2, Temperature, etc.

### Issue: Data not updating in dashboard

**Solution:** Check network/API connection

```bash
# Verify API is running
curl http://localhost:8000/health
# Should return: {"status": "ok"}
```

### Issue: Parsing errors in console

**Solution:** CSV format issue

- Open CSV file in Excel/text editor
- Verify required columns exist: HeartRate, SpO2, Temperature, Acc_X, Acc_Y, Acc_Z, Gyro_X, Gyro_Y, Gyro_Z
- Check for missing values (empty cells)

## Performance Notes

- **CSV Loading:** Single-threaded, happens once at startup (~100-500ms for typical files)
- **Memory Usage:** Minimal (typically <5MB for 200 rows)
- **API Response Time:** <10ms per request
- **Recommended Dashboard Update Interval:** 2000ms (2 seconds)

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────┐
│              Police Health Dashboard                     │
│         (Next.js - updates every 2 seconds)              │
└──────┬──────────────────────────────────────────────────┘
       │ HTTP GET /api/telemetry/current
       │ HTTP GET /api/telemetry/history
       │
┌──────▼──────────────────────────────────────────────────┐
│         Police Health API (FastAPI)                      │
│ - CSV Data Loader (initialized at startup)              │
│ - Real-time data cycling                                │
│ - Fallback to random data                               │
└──────┬──────────────────────────────────────────────────┘
       │ Reads sequentially
       │ Cycles back to start
       │
┌──────▼──────────────────────────────────────────────────┐
│    CSV Files (Real Personnel Data)                       │
│ police-personnel-data-realtime/                          │
├──────────────────────────────────────────────────────────┤
│ • 0498 - Officer A - 47 rows                             │
│ • 699 - Officer B - 98 rows                              │
│ • 949 - Officer C - 52 rows                              │
│ Total: 197 rows of real data                             │
└──────────────────────────────────────────────────────────┘
```

## Files Modified/Created

1. **Modified:** `police_health_api.py`
   - Added `CSVDataLoader` class
   - Updated data generation functions
   - New `/api/system/csv-status` endpoint

2. **Created:** `CSV_INTEGRATION_GUIDE.md`
   - Complete integration documentation

3. **Created:** `requirements.txt`
   - Python dependencies

4. **Created:** `start-api.bat`
   - Windows startup script for convenience

## Next Steps

Once everything is working:

1. Monitor the dashboard for accurate real-time data display
2. Verify metrics are calculated correctly from CSV values
3. Test AI insights with real data patterns
4. Consider adding:
   - Database persistence
   - Multi-officer filtering
   - Historical data export
   - Alert thresholds based on CSV patterns
