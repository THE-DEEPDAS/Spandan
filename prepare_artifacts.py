import os
import numpy as np
import pandas as pd
from joblib import dump
from scipy.signal import find_peaks
from scipy.stats import entropy
from sklearn.preprocessing import StandardScaler

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TRAIN_PATH = os.path.join(BASE_DIR, "data", "train", "combined_train.csv")
ARTIFACT_DIR = os.path.join(BASE_DIR, "artifacts")
WINDOW = 60
STEP = 10
PHYSICAL_FEATURES = [
    "heart_rate", "spo2", "skin_temperature",
    "accel_x", "accel_y", "accel_z",
    "gyro_x", "gyro_y", "gyro_z",
    "lat_delta", "lon_delta", "altitude", "time_delta",
]


def movement_entropy(signal):
    histogram, _ = np.histogram(signal, bins=10, density=True)
    histogram += 1e-8
    return float(entropy(histogram))


def window_features(window):
    acceleration = np.sqrt(
        window["accel_x"] ** 2 + window["accel_y"] ** 2 + window["accel_z"] ** 2
    )
    gyroscope = np.sqrt(
        window["gyro_x"] ** 2 + window["gyro_y"] ** 2 + window["gyro_z"] ** 2
    )
    displacement = np.sqrt(window["lat_delta"] ** 2 + window["lon_delta"] ** 2)
    speed = np.mean(displacement / (window["time_delta"] + 1e-6))
    return [
        float(np.var(acceleration)),
        float(np.var(gyroscope)),
        movement_entropy(acceleration),
        float(len(find_peaks(acceleration)[0])),
        float(np.var(window["heart_rate"])),
        float((window["heart_rate"].iloc[-1] - window["heart_rate"].iloc[0]) / len(window)),
        float(speed),
    ]


def main():
    frame = pd.read_csv(TRAIN_PATH)
    os.makedirs(ARTIFACT_DIR, exist_ok=True)

    physical_scaler = StandardScaler().fit(frame[PHYSICAL_FEATURES].to_numpy(dtype=np.float32))
    dump(physical_scaler, os.path.join(ARTIFACT_DIR, "physical_scaler.joblib"))

    windows = []
    for _, officer_frame in frame.groupby("badge_id"):
        officer_frame = officer_frame.sort_values("timestamp").reset_index(drop=True)
        for start in range(0, len(officer_frame) - WINDOW, STEP):
            windows.append(window_features(officer_frame.iloc[start:start + WINDOW]))

    distraction_scaler = StandardScaler().fit(np.asarray(windows, dtype=np.float32))
    dump(distraction_scaler, os.path.join(ARTIFACT_DIR, "distraction_scaler.joblib"))
    print(f"Created scalers in {ARTIFACT_DIR}")
    print(f"Physical rows: {len(frame):,}")
    print(f"Distraction windows: {len(windows):,}")


if __name__ == "__main__":
    main()
