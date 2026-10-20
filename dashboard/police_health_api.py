"""
Standalone API service for Police Health integrations.

Run:
    pip install fastapi uvicorn requests python-dotenv
    uvicorn police_health_api:app --reload --port 8000

This service provides API endpoints that mirror the dashboard logic without UI dependencies.
"""

from __future__ import annotations

import csv
import glob
import math
import os
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Literal, Optional

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

load_dotenv()


# ============================================================================
# Real-Time CSV Data Loader
# ============================================================================

class CSVDataLoader:
    """Loads and manages real-time CSV data from police personnel files."""
    
    def __init__(self, csv_dir: str = "./police-personnel-data-realtime"):
        self.csv_dir = csv_dir
        self.all_rows: List[dict] = []
        self.current_index = 0
        self.last_loaded = None
        self._load_csv_data()
    
    def _load_csv_data(self):
        """Load all CSV files from the directory."""
        csv_files = glob.glob(os.path.join(self.csv_dir, "*.csv"))
        
        if not csv_files:
            print(f"Warning: No CSV files found in {self.csv_dir}")
            return
        
        for csv_file in csv_files:
            try:
                with open(csv_file, 'r', encoding='utf-8') as f:
                    # Skip header section until we find the actual data header
                    # The data header line starts with "App_Date"
                    line = f.readline()
                    while line and not line.startswith("App_Date"):
                        line = f.readline()
                    
                    if not line:
                        print(f"Warning: Could not find data header in {os.path.basename(csv_file)}")
                        continue
                    
                    # Now read the CSV data starting from the actual header
                    # Reset to read the header and data
                    f.seek(0)
                    content = f.read()
                    # Find the position of "App_Date"
                    start_pos = content.find("App_Date")
                    if start_pos == -1:
                        print(f"Warning: No data found in {os.path.basename(csv_file)}")
                        continue
                    
                    # Get the data portion starting from "App_Date"
                    data_content = content[start_pos:]
                    data_lines = data_content.split('\n')
                    
                    # Parse with csv.DictReader
                    reader = csv.DictReader(data_lines)
                    rows = list(reader)
                    self.all_rows.extend(rows)
                    print(f"Loaded {len(rows)} rows from {os.path.basename(csv_file)}")
            except Exception as e:
                print(f"Error loading {csv_file}: {e}")
        
        print(f"Total rows loaded: {len(self.all_rows)}")
    
    def get_next_row(self) -> Optional[dict]:
        """Get the next row cyclically from the CSV data."""
        if not self.all_rows:
            return None
        
        row = self.all_rows[self.current_index]
        self.current_index = (self.current_index + 1) % len(self.all_rows)
        return row
    
    def has_data(self) -> bool:
        """Check if CSV data is available."""
        return len(self.all_rows) > 0


# Initialize the CSV data loader
csv_loader = CSVDataLoader(csv_dir="../police-personnel-data-realtime")


class Vector3(BaseModel):
    x: float
    y: float
    z: float


class RawData(BaseModel):
    heartRate: float = Field(ge=60, le=180)
    spo2: float = Field(ge=85, le=100)
    temp: float = Field(ge=36, le=40)
    accel: Vector3
    gyro: Vector3


class DerivedMetrics(BaseModel):
    physicalLoad: float
    rotationalStress: float
    metabolicStrain: float
    stabilityScore: float = Field(ge=0, le=100)


class TelemetryPoint(BaseModel):
    timestamp: datetime
    raw: RawData
    derived: DerivedMetrics


class AIRecommendation(BaseModel):
    status: Literal["normal", "warning", "anomaly"]
    message: str
    recommendation: str


class AIRecommendationRequest(BaseModel):
    history: List[TelemetryPoint] = Field(min_length=5)


class TelemetryHistoryResponse(BaseModel):
    items: List[TelemetryPoint]


class SystemStatus(BaseModel):
    watchSync: Literal["active", "loading", "offline"]
    aiAnalysis: Literal["active", "loading", "offline"]
    updatedAt: datetime


def _calculate_derived_metrics(raw: RawData) -> DerivedMetrics:
    accel_mag = math.sqrt(raw.accel.x**2 + raw.accel.y**2 + raw.accel.z**2)
    gyro_mag = math.sqrt(raw.gyro.x**2 + raw.gyro.y**2 + raw.gyro.z**2)

    hr_component = (raw.heartRate - 70) / 100
    temp_component = (raw.temp - 37) / 2
    metabolic_strain = max(0, (hr_component * 0.7 + temp_component * 0.3) * 10)

    stability = max(0, 100 - (accel_mag * 5 + gyro_mag * 2))

    return DerivedMetrics(
        physicalLoad=round(accel_mag, 2),
        rotationalStress=round(gyro_mag, 2),
        metabolicStrain=round(metabolic_strain, 2),
        stabilityScore=round(stability, 2),
    )


def _drift(value: float, value_range: float) -> float:
    return value + (random.random() - 0.5) * value_range


def _generate_raw_data_from_csv() -> RawData:
    """Generate raw data from CSV source or fallback to random."""
    if not csv_loader.has_data():
        # Fallback to random generation if no CSV data
        return _generate_random_raw_data()
    
    row = csv_loader.get_next_row()
    if not row:
        return _generate_random_raw_data()
    
    try:
        # Extract values from CSV with proper type conversion and fallback
        heart_rate = float(row.get('HeartRate', 75))
        spo2 = float(row.get('SpO2', 98.5))
        temp = float(row.get('Temperature', 36.8))
        acc_x = float(row.get('Acc_X', 0))
        acc_y = float(row.get('Acc_Y', 0))
        acc_z = float(row.get('Acc_Z', 0))
        gyro_x = float(row.get('Gyro_X', 0))
        gyro_y = float(row.get('Gyro_Y', 0))
        gyro_z = float(row.get('Gyro_Z', 0))
        
        # Ensure values are within valid ranges
        heart_rate = max(60, min(180, heart_rate))
        spo2 = max(85, min(100, spo2))
        temp = max(36, min(40, temp))
        
        return RawData(
            heartRate=round(heart_rate, 1),
            spo2=round(spo2, 1),
            temp=round(temp, 1),
            accel=Vector3(
                x=round(acc_x, 3),
                y=round(acc_y, 3),
                z=round(acc_z, 3),
            ),
            gyro=Vector3(
                x=round(gyro_x, 3),
                y=round(gyro_y, 3),
                z=round(gyro_z, 3),
            ),
        )
    except (ValueError, TypeError, KeyError) as e:
        print(f"Error parsing CSV row: {e}, falling back to random data")
        return _generate_random_raw_data()


def _generate_random_raw_data(prev: Optional[RawData] = None) -> RawData:
    is_anomaly = random.random() < 0.05
    anomaly_type = random.randint(0, 2)

    hr = _drift(prev.heartRate if prev else 75, 5)
    spo2 = _drift(prev.spo2 if prev else 98.5, 0.5)
    temp = _drift(prev.temp if prev else 36.8, 0.2)

    if is_anomaly:
        if anomaly_type == 0:
            hr += 40
        elif anomaly_type == 1:
            spo2 -= 4
        else:
            hr += 20
            temp += 1.5

    return RawData(
        heartRate=max(60, min(180, hr)),
        spo2=max(85, min(100, spo2)),
        temp=max(36, min(40, temp)),
        accel=Vector3(
            x=(random.random() - 0.5) * 2,
            y=(random.random() - 0.5) * 2,
            z=9.8 + (random.random() - 0.5) * 1,
        ),
        gyro=Vector3(
            x=(random.random() - 0.5) * 0.5,
            y=(random.random() - 0.5) * 0.5,
            z=(random.random() - 0.5) * 0.5,
        ),
    )


def _build_history(limit: int = 30) -> List[TelemetryPoint]:
    points: List[TelemetryPoint] = []
    for _ in range(limit):
        # Use CSV data if available, otherwise fall back to random
        raw = _generate_raw_data_from_csv() if csv_loader.has_data() else _generate_random_raw_data()
        derived = _calculate_derived_metrics(raw)
        points.append(
            TelemetryPoint(
                timestamp=datetime.now(timezone.utc),
                raw=raw,
                derived=derived,
            )
        )
    return points


def _default_ai_recommendation() -> AIRecommendation:
    return AIRecommendation(
        status="normal",
        message="Self-monitoring active. AI provider unavailable.",
        recommendation="Verify GROQ_API_KEY and network connectivity.",
    )


def _get_ai_insights_from_groq(history: List[TelemetryPoint], api_key: str) -> AIRecommendation:
    context_data = [
        {
            "hr": round(point.raw.heartRate, 1),
            "spo2": round(point.raw.spo2, 1),
            "load": point.derived.physicalLoad,
            "stability": point.derived.stabilityScore,
        }
        for point in history[-5:]
    ]

    prompt = (
        "Analyze this live health data for a police officer wearing an AI-enhanced watch:\n"
        f"{context_data}\n\n"
        "Rules:\n"
        "1. Provide genuine, non-exaggerated recommendations.\n"
        "2. Focus on HR vs load, SpO2 anomalies, and stability issues.\n"
        "3. If normal, clearly state it with trend rationale.\n"
        "4. Return ONLY JSON with fields: status, message, recommendation."
    )

    payload = {
        "model": "llama-3.1-8b-instant",
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a specialized medical AI analyzing police personnel health "
                    "metrics. Return ONLY valid JSON."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.1,
    }

    response = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=25,
    )
    response.raise_for_status()

    result = response.json()
    if "error" in result:
        raise RuntimeError(result["error"].get("message", "Unknown Groq API error"))

    content = result["choices"][0]["message"]["content"]
    recommendation = AIRecommendation.model_validate_json(content)
    return recommendation


app = FastAPI(
    title="Police Health API",
    description="Integration-first API for telemetry and AI recommendations.",
    version="1.0.0",
)


@app.get("/api/telemetry/current", response_model=TelemetryPoint, tags=["Telemetry"])
def get_telemetry_current() -> TelemetryPoint:
    raw = _generate_raw_data_from_csv() if csv_loader.has_data() else _generate_random_raw_data()
    derived = _calculate_derived_metrics(raw)
    return TelemetryPoint(timestamp=datetime.now(timezone.utc), raw=raw, derived=derived)


@app.get("/api/telemetry/history", response_model=TelemetryHistoryResponse, tags=["Telemetry"])
def get_telemetry_history(
    limit: int = Query(30, ge=1, le=500, description="Number of latest points to return."),
) -> TelemetryHistoryResponse:
    return TelemetryHistoryResponse(items=_build_history(limit=limit))


@app.post("/api/ai/recommendation", response_model=AIRecommendation, tags=["AI Insights"])
def post_ai_recommendation(payload: AIRecommendationRequest) -> AIRecommendation:
    api_key = os.getenv("GROQ_API_KEY") or os.getenv("NEXT_PUBLIC_GROQ_API_KEY")
    if not api_key:
        return _default_ai_recommendation()

    try:
        return _get_ai_insights_from_groq(payload.history, api_key)
    except requests.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Upstream AI provider error: {exc}") from exc
    except Exception:
        return _default_ai_recommendation()


@app.get("/api/system/status", response_model=SystemStatus, tags=["System"])
def get_system_status() -> SystemStatus:
    ai_key_present = bool(os.getenv("GROQ_API_KEY") or os.getenv("NEXT_PUBLIC_GROQ_API_KEY"))
    return SystemStatus(
        watchSync="active" if csv_loader.has_data() else "offline",
        aiAnalysis="active" if ai_key_present else "offline",
        updatedAt=datetime.now(timezone.utc),
    )


@app.get("/api/system/csv-status", tags=["System"])
def get_csv_status() -> dict:
    """Check the status of real-time CSV data."""
    return {
        "hasData": csv_loader.has_data(),
        "totalRows": len(csv_loader.all_rows),
        "currentIndex": csv_loader.current_index,
        "dataSource": "real-time CSV" if csv_loader.has_data() else "random fallback"
    }


@app.get("/health", tags=["System"])
def health() -> dict[str, str]:
    return {"status": "ok"}
