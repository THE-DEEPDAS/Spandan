#!/usr/bin/env python3
"""
Diagnostic script to inspect CSV data and verify cycling works correctly.
Run this to see what's actually in your CSV files.
"""

import csv
import glob
import os
from pathlib import Path

CSV_DIR = "../police-personnel-data-realtime"

def inspect_csv_data():
    """Inspect CSV files and show data samples."""
    print("=" * 70)
    print("CSV Data Diagnostic Report")
    print("=" * 70)
    
    csv_files = glob.glob(os.path.join(CSV_DIR, "*.csv"))
    
    if not csv_files:
        print(f"\n❌ ERROR: No CSV files found in {CSV_DIR}")
        return
    
    all_rows = []
    
    for csv_file in csv_files:
        print(f"\n📄 File: {os.path.basename(csv_file)}")
        print("-" * 70)
        
        try:
            with open(csv_file, 'r', encoding='utf-8') as f:
                # Skip header section until we find the actual data header
                content = f.read()
                start_pos = content.find("App_Date")
                
                if start_pos == -1:
                    print(f"  ⚠️  Could not find data header in file")
                    continue
                
                # Get the data portion starting from "App_Date"
                data_content = content[start_pos:]
                data_lines = data_content.split('\n')
                
                # Parse with csv.DictReader
                reader = csv.DictReader(data_lines)
                rows = [r for r in reader if r.get('HeartRate')]  # Filter out empty rows
                all_rows.extend(rows)
                
                print(f"Total rows in file: {len(rows)}")
                
                if len(rows) > 0:
                    # Show first 3 rows
                    print(f"\n  First 3 rows of data:")
                    for i, row in enumerate(rows[:3]):
                        hr = row.get('HeartRate', 'N/A')
                        spo2 = row.get('SpO2', 'N/A')
                        temp = row.get('Temperature', 'N/A')
                        print(f"    Row {i}: HR={hr}, SpO2={spo2}, Temp={temp}")
                    
                    # Show last 3 rows
                    print(f"\n  Last 3 rows of data:")
                    for i, row in enumerate(rows[-3:], start=len(rows)-3):
                        hr = row.get('HeartRate', 'N/A')
                        spo2 = row.get('SpO2', 'N/A')
                        temp = row.get('Temperature', 'N/A')
                        print(f"    Row {i}: HR={hr}, SpO2={spo2}, Temp={temp}")
                    
                    # Check for value changes in first 5 rows
                    if len(rows) >= 2:
                        print(f"\n  Consecutive row comparison (first 5):")
                        for i in range(min(5, len(rows)-1)):
                            hr1 = rows[i].get('HeartRate', 'N/A')
                            hr2 = rows[i+1].get('HeartRate', 'N/A')
                            match = "SAME" if hr1 == hr2 else "different"
                            print(f"    Row {i} → Row {i+1}: {hr1} → {hr2} ({match})")
        
        except Exception as e:
            print(f"  ❌ Error reading file: {e}")
    
    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"CSV Files found: {len(csv_files)}")
    print(f"Total rows across all files: {len(all_rows)}")
    
    if len(all_rows) > 0:
        print(f"\n✓ CSV data is ready to use")
        print(f"\nWhen API cycles through data:")
        print(f"  - Each API call gets the next row")
        print(f"  - Dashboard polls every 2 seconds")
        print(f"  - With {len(all_rows)} rows, cycle completes in {len(all_rows) * 2} seconds (~{len(all_rows) * 2 / 60:.1f} minutes)")
        
        # Check value ranges
        print(f"\n📊 Data Value Ranges:")
        hr_values = []
        spo2_values = []
        temp_values = []
        
        for row in all_rows:
            try:
                hr = float(row.get('HeartRate', 0))
                spo2 = float(row.get('SpO2', 0))
                temp = float(row.get('Temperature', 0))
                if hr > 0: hr_values.append(hr)
                if spo2 > 0: spo2_values.append(spo2)
                if temp > 0: temp_values.append(temp)
            except:
                pass
        
        if hr_values:
            print(f"  Heart Rate: {min(hr_values):.1f} - {max(hr_values):.1f} BPM (avg: {sum(hr_values)/len(hr_values):.1f})")
        if spo2_values:
            print(f"  SpO2: {min(spo2_values):.1f} - {max(spo2_values):.1f}% (avg: {sum(spo2_values)/len(spo2_values):.1f})")
        if temp_values:
            print(f"  Temperature: {min(temp_values):.1f} - {max(temp_values):.1f}°C (avg: {sum(temp_values)/len(temp_values):.1f})")
    
    else:
        print(f"\n❌ No data rows found in CSV files")

if __name__ == "__main__":
    inspect_csv_data()
