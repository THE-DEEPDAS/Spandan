import os
import glob
import pandas as pd
import numpy as np

src_dir = "/Users/akshdharodiya/Desktop/projects/police_watch/real_data/individual_person_data"
out_base = "/Users/akshdharodiya/Desktop/projects/police_watch/18_09_26/data"

train_dir = os.path.join(out_base, "train")
val_dir = os.path.join(out_base, "val")
test_dir = os.path.join(out_base, "test")

for d in [train_dir, val_dir, test_dir]:
    os.makedirs(d, exist_ok=True)

csv_files = [f for f in glob.glob(os.path.join(src_dir, "*.csv")) if not os.path.basename(f).startswith("_")]
csv_files.sort()

print(f"Found {len(csv_files)} officer CSV files to split chronologically.")

all_train = []
all_val = []
all_test = []

split_summary = []

for fpath in csv_files:
    fname = os.path.basename(fpath)
    base_name = fname.replace(".csv", "")
    
    df = pd.read_csv(fpath)
    if len(df) == 0:
        continue
        
    df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')
    df = df.dropna(subset=['timestamp']).sort_values('timestamp').reset_index(drop=True)
    n_rows = len(df)
    
    if n_rows < 10:
        continue
        
    # Map and clean features
    # 1. heart_rate
    df['heart_rate'] = pd.to_numeric(df['pulse'], errors='coerce').ffill().bfill().fillna(80.0)
    df.loc[df['heart_rate'] <= 35, 'heart_rate'] = 80.0 # remove 0/disconnect artifact
    
    # 2. spo2
    df['spo2'] = pd.to_numeric(df['spo2'], errors='coerce').ffill().bfill().fillna(95.0)
    df.loc[df['spo2'] <= 60, 'spo2'] = 95.0
    
    # 3. skin_temperature (baseline 36.5)
    if 'temperature' in df.columns:
        df['skin_temperature'] = pd.to_numeric(df['temperature'], errors='coerce').fillna(36.5)
    else:
        df['skin_temperature'] = 36.5
        
    # 4, 5, 6. accel_x, accel_y, accel_z
    df['accel_x'] = pd.to_numeric(df['accel_x'], errors='coerce').ffill().bfill().fillna(0.0)
    df['accel_y'] = pd.to_numeric(df['accel_y'], errors='coerce').ffill().bfill().fillna(0.0)
    df['accel_z'] = pd.to_numeric(df['accel_z'], errors='coerce').ffill().bfill().fillna(0.98)
    
    # 7, 8, 9. gyro_x, gyro_y, gyro_z (baseline 0.0)
    df['gyro_x'] = 0.0
    df['gyro_y'] = 0.0
    df['gyro_z'] = 0.0
    
    # 10, 11, 12, 13. lat_delta, lon_delta, altitude, time_delta
    df['lat_delta'] = pd.to_numeric(df['lat_delta'], errors='coerce').fillna(0.0)
    df['lon_delta'] = pd.to_numeric(df['lon_delta'], errors='coerce').fillna(0.0)
    df['altitude'] = pd.to_numeric(df['altitude'], errors='coerce').ffill().bfill().fillna(20.0)
    df['time_delta'] = pd.to_numeric(df['time_delta'], errors='coerce').fillna(30.0)
    
    speed = pd.to_numeric(df['approx_speed_kmh'], errors='coerce').fillna(0.0)
    
    # Kinematic & physiological heuristic labeling:
    # Compute acceleration variance over rolling window
    acc_mag = np.sqrt(df['accel_x']**2 + df['accel_y']**2 + df['accel_z']**2)
    acc_var = acc_mag.rolling(window=5, min_periods=1).var().fillna(0.0)
    
    # Target rule:
    # 1 = PHYSICAL ACTIVITY: High movement variance (>0.12) OR speed > 4.5 km/h
    # 0 = STRESS: Stationary (acc_var <= 0.12 and speed < 2.0) BUT elevated heart rate (>90 bpm) OR spo2 < 91
    # 2 = NORMAL: Routine resting/moderate baseline
    targets = np.full(n_rows, 2, dtype=np.int64) # default normal
    
    is_activity = (acc_var > 0.12) | (speed > 4.5)
    is_stress = (~is_activity) & ((df['heart_rate'] > 90.0) | (df['spo2'] < 91.0))
    
    targets[is_activity] = 1
    targets[is_stress] = 0
    
    df['target'] = targets
    
    # Temporal order-wise split: 70% Train, 15% Val, 15% Test
    idx_train = int(0.70 * n_rows)
    idx_val = int(0.85 * n_rows)
    
    df_train = df.iloc[:idx_train].copy()
    df_val = df.iloc[idx_train:idx_val].copy()
    df_test = df.iloc[idx_val:].copy()
    
    # Save individual officer split CSVs
    df_train.to_csv(os.path.join(train_dir, f"{base_name}_train.csv"), index=False)
    df_val.to_csv(os.path.join(val_dir, f"{base_name}_val.csv"), index=False)
    df_test.to_csv(os.path.join(test_dir, f"{base_name}_test.csv"), index=False)
    
    all_train.append(df_train)
    all_val.append(df_val)
    all_test.append(df_test)
    
    split_summary.append({
        'officer': base_name,
        'total_rows': n_rows,
        'train_rows': len(df_train),
        'val_rows': len(df_val),
        'test_rows': len(df_test),
        'train_start': str(df_train['timestamp'].min()),
        'train_end': str(df_train['timestamp'].max()),
        'val_start': str(df_val['timestamp'].min()),
        'val_end': str(df_val['timestamp'].max()),
        'test_start': str(df_test['timestamp'].min()),
        'test_end': str(df_test['timestamp'].max())
    })

# Combine master datasets
combined_train = pd.concat(all_train, ignore_index=True)
combined_val = pd.concat(all_val, ignore_index=True)
combined_test = pd.concat(all_test, ignore_index=True)

combined_train.to_csv(os.path.join(train_dir, "combined_train.csv"), index=False)
combined_val.to_csv(os.path.join(val_dir, "combined_val.csv"), index=False)
combined_test.to_csv(os.path.join(test_dir, "combined_test.csv"), index=False)

df_split_summary = pd.DataFrame(split_summary)
df_split_summary.to_csv(os.path.join(out_base, "_split_summary.csv"), index=False)

print("\n" + "="*50)
print("✅ Temporal 70 / 15 / 15 Split Completed!")
print("="*50)
print(f"Total Officers Processed : {len(split_summary)}")
print(f"Combined Train Rows      : {len(combined_train):,} ({len(combined_train)/(len(combined_train)+len(combined_val)+len(combined_test))*100:.1f}%)")
print(f"Combined Val Rows        : {len(combined_val):,} ({len(combined_val)/(len(combined_train)+len(combined_val)+len(combined_test))*100:.1f}%)")
print(f"Combined Test Rows       : {len(combined_test):,} ({len(combined_test)/(len(combined_train)+len(combined_val)+len(combined_test))*100:.1f}%)")
print("\nTarget Class Distribution in Test Set:")
print(combined_test['target'].value_counts())
