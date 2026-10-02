import json
import os

import gradio as gr
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from joblib import load
from scipy.signal import find_peaks
from scipy.stats import entropy

try:
    import spaces
except ImportError:
    class _LocalSpaces:
        @staticmethod
        def GPU(function):
            return function

    spaces = _LocalSpaces()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.path.join(BASE_DIR, "best_models")
ARTIFACT_DIR = os.path.join(BASE_DIR, "artifacts")
DEVICE = torch.device("cpu")
WINDOW_SIZE = 60
PHYSICAL_LABELS = {0: "STRESS", 1: "PHYSICAL ACTIVITY", 2: "NORMAL"}
DISTRACTION_LABELS = {0: "FOCUSED", 1: "DISTRACTED"}


class WearableMLP(nn.Module):
    def __init__(self):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(13, 256), nn.BatchNorm1d(256), nn.ReLU(), nn.Dropout(0.3),
            nn.Linear(256, 128), nn.BatchNorm1d(128), nn.ReLU(), nn.Dropout(0.3),
            nn.Linear(128, 64), nn.BatchNorm1d(64), nn.ReLU(), nn.Dropout(0.3),
            nn.Linear(64, 3),
        )

    def forward(self, inputs):
        return self.net(inputs)


class DistractionNet(nn.Module):
    def __init__(self):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(7, 64), nn.BatchNorm1d(64), nn.ReLU(), nn.Dropout(0.3),
            nn.Linear(64, 32), nn.BatchNorm1d(32), nn.ReLU(), nn.Dropout(0.2),
            nn.Linear(32, 1), nn.Sigmoid(),
        )

    def forward(self, inputs):
        return self.net(inputs).squeeze(1)


def load_model(model, filename):
    path = os.path.join(MODEL_DIR, filename)
    if not os.path.exists(path):
        raise FileNotFoundError(f"Missing model file: {path}")
    model.load_state_dict(torch.load(path, map_location=DEVICE))
    model.eval()
    return model


physical_model = load_model(WearableMLP(), "model_1c_state_scratch.pt")
distraction_model = load_model(DistractionNet(), "model_2c_distraction_scratch.pt")
physical_scaler = load(os.path.join(ARTIFACT_DIR, "physical_scaler.joblib"))
distraction_scaler = load(os.path.join(ARTIFACT_DIR, "distraction_scaler.joblib"))


def check_values(values):
    values = np.asarray(values, dtype=np.float32)
    if not np.isfinite(values).all():
        raise gr.Error("All input values must be finite numbers.")
    return values


@spaces.GPU
def predict_physical_state(
    heart_rate, spo2, skin_temperature, accel_x, accel_y, accel_z,
    gyro_x, gyro_y, gyro_z, lat_delta, lon_delta, altitude, time_delta,
):
    values = check_values([
        heart_rate, spo2, skin_temperature, accel_x, accel_y, accel_z,
        gyro_x, gyro_y, gyro_z, lat_delta, lon_delta, altitude, time_delta,
    ]).reshape(1, -1)
    scaled = physical_scaler.transform(values).astype(np.float32)
    with torch.inference_mode():
        probabilities = torch.softmax(
            physical_model(torch.from_numpy(scaled)), dim=1
        )[0].numpy()
    class_id = int(np.argmax(probabilities))
    return {
        "model": "model_1c_state_scratch",
        "task": "physical_state",
        "class_id": class_id,
        "state": PHYSICAL_LABELS[class_id],
        "probability": round(float(probabilities[class_id]), 6),
        "probabilities": {
            PHYSICAL_LABELS[index]: round(float(value), 6)
            for index, value in enumerate(probabilities)
        },
        "alert": class_id == 0,
    }


def calculate_window_features(samples):
    if isinstance(samples, dict):
        samples = samples.get("samples")
    if not isinstance(samples, list) or len(samples) != WINDOW_SIZE:
        raise gr.Error("The distraction input must contain exactly 60 samples.")
    frame = pd.DataFrame(samples)
    required = [
        "heart_rate", "accel_x", "accel_y", "accel_z",
        "gyro_x", "gyro_y", "gyro_z", "lat_delta", "lon_delta", "time_delta",
    ]
    missing = [name for name in required if name not in frame.columns]
    if missing:
        raise gr.Error(f"Missing sample fields: {', '.join(missing)}")
    frame = frame[required].astype(np.float32)
    if not np.isfinite(frame.to_numpy()).all():
        raise gr.Error("All sample values must be finite numbers.")
    acceleration = np.sqrt(
        frame["accel_x"] ** 2 + frame["accel_y"] ** 2 + frame["accel_z"] ** 2
    ).to_numpy()
    gyroscope = np.sqrt(
        frame["gyro_x"] ** 2 + frame["gyro_y"] ** 2 + frame["gyro_z"] ** 2
    ).to_numpy()
    displacement = np.sqrt(frame["lat_delta"] ** 2 + frame["lon_delta"] ** 2)
    speed = np.mean(displacement / (frame["time_delta"] + 1e-6))
    histogram, _ = np.histogram(acceleration, bins=10, density=True)
    histogram += 1e-8
    return np.asarray([
        np.var(acceleration),
        np.var(gyroscope),
        entropy(histogram),
        len(find_peaks(acceleration)[0]),
        np.var(frame["heart_rate"].to_numpy()),
        (frame["heart_rate"].iloc[-1] - frame["heart_rate"].iloc[0]) / len(frame),
        speed,
    ], dtype=np.float32)


@spaces.GPU
def predict_distraction(samples_json):
    try:
        samples = json.loads(samples_json)
    except (TypeError, json.JSONDecodeError) as error:
        raise gr.Error("Enter valid JSON containing a samples array.") from error
    features = calculate_window_features(samples).reshape(1, -1)
    scaled = distraction_scaler.transform(features).astype(np.float32)
    with torch.inference_mode():
        probability = float(distraction_model(torch.from_numpy(scaled))[0].item())
    class_id = int(probability >= 0.5)
    return {
        "model": "model_2c_distraction_scratch",
        "task": "focus_distraction",
        "class_id": class_id,
        "state": DISTRACTION_LABELS[class_id],
        "probability": round(probability, 6),
        "alert": class_id == 1,
        "window_size": WINDOW_SIZE,
    }


physical_inputs = [
    gr.Number(label="Heart rate", value=80),
    gr.Number(label="SpO2", value=97),
    gr.Number(label="Skin temperature", value=36.5),
    gr.Number(label="Accel X", value=0),
    gr.Number(label="Accel Y", value=0),
    gr.Number(label="Accel Z", value=9.81),
    gr.Number(label="Gyro X", value=0),
    gr.Number(label="Gyro Y", value=0),
    gr.Number(label="Gyro Z", value=0),
    gr.Number(label="Latitude delta", value=0),
    gr.Number(label="Longitude delta", value=0),
    gr.Number(label="Altitude", value=20),
    gr.Number(label="Time delta", value=30),
]

with gr.Blocks(title="Spandan Smartwatch AI") as demo:
    gr.Markdown("# Spandan Smartwatch AI\nTwo-model inference for physical state and focus monitoring.")
    with gr.Tab("Physical state"):
        gr.Markdown("Enter one cleaned telemetry row. The endpoint returns STRESS, PHYSICAL ACTIVITY, or NORMAL.")
        physical_button = gr.Button("Run physical-state model", variant="primary")
        physical_output = gr.JSON(label="Physical-state output")
        physical_button.click(
            predict_physical_state,
            inputs=physical_inputs,
            outputs=physical_output,
            api_name="predict_physical_state",
        )
    with gr.Tab("Focus and distraction"):
        gr.Markdown("Paste JSON with exactly 60 ordered samples from one officer.")
        distraction_input = gr.Textbox(
            label="60-sample JSON",
            lines=12,
            placeholder='{"samples": [{"heart_rate": 80, "accel_x": 0, ...}]}'
        )
        distraction_button = gr.Button("Run distraction model", variant="primary")
        distraction_output = gr.JSON(label="Distraction output")
        distraction_button.click(
            predict_distraction,
            inputs=distraction_input,
            outputs=distraction_output,
            api_name="predict_distraction",
        )

if __name__ == "__main__":
    demo.launch()
