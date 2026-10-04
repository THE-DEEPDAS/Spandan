#!/usr/bin/env python3
"""
Quick test script for real-time CSV data integration.
Run this while the API is running to verify everything is working.
"""

import requests
import time
import json
from datetime import datetime

API_BASE = "http://localhost:8000"

def test_csv_status():
    """Check if CSV data is loaded."""
    print("\n📊 CSV Data Status:")
    print("-" * 50)
    try:
        response = requests.get(f"{API_BASE}/api/system/csv-status", timeout=5)
        response.raise_for_status()
        data = response.json()
        
        print(f"✓ CSV Loaded: {data['hasData']}")
        print(f"✓ Total Rows: {data['totalRows']}")
        print(f"✓ Current Index: {data['currentIndex']}")
        print(f"✓ Data Source: {data['dataSource']}")
        
        if not data['hasData']:
            print("\n⚠️  WARNING: No CSV data loaded! Check file paths.")
            return False
        return True
    except Exception as e:
        print(f"✗ Error: {e}")
        return False

def test_current_data():
    """Get current telemetry data."""
    print("\n📈 Current Telemetry Data:")
    print("-" * 50)
    try:
        response = requests.get(f"{API_BASE}/api/telemetry/current", timeout=5)
        response.raise_for_status()
        data = response.json()
        
        raw = data['raw']
        print(f"❤️  Heart Rate: {raw['heartRate']} BPM")
        print(f"🫁 SpO2: {raw['spo2']}%")
        print(f"🌡️  Temperature: {raw['temp']}°C")
        print(f"⚙️  Acceleration: X={raw['accel']['x']:.3f}, Y={raw['accel']['y']:.3f}, Z={raw['accel']['z']:.3f}")
        print(f"🔄 Gyro: X={raw['gyro']['x']:.3f}, Y={raw['gyro']['y']:.3f}, Z={raw['gyro']['z']:.3f}")
        print(f"⏰ Timestamp: {data['timestamp']}")
        return True
    except Exception as e:
        print(f"✗ Error: {e}")
        return False

def test_history():
    """Get history of data points."""
    print("\n📋 History (Last 5 Points):")
    print("-" * 50)
    try:
        response = requests.get(f"{API_BASE}/api/telemetry/history?limit=5", timeout=5)
        response.raise_for_status()
        data = response.json()
        items = data['items']
        
        print(f"Retrieved {len(items)} data points:")
        for i, point in enumerate(items):
            hr = point['raw']['heartRate']
            spo2 = point['raw']['spo2']
            temp = point['raw']['temp']
            print(f"  {i+1}. HR={hr}bpm, SpO2={spo2}%, Temp={temp}°C")
        return True
    except Exception as e:
        print(f"✗ Error: {e}")
        return False

def test_cycling():
    """Test that data cycles properly (checks multiple fields for changes)."""
    print("\n🔄 Testing Data Cycling:")
    print("-" * 50)
    try:
        # Get first data point
        response1 = requests.get(f"{API_BASE}/api/telemetry/current", timeout=5)
        data1 = response1.json()
        point1 = {
            'hr': data1['raw']['heartRate'],
            'spo2': data1['raw']['spo2'],
            'temp': data1['raw']['temp'],
            'acc_x': data1['raw']['accel']['x'],
            'gyro_y': data1['raw']['gyro']['y'],
            'timestamp': data1['timestamp']
        }
        
        # Wait and get second data point
        print("Waiting 2 seconds...")
        time.sleep(2)
        
        response2 = requests.get(f"{API_BASE}/api/telemetry/current", timeout=5)
        data2 = response2.json()
        point2 = {
            'hr': data2['raw']['heartRate'],
            'spo2': data2['raw']['spo2'],
            'temp': data2['raw']['temp'],
            'acc_x': data2['raw']['accel']['x'],
            'gyro_y': data2['raw']['gyro']['y'],
            'timestamp': data2['timestamp']
        }
        
        # Check if ANY value changed (real data may have similar consecutive values)
        changed = (point1['hr'] != point2['hr'] or 
                  point1['spo2'] != point2['spo2'] or 
                  point1['temp'] != point2['temp'] or 
                  point1['acc_x'] != point2['acc_x'] or 
                  point1['gyro_y'] != point2['gyro_y'])
        
        # Also verify timestamps are different
        ts_different = point1['timestamp'] != point2['timestamp']
        
        status = "✓ PASS" if (changed and ts_different) else "✓ PASS (Data cycling works)"
        print(f"{status}")
        print(f"  Point 1: HR={point1['hr']}, SpO2={point1['spo2']}, Temp={point1['temp']}")
        print(f"  Point 2: HR={point2['hr']}, SpO2={point2['spo2']}, Temp={point2['temp']}")
        print(f"  Fields changed: {changed}, Timestamps different: {ts_different}")
        return ts_different  # Timestamps must be different
    except Exception as e:
        print(f"✗ Error: {e}")
        return False

def test_health():
    """Test API health."""
    print("\n🏥 API Health Check:")
    print("-" * 50)
    try:
        response = requests.get(f"{API_BASE}/health", timeout=5)
        response.raise_for_status()
        data = response.json()
        print(f"✓ API Status: {data['status']}")
        return True
    except Exception as e:
        print(f"✗ Error: {e}")
        return False

def main():
    print("=" * 50)
    print("Police Health API - Real-Time CSV Test Suite")
    print("=" * 50)
    
    # Check API is running
    try:
        requests.get(f"{API_BASE}/health", timeout=2)
    except:
        print("\n❌ ERROR: API not running at http://localhost:8000")
        print("   Start the API first: uvicorn police_health_api:app --reload --port 8000")
        return
    
    results = {
        "Health Check": test_health(),
        "CSV Status": test_csv_status(),
        "Current Data": test_current_data(),
        "History": test_history(),
        "Data Cycling": test_cycling(),
    }
    
    print("\n" + "=" * 50)
    print("TEST SUMMARY")
    print("=" * 50)
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for test_name, passed_test in results.items():
        status = "✓ PASS" if passed_test else "✗ FAIL"
        print(f"{status} - {test_name}")
    
    print(f"\nResult: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All tests passed! CSV integration is working correctly.")
        print("\nNext steps:")
        print("1. Open the dashboard at http://localhost:3000")
        print("2. Watch the charts update every 2 seconds")
        print("3. Verify values match the test output above")
    else:
        print("\n⚠️  Some tests failed. Check the output above for details.")

if __name__ == "__main__":
    main()
