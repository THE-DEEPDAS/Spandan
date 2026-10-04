# 🚀 QUICK START - Real-Time CSV Integration

## ⚡ 30-Second Setup

```bash
cd Police-Project-Data-Science
pip install -r requirements.txt
uvicorn police_health_api:app --reload --port 8000
```

Then open: `http://localhost:3000` (your dashboard)

## 📊 What You'll See

- **Real officer health data** from CSV files cycling every 2 seconds
- **Heart rate, SpO2, temperature** updating live on charts
- **Actual sensor data** (acceleration, gyroscope) from personnel
- **197 rows of real data** looping continuously

## 🔍 Quick Verification

```bash
# Verify CSV loaded
curl http://localhost:8000/api/system/csv-status

# Expected response shows:
# "hasData": true
# "totalRows": 197
# "dataSource": "real-time CSV"
```

## 📁 Files Modified/Created

| File                         | Status      | Purpose                     |
| ---------------------------- | ----------- | --------------------------- |
| `police_health_api.py`       | ✏️ MODIFIED | Now loads & cycles CSV data |
| `requirements.txt`           | ✨ NEW      | Python dependencies         |
| `start-api.bat`              | ✨ NEW      | Windows startup script      |
| `test_api.py`                | ✨ NEW      | Automated test suite        |
| `CSV_INTEGRATION_GUIDE.md`   | 📖 NEW      | Full technical guide        |
| `TESTING_GUIDE.md`           | 📖 NEW      | Testing procedures          |
| `DATA_FLOW_VISUALIZATION.md` | 📊 NEW      | Architecture diagrams       |
| `SETUP_COMPLETE.md`          | 📖 NEW      | Detailed setup guide        |

## 🎯 Real-Time Timeline

**Per 2 seconds (dashboard refresh):**

- 1 new CSV row displayed
- ~30 rows per minute
- 197 total rows cycle every 6.5 minutes
- **Seamless continuous looping**

## 🧪 Run Tests

```bash
python test_api.py
```

Expected output:

```
✓ API Health Check
✓ CSV Status (197 rows)
✓ Current Data (from CSV)
✓ History (30 points)
✓ Data Cycling (changes every 2s)

Result: 5/5 tests passed 🎉
```

## 📡 Core API Endpoints

| Endpoint                              | What it does      | Returns                   |
| ------------------------------------- | ----------------- | ------------------------- |
| `GET /api/telemetry/current`          | Latest data point | 1 telemetry reading       |
| `GET /api/telemetry/history?limit=30` | Last 30 points    | 30 readings from CSV      |
| `GET /api/system/csv-status`          | CSV data info     | Row count, cycling status |
| `GET /api/system/status`              | System health     | API status                |

## ⚙️ Configuration

**To change update rate** (in `src/components/PoliceHealth/Dashboard.tsx`):

```tsx
// Current: 2 seconds
const interval = setInterval(() => {
  // Update
}, 2000); // Change this number (milliseconds)
```

**To add more CSV files:**

- Drop `.csv` files in `../police-personnel-data-realtime/`
- Need columns: HeartRate, SpO2, Temperature, Acc_X/Y/Z, Gyro_X/Y/Z
- Auto-loads on next API startup

## ❓ Troubleshooting

| Problem                | Solution                                                     |
| ---------------------- | ------------------------------------------------------------ |
| "random fallback"      | CSV files not found - check path                             |
| Dashboard not updating | Is API running? Test: `curl http://localhost:8000/health`    |
| CSV parsing error      | Verify column names in CSV file                              |
| Data seems static      | Wait 2+ seconds or check if API is cycling (use test_api.py) |

## 📚 Detailed Guides

Need more info? Check these files:

- 📖 **Setup details**: `SETUP_COMPLETE.md`
- 🔧 **Technical deep-dive**: `CSV_INTEGRATION_GUIDE.md`
- 🧪 **Testing procedures**: `TESTING_GUIDE.md`
- 📊 **Architecture & data flow**: `DATA_FLOW_VISUALIZATION.md`

## ✅ Success Checklist

- [ ] API starts without errors
- [ ] CSV files loaded (check: `curl http://localhost:8000/api/system/csv-status`)
- [ ] Dashboard updates every 2 seconds
- [ ] Heart rate values are real (60-180 range)
- [ ] SpO2 values are real (85-100 range)
- [ ] Temperature values are real (36-40°C range)
- [ ] Charts show smooth data progression
- [ ] Data cycles back to start after 6-7 minutes

---

**Status: ✅ READY TO RUN**

Your Police Health API is now powered by real CSV data! 🎉

All officer telemetry is live and cycling every 2 seconds.
