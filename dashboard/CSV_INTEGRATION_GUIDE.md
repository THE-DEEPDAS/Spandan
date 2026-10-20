# Real-Time CSV Data Integration Guide

## Overview

The Police Health API now supports real-time data streaming from CSV files located in the `police-personnel-data-realtime/` directory. The API automatically loads all CSV files on startup and cycles through the data rows with each API request.

## How It Works

### Data Flow

1. **CSV Loading**: On API startup, the `CSVDataLoader` scans the `../police-personnel-data-realtime/` directory for all `.csv` files
2. **Data Cycling**: Each time an endpoint is called, it retrieves the next row from the CSV data cyclically
3. **Simulated Real-Time**: With the 2-second update interval in the dashboard, data cycles through CSV rows at ~2-3 rows/second
4. **Fallback**: If no CSV data is available, the API falls back to random data generation

### CSV File Requirements

CSV files should contain the following columns (as seen in your police personnel data):

- `HeartRate` - Heart rate in BPM (60-180)
- `SpO2` - Oxygen saturation (85-100%)
- `Temperature` - Body temperature in °C (36-40)
- `Acc_X`, `Acc_Y`, `Acc_Z` - Acceleration values
- `Gyro_X`, `Gyro_Y`, `Gyro_Z` - Gyroscope values

Additional columns are ignored but won't cause errors.

## API Endpoints

### New Endpoint: CSV Status

```
GET /api/system/csv-status
```

Returns:

```json
{
  "hasData": true,
  "totalRows": 145,
  "currentIndex": 42,
  "dataSource": "real-time CSV"
}
```

### Updated Endpoint: System Status

```
GET /api/system/status
```

Now returns `watchSync: "active"` when CSV data is loaded, `"offline"` otherwise.

### Existing Endpoints (Now Using CSV Data)

- `GET /api/telemetry/current` - Gets latest data point (from CSV)
- `GET /api/telemetry/history?limit=30` - Gets 30 latest points (from CSV)

## Running the API

```bash
# Make sure you're in the Police-Project-Data-Science directory
cd Police-Project-Data-Science

# Start the API
pip install fastapi uvicorn requests python-dotenv
uvicorn police_health_api:app --reload --port 8000
```

The API will:

1. Scan for CSV files in `../police-personnel-data-realtime/`
2. Print loading status to console:
   ```
   Loaded 47 rows from 0498 - PankilKumar Arjunbhai Patel - 1051DB1C7222 - 2026-03-27.csv
   Loaded 98 rows from 699 - Ashvinbhai chinmanbhai chaudhari - 1051DB1C72AE - 2026-03-27.csv
   ...
   Total rows loaded: 245
   ```

## Dashboard Integration

The dashboard already has a 2-second update interval that pulls from:

- `GET /api/telemetry/current` - For individual data points
- `GET /api/telemetry/history?limit=30` - For the 30-point history

With CSV data cycling, you'll see **real personnel data** updating every 2 seconds, simulating continuous real-time monitoring.

**Data Update Rate:**

- 1 API call per 2 seconds = ~30 data points per minute
- Each CSV row represents ~2 seconds of sensor data
- Cycles through available CSV rows continuously

## Data Validation

The API includes safeguards:

- Heart rate clamped to 60-180 BPM
- SpO2 clamped to 85-100%
- Temperature clamped to 36-40°C
- If CSV parsing fails, falls back to random data
- Missing columns are handled gracefully

## Monitoring Real-Time Updates

To verify real-time updates are working:

1. **Check CSV Loading**:

   ```bash
   curl http://localhost:8000/api/system/csv-status
   ```

   Should show `"dataSource": "real-time CSV"` with `totalRows > 0`

2. **Watch Data Change**:

   ```bash
   # Run twice with 2-second delay
   curl http://localhost:8000/api/telemetry/current
   sleep 2
   curl http://localhost:8000/api/telemetry/current
   ```

   Timestamps should differ, data should change

3. **View Dashboard**:
   Open the browser and watch the charts update every 2 seconds with real CSV data

## Future Enhancements

- [ ] Real file watching (auto-reload when new CSV files arrive)
- [ ] Per-officer data filtering
- [ ] Configurable update intervals (30s, 60s, custom)
- [ ] Time-series compression for long-term storage
- [ ] Database integration for persistent storage
