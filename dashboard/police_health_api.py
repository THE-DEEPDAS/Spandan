"""
Standalone API service for Police Health integrations.

Run:
    pip install fastapi uvicorn requests python-dotenv
    uvicorn police_health_api:app --reload --port 8000

This service provides API endpoints that mirror the dashboard logic without UI dependencies.
"""

from __future__ import annotations

import csv
import json
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
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from police_analytics import TrainingAnalytics

load_dotenv()


# ============================================================================
# Real-Time CSV Data Loader
# ============================================================================

class CSVDataLoader:
    """Loads and manages real-time CSV data from police personnel files."""
    
    def __init__(self, csv_dir: str):
        self.csv_dir = csv_dir
        self.all_rows: List[dict] = []
        self.current_index = 0
        self.last_loaded = None
        self._load_csv_data()
    
    def _load_csv_data(self):
        """Load all CSV files from the directory."""
        csv_files = sorted(glob.glob(os.path.join(self.csv_dir, "*.csv")))

        if not csv_files:
            print(f"Warning: No CSV files found in {self.csv_dir}")
            return

        # combined_train.csv contains the complete training set. Prefer it when
        # present so the same rows are not loaded again from the per-officer files.
        combined_file = next(
            (path for path in csv_files if os.path.basename(path).lower() == "combined_train.csv"),
            None,
        )
        if combined_file:
            csv_files = [combined_file]

        for csv_file in csv_files:
            try:
                with open(csv_file, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
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


# Initialize from the requested train dataset, with the existing realtime
# directory retained as a fallback for older local setups.
project_root = Path(__file__).resolve().parents[2]
# TRAIN_DATA_DIR wins; otherwise use data/train beside dashboard/ (Spandan repo
# layout), then the standalone 18_09_26 checkout.
default_train_dirs = [
    Path(__file__).resolve().parents[1] / "data" / "train",
    project_root / "18_09_26" / "18_09_26" / "data" / "train",
]
train_dir = Path(
    os.getenv("TRAIN_DATA_DIR")
    or next((path for path in default_train_dirs if path.is_dir()), default_train_dirs[-1])
)
legacy_dir = project_root / "api dashboard" / "police-personnel-data-realtime"
csv_loader = CSVDataLoader(str(train_dir if train_dir.is_dir() else legacy_dir))
analytics = TrainingAnalytics(train_dir)


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


class OfficerMetadata(BaseModel):
    name: str
    id: str
    rank: Optional[str] = None
    userId: Optional[str] = None


class DerivedMetrics(BaseModel):
    physicalLoad: float
    rotationalStress: float
    metabolicStrain: float
    stabilityScore: float = Field(ge=0, le=100)


class TelemetryPoint(BaseModel):
    timestamp: datetime
    raw: RawData
    derived: DerivedMetrics
    officer: Optional[OfficerMetadata] = None


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
    """Read the next telemetry point from the configured train dataset."""
    if not csv_loader.has_data():
        raise RuntimeError(f"No telemetry CSV data loaded from {csv_loader.csv_dir}")
    
    row = csv_loader.get_next_row()
    if not row:
        raise RuntimeError("Telemetry dataset is empty")
    
    try:
        # Extract values from CSV with proper type conversion and fallback
        heart_rate = float(row.get('heart_rate') or row.get('pulse') or row.get('HeartRate') or 75)
        spo2 = float(row.get('spo2') or row.get('SpO2') or 98.5)
        temp = float(row.get('temperature') or row.get('skin_temperature') or row.get('Temperature') or 36.8)
        acc_x = float(row.get('accel_x') or row.get('Acc_X') or 0)
        acc_y = float(row.get('accel_y') or row.get('Acc_Y') or 0)
        acc_z = float(row.get('accel_z') or row.get('Acc_Z') or 0)
        gyro_x = float(row.get('gyro_x') or row.get('Gyro_X') or 0)
        gyro_y = float(row.get('gyro_y') or row.get('Gyro_Y') or 0)
        gyro_z = float(row.get('gyro_z') or row.get('Gyro_Z') or 0)
        
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
        raise RuntimeError(f"Invalid telemetry row at index {csv_loader.current_index - 1}: {e}") from e


def _get_current_officer() -> Optional[OfficerMetadata]:
    row = csv_loader.all_rows[(csv_loader.current_index - 1) % len(csv_loader.all_rows)] if csv_loader.all_rows else None
    if not row:
        return None
    return OfficerMetadata(
        name=row.get("officer_name") or "Unknown officer",
        id=row.get("badge_id") or "Unknown ID",
        rank=row.get("rank"),
        userId=row.get("user_id"),
    )


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
                officer=_get_current_officer(),
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
        " The status value MUST be exactly one of: normal, warning, anomaly."
    )
    return _request_groq_recommendation(prompt, api_key)


def _get_officer_assessment_from_groq(detail: dict, api_key: str) -> AIRecommendation:
    officer = detail["officer"]
    context_data = {
        "rank": officer["rank"],
        "readings": officer["readings"],
        "activeDays": officer["activeDays"],
        "medianHeartRate": officer["medianHeartRate"],
        "heartRateP5toP95": [detail["stats"]["heartRateP5"], detail["stats"]["heartRateP95"]],
        "heartRateMeasuredShare": officer["hrMeasuredShare"],
        "medianSpo2": officer["medianSpo2"],
        "spo2Below90Share": officer["lowSpo2Share"],
        "spo2Below85Share": officer["severeSpo2Share"],
        "physicalStateCounts": officer["states"],
        "stressLabelDrivers": detail["stressDrivers"],
        "movement": {bucket["key"]: bucket["count"] for bucket in detail["movement"]},
    }

    prompt = (
        "Summarise the on-duty health profile of a police officer from smartwatch telemetry "
        "aggregated over the training period:\n"
        f"{json.dumps(context_data)}\n\n"
        "Rules:\n"
        "1. Be factual and non-alarmist; base every claim on the numbers given.\n"
        "2. Stress labels mark stationary readings with heart rate > 90 bpm or SpO2 < 91%. "
        "Say whether low SpO2 or heart rate drives them, and treat implausibly frequent low SpO2 "
        "as a possible sensor-fit issue rather than a diagnosis.\n"
        "3. message: at most two sentences. recommendation: one practical next step.\n"
        "4. Return ONLY JSON with fields: status, message, recommendation."
        " The status value MUST be exactly one of: normal, warning, anomaly."
    )
    return _request_groq_recommendation(prompt, api_key)


def _request_groq_recommendation(prompt: str, api_key: str) -> AIRecommendation:
    payload = {
        "model": os.getenv("GROQ_MODEL", "openai/gpt-oss-20b"),
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

    request_headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    response = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers=request_headers,
        json=payload,
        timeout=25,
    )
    response.raise_for_status()

    result = response.json()
    if "error" in result:
        raise RuntimeError(result["error"].get("message", "Unknown Groq API error"))

    content = result["choices"][0]["message"]["content"]
    parsed = json.loads(content)
    status = str(parsed.get("status", "")).lower()
    if status not in {"normal", "warning", "anomaly"}:
        if "anomal" in status:
            status = "anomaly"
        elif "concern" in status or "warn" in status:
            status = "warning"
        else:
            status = "normal"
    parsed["status"] = status
    recommendation = AIRecommendation.model_validate(parsed)
    return recommendation


app = FastAPI(
    title="Police Health API",
    description="Integration-first API for telemetry and AI recommendations.",
    version="1.0.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/api/telemetry/current", response_model=TelemetryPoint, tags=["Telemetry"])
def get_telemetry_current() -> TelemetryPoint:
    if not csv_loader.has_data():
        raise HTTPException(status_code=503, detail=f"No train telemetry data loaded from {csv_loader.csv_dir}")
    raw = _generate_raw_data_from_csv()
    derived = _calculate_derived_metrics(raw)
    return TelemetryPoint(
        timestamp=datetime.now(timezone.utc),
        raw=raw,
        derived=derived,
        officer=_get_current_officer(),
    )


@app.get("/api/telemetry/history", response_model=TelemetryHistoryResponse, tags=["Telemetry"])
def get_telemetry_history(
    limit: int = Query(30, ge=1, le=500, description="Number of latest points to return."),
) -> TelemetryHistoryResponse:
    if not csv_loader.has_data():
        raise HTTPException(status_code=503, detail=f"No train telemetry data loaded from {csv_loader.csv_dir}")
    return TelemetryHistoryResponse(items=_build_history(limit=limit))


@app.post("/api/ai/recommendation", response_model=AIRecommendation, tags=["AI Insights"])
def post_ai_recommendation(payload: AIRecommendationRequest) -> AIRecommendation:
    api_key = os.getenv("GROQ_API_KEY") or os.getenv("NEXT_PUBLIC_GROQ_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="GROQ_API_KEY is not configured on the backend")

    try:
        return _get_ai_insights_from_groq(payload.history, api_key)
    except requests.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Upstream AI provider error: {exc}") from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI provider error: {exc}") from exc


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
        "dataSource": csv_loader.csv_dir if csv_loader.has_data() else "random fallback",
        "fileCount": len(glob.glob(os.path.join(csv_loader.csv_dir, "*.csv"))),
    }


def _analytics_overview() -> dict:
    try:
        return analytics.overview()
    except (FileNotFoundError, KeyError, ValueError) as exc:
        raise HTTPException(status_code=503, detail=f"Training data unavailable in {analytics.data_dir}: {exc}") from exc


@app.get("/api/analytics/overview", tags=["Analytics"])
def get_analytics_overview() -> dict:
    """Fleet-wide aggregates, officer summaries and data-quality checks for the training split."""
    return _analytics_overview()


@app.get("/api/analytics/officers/{badge_id}", tags=["Analytics"])
def get_officer_analytics(badge_id: str) -> dict:
    """Timeline, daily/hourly state mix, movement and recent readings for one officer."""
    _analytics_overview()
    detail = analytics.officer_detail(badge_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"No training data for officer {badge_id}")
    return detail


@app.post("/api/analytics/officers/{badge_id}/assessment", response_model=AIRecommendation, tags=["AI Insights"])
def post_officer_assessment(badge_id: str) -> AIRecommendation:
    """AI summary of one officer's aggregated health profile."""
    detail = get_officer_analytics(badge_id)
    api_key = os.getenv("GROQ_API_KEY") or os.getenv("NEXT_PUBLIC_GROQ_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="GROQ_API_KEY is not configured on the backend")

    try:
        return _get_officer_assessment_from_groq(detail, api_key)
    except requests.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Upstream AI provider error: {exc}") from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI provider error: {exc}") from exc


@app.get("/health", tags=["System"])
def health() -> dict[str, str]:
    return {"status": "ok"}
