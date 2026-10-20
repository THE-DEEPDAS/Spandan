"""
Aggregate analytics over the labelled training split (combined_train.csv).

The dashboard reads these aggregates instead of replaying individual rows, so
every figure it shows can be traced back to the training data. All times are
reported in IST, where the officers are deployed.
"""

from __future__ import annotations

import math
from datetime import timedelta, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

IST = timezone(timedelta(hours=5, minutes=30), name="IST")

# Thresholds used by 18_09_26/code/prepare_temporal_splits.py to derive `target`.
STRESS_HR_BPM = 90.0
STRESS_SPO2_PCT = 91.0

LOW_SPO2_PCT = 90.0
SEVERE_SPO2_PCT = 85.0
MAX_PLAUSIBLE_SPEED_KMH = 150.0
WALKING_SPEED_KMH = 1.0
VEHICLE_SPEED_KMH = 6.0
SESSION_GAP = pd.Timedelta(minutes=5)
LOW_SAMPLE_READINGS = 100

STATES = {0: "stress", 1: "activity", 2: "normal"}
STATE_KEYS = list(STATES.values())

RANK_ORDER = ["Constable", "Head Constable", "ASI", "PSI", "PI", "SUBDISTRICT_OFFICER", "RURALADMIN"]
RANK_LABELS = {"SUBDISTRICT_OFFICER": "Sub-district Officer", "RURALADMIN": "Rural Admin"}

TIMELINE_BUCKET_MINUTES = [1, 2, 5, 10, 15, 30, 60, 120, 180, 360, 720, 1440]
MAX_TIMELINE_POINTS = 500
RECENT_READINGS = 12


def _num(value, digits: int = 1) -> Optional[float]:
    if value is None or pd.isna(value):
        return None
    return round(float(value), digits)


def _share(mask: pd.Series) -> float:
    return round(float(mask.mean()), 4) if len(mask) else 0.0


def _rank_label(rank: str) -> str:
    return RANK_LABELS.get(rank, rank)


def _rank_sort_key(rank: str) -> int:
    return RANK_ORDER.index(rank) if rank in RANK_ORDER else len(RANK_ORDER)


def _load_frame(data_dir: Path) -> pd.DataFrame:
    combined = data_dir / "combined_train.csv"
    if combined.is_file():
        df = pd.read_csv(combined)
    else:
        files = [path for path in sorted(data_dir.glob("*.csv")) if not path.name.startswith("_")]
        if not files:
            raise FileNotFoundError(f"No training CSV files found in {data_dir}")
        df = pd.concat((pd.read_csv(path) for path in files), ignore_index=True)

    df["ts"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce").dt.tz_convert(IST)
    df = df.dropna(subset=["ts"]).sort_values(["badge_id", "ts"]).reset_index(drop=True)

    df["state"] = df["target"].map(STATES)
    df["date"] = df["ts"].dt.strftime("%Y-%m-%d")
    df["hour"] = df["ts"].dt.hour
    # heart_rate is pulse with gaps filled and <=35 bpm disconnects replaced by 80.
    df["hr_measured"] = df["pulse"].notna() & (df["pulse"] > 35)
    df["gps_fix"] = (df["latitude"] != 0) & (df["longitude"] != 0)
    plausible_speed = df["gps_fix"] & (df["approx_speed_kmh"] <= MAX_PLAUSIBLE_SPEED_KMH)
    df["speed"] = df["approx_speed_kmh"].where(plausible_speed)
    return df


def _state_counts(frame: pd.DataFrame) -> dict:
    counts = frame["state"].value_counts()
    return {key: int(counts.get(key, 0)) for key in STATE_KEYS}


def _stress_drivers(frame: pd.DataFrame) -> dict:
    stress = frame[frame["target"] == 0]
    high_hr = stress["heart_rate"] > STRESS_HR_BPM
    low_spo2 = stress["spo2"] < STRESS_SPO2_PCT
    return {
        "total": len(stress),
        "spo2Only": int((low_spo2 & ~high_hr).sum()),
        "heartRateOnly": int((high_hr & ~low_spo2).sum()),
        "both": int((high_hr & low_spo2).sum()),
    }


def _officer_summary(badge_id: str, frame: pd.DataFrame) -> dict:
    first = frame.iloc[0]
    heart_rate = frame["heart_rate"]
    modal_hr = heart_rate.mode()
    return {
        "badgeId": badge_id,
        "name": first["officer_name"],
        "rank": _rank_label(first["rank"]),
        "readings": len(frame),
        "activeDays": int(frame["date"].nunique()),
        "firstSeen": frame["ts"].iloc[0].isoformat(),
        "lastSeen": frame["ts"].iloc[-1].isoformat(),
        "medianHeartRate": _num(heart_rate.median()),
        "medianSpo2": _num(frame["spo2"].median()),
        "lowSpo2Share": _share(frame["spo2"] < LOW_SPO2_PCT),
        "severeSpo2Share": _share(frame["spo2"] < SEVERE_SPO2_PCT),
        "hrMeasuredShare": _share(frame["hr_measured"]),
        "modalHeartRateShare": _share(heart_rate == modal_hr.iloc[0]) if not modal_hr.empty else 0.0,
        "gpsFixShare": _share(frame["gps_fix"]),
        "states": _state_counts(frame),
        "lowSample": len(frame) < LOW_SAMPLE_READINGS,
    }


def _daily(frame: pd.DataFrame) -> list[dict]:
    table = pd.crosstab(frame["date"], frame["state"]).reindex(columns=STATE_KEYS, fill_value=0)
    # Include days without readings so the time axis stays honest.
    all_days = pd.date_range(table.index.min(), table.index.max(), freq="D").strftime("%Y-%m-%d")
    table = table.reindex(all_days, fill_value=0)
    return [{"date": date, **{key: int(row[key]) for key in STATE_KEYS}} for date, row in table.iterrows()]


def _hourly(frame: pd.DataFrame) -> list[dict]:
    table = pd.crosstab(frame["hour"], frame["state"]).reindex(
        index=range(24), columns=STATE_KEYS, fill_value=0
    )
    median_hr = frame.groupby("hour")["heart_rate"].median()
    return [
        {"hour": hour, **{key: int(row[key]) for key in STATE_KEYS}, "medianHeartRate": _num(median_hr.get(hour))}
        for hour, row in table.iterrows()
    ]


def _heart_rate_histogram(series: pd.Series, width: int = 5) -> list[dict]:
    low = int(math.floor((series.min() - 1) / width) * width)
    high = int(math.ceil(series.max() / width) * width)
    edges = list(range(low, high + width, width))
    counts = pd.cut(series, bins=edges, right=True).value_counts(sort=False)
    return [
        {
            "label": f"{start + 1}–{start + width}",
            "start": start,
            "count": int(count),
            "aboveStressThreshold": start >= STRESS_HR_BPM,
        }
        for start, count in zip(edges[:-1], counts)
    ]


def _spo2_histogram(series: pd.Series) -> list[dict]:
    values = series.round().astype(int)
    counts = values.value_counts().reindex(range(values.min(), values.max() + 1), fill_value=0)
    return [
        {"value": int(value), "count": int(count), "belowStressThreshold": value < STRESS_SPO2_PCT}
        for value, count in counts.items()
    ]


def _ranks(df: pd.DataFrame) -> list[dict]:
    rows = []
    for rank, frame in df.groupby("rank"):
        rows.append(
            {
                "rank": _rank_label(rank),
                "sortKey": _rank_sort_key(rank),
                "officers": int(frame["badge_id"].nunique()),
                "readings": len(frame),
                "medianHeartRate": _num(frame["heart_rate"].median()),
                "medianSpo2": _num(frame["spo2"].median()),
                "states": _state_counts(frame),
            }
        )
    rows.sort(key=lambda row: row.pop("sortKey"))
    return rows


def _movement(frame: pd.DataFrame) -> list[dict]:
    speed = frame["speed"]
    buckets = [
        ("stationary", f"Stationary (< {WALKING_SPEED_KMH:g} km/h)", speed < WALKING_SPEED_KMH),
        ("walking", f"On foot ({WALKING_SPEED_KMH:g}–{VEHICLE_SPEED_KMH:g} km/h)",
         speed.between(WALKING_SPEED_KMH, VEHICLE_SPEED_KMH, inclusive="left")),
        ("vehicle", f"Vehicle (≥ {VEHICLE_SPEED_KMH:g} km/h)", speed >= VEHICLE_SPEED_KMH),
        ("unknown", "No valid GPS speed", speed.isna()),
    ]
    return [{"key": key, "label": label, "count": int(mask.sum())} for key, label, mask in buckets]


def _sampling_intervals(df: pd.DataFrame) -> list[dict]:
    delta = df["time_delta"]
    buckets = [
        ("Under 25 s", delta < 25),
        ("25–35 s (nominal 30 s)", delta.between(25, 35)),
        ("35–60 s", (delta > 35) & (delta <= 60)),
        ("1–5 min", (delta > 60) & (delta <= 300)),
        ("Over 5 min (recording gap)", delta > 300),
    ]
    return [{"label": label, "count": int(mask.sum())} for label, mask in buckets]


def _sensor_coverage(df: pd.DataFrame) -> list[dict]:
    accel_placeholder = (df["accel_x"] == 0) & (df["accel_y"] == 0) & df["accel_z"].isin([0, 9.81])
    gyro_live = (df[["gyro_x", "gyro_y", "gyro_z"]] != 0).any(axis=1)
    sensors = [
        ("heartRate", "Heart rate (PPG pulse)", df["hr_measured"],
         "Missing values were forward-filled during preprocessing."),
        ("spo2", "Blood oxygen (SpO2)", df["spo2"].notna(), "Recorded on every reading."),
        ("accelerometer", "Accelerometer", ~accel_placeholder,
         "Excludes all-zero and flat 9.81 m/s² placeholder rows."),
        ("gps", "GPS position", df["gps_fix"], "Excludes (0, 0) no-fix coordinates."),
        ("temperature", "Skin temperature", df["temperature"].notna(),
         "Not streamed by firmware; imputed as 36.5 °C for modelling."),
        ("gyroscope", "Gyroscope", gyro_live, "Not streamed by firmware; imputed as 0 for modelling."),
        ("ppg", "Raw PPG (IR / red)", df["ir"].fillna(0) > 0, "Only present on early test devices."),
        ("magnetometer", "Magnetometer", df["mag_x"].notna(), "Only present on early test devices."),
        ("battery", "Battery voltage", df["bat_v"].notna(), "Only present on early test devices."),
        ("barometer", "Barometer", df["barometer"].notna(), "Never recorded."),
    ]
    return [
        {"key": key, "label": label, "coverage": _share(mask), "note": note}
        for key, label, mask, note in sensors
    ]


def _quality_issues(df: pd.DataFrame, drivers: dict) -> list[dict]:
    rows = len(df)
    modal_hr = df["heart_rate"].mode().iloc[0]
    modal_hr_count = int((df["heart_rate"] == modal_hr).sum())
    hr_filled = int((~df["hr_measured"]).sum())
    severe_spo2 = int((df["spo2"] < SEVERE_SPO2_PCT).sum())
    no_fix = int((~df["gps_fix"]).sum())
    implausible_speed = int((df["gps_fix"] & (df["approx_speed_kmh"] > MAX_PLAUSIBLE_SPEED_KMH)).sum())
    stress_total = max(drivers["total"], 1)
    hr_driven = drivers["heartRateOnly"] + drivers["both"]

    return [
        {
            "key": "stressDrivenBySpo2",
            "severity": "critical",
            "title": "Stress labels are driven by SpO2 alone",
            "count": drivers["spo2Only"],
            "share": round(drivers["spo2Only"] / stress_total, 4),
            "denominator": "of stress-labelled readings",
            "detail": (
                f"Heart rate above {STRESS_HR_BPM:g} bpm contributed to only {hr_driven:,} stress labels. "
                "The Stress class mostly captures stationary readings with low SpO2."
            ),
        },
        {
            "key": "severeSpo2",
            "severity": "critical",
            "title": f"SpO2 below {SEVERE_SPO2_PCT:g}%",
            "count": severe_spo2,
            "share": round(severe_spo2 / rows, 4),
            "denominator": "of readings",
            "detail": (
                "Values this low would be severe hypoxaemia if genuine. At this frequency in on-duty "
                "officers they more likely reflect sensor fit or motion artefact."
            ),
        },
        {
            "key": "modalHeartRate",
            "severity": "warning",
            "title": f"Heart rate reads exactly {modal_hr:g} bpm",
            "count": modal_hr_count,
            "share": round(modal_hr_count / rows, 4),
            "denominator": "of readings",
            "detail": "A single value dominates the signal, which suggests a firmware default or heavy smoothing.",
        },
        {
            "key": "heartRateFilled",
            "severity": "warning",
            "title": "Heart rate missing and filled",
            "count": hr_filled,
            "share": round(hr_filled / rows, 4),
            "denominator": "of readings",
            "detail": "Pulse was absent or a disconnect artefact (≤ 35 bpm); preprocessing filled these values.",
        },
        {
            "key": "gpsNoFix",
            "severity": "info",
            "title": "GPS without a fix (0, 0)",
            "count": no_fix,
            "share": round(no_fix / rows, 4),
            "denominator": "of readings",
            "detail": "Excluded from movement statistics.",
        },
        {
            "key": "implausibleSpeed",
            "severity": "info",
            "title": f"GPS speed above {MAX_PLAUSIBLE_SPEED_KMH:g} km/h",
            "count": implausible_speed,
            "share": round(implausible_speed / rows, 4),
            "denominator": "of readings",
            "detail": "Jumps between distant fixes; excluded from movement statistics.",
        },
    ]


def _timeline(frame: pd.DataFrame) -> dict:
    span_minutes = (frame["ts"].iloc[-1] - frame["ts"].iloc[0]).total_seconds() / 60
    bucket_minutes = next(
        (size for size in TIMELINE_BUCKET_MINUTES if span_minutes / size <= MAX_TIMELINE_POINTS),
        TIMELINE_BUCKET_MINUTES[-1],
    )
    bucket = pd.Timedelta(minutes=bucket_minutes)
    keys = frame["ts"].dt.floor(bucket)
    grouped = frame.groupby(keys)
    table = pd.DataFrame(
        {
            "heartRate": grouped["heart_rate"].mean(),
            "spo2": grouped["spo2"].mean(),
            "readings": grouped.size(),
        }
    ).join(pd.crosstab(keys, frame["state"]).reindex(columns=STATE_KEYS, fill_value=0))
    # Empty buckets stay in the series as nulls so charts show recording gaps.
    table = table.reindex(pd.date_range(table.index.min(), table.index.max(), freq=bucket))

    points = []
    for ts, row in table.iterrows():
        readings = 0 if pd.isna(row["readings"]) else int(row["readings"])
        points.append(
            {
                "t": int(ts.timestamp() * 1000),
                "heartRate": _num(row["heartRate"]),
                "spo2": _num(row["spo2"]),
                "readings": readings,
                **{key: 0 if pd.isna(row[key]) else int(row[key]) for key in STATE_KEYS},
            }
        )
    return {"bucketMinutes": bucket_minutes, "points": points}


def _recent(frame: pd.DataFrame) -> list[dict]:
    return [
        {
            "timestamp": row.ts.isoformat(),
            "heartRate": _num(row.heart_rate),
            "heartRateMeasured": bool(row.hr_measured),
            "spo2": _num(row.spo2),
            "speedKmh": _num(row.speed),
            "state": row.state,
        }
        for row in frame.tail(RECENT_READINGS).iloc[::-1].itertuples()
    ]


class TrainingAnalytics:
    """Loads the training split lazily and caches the fleet-wide aggregates."""

    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self._df: Optional[pd.DataFrame] = None
        self._overview: Optional[dict] = None

    @property
    def df(self) -> pd.DataFrame:
        if self._df is None:
            self._df = _load_frame(self.data_dir)
        return self._df

    def overview(self) -> dict:
        if self._overview is None:
            self._overview = self._build_overview()
        return self._overview

    def _build_overview(self) -> dict:
        df = self.df
        drivers = _stress_drivers(df)
        officers = [_officer_summary(badge_id, frame) for badge_id, frame in df.groupby("badge_id")]
        source = "combined_train.csv" if (self.data_dir / "combined_train.csv").is_file() else "per-officer CSVs"
        return {
            "dataset": {
                "split": "train",
                "source": source,
                "directory": str(self.data_dir),
                "readings": len(df),
                "officers": len(officers),
                "lowSampleOfficers": sum(officer["lowSample"] for officer in officers),
                "start": df["ts"].min().isoformat(),
                "end": df["ts"].max().isoformat(),
                "activeDays": int(df["date"].nunique()),
                "timezone": "IST (UTC+05:30)",
            },
            "thresholds": {
                "stressHeartRate": STRESS_HR_BPM,
                "stressSpo2": STRESS_SPO2_PCT,
                "lowSpo2": LOW_SPO2_PCT,
                "severeSpo2": SEVERE_SPO2_PCT,
                "lowSampleReadings": LOW_SAMPLE_READINGS,
            },
            "kpis": {
                "medianHeartRate": _num(df["heart_rate"].median()),
                "medianSpo2": _num(df["spo2"].median()),
                "lowSpo2Share": _share(df["spo2"] < LOW_SPO2_PCT),
                "hrMeasuredShare": _share(df["hr_measured"]),
            },
            "states": _state_counts(df),
            "stressDrivers": drivers,
            "daily": _daily(df),
            "hourly": _hourly(df),
            "heartRateHistogram": _heart_rate_histogram(df["heart_rate"]),
            "spo2Histogram": _spo2_histogram(df["spo2"]),
            "ranks": _ranks(df),
            "officers": officers,
            "quality": {
                "sensors": _sensor_coverage(df),
                "issues": _quality_issues(df, drivers),
                "samplingIntervals": _sampling_intervals(df),
            },
        }

    def officer_detail(self, badge_id: str) -> Optional[dict]:
        frame = self.df[self.df["badge_id"] == badge_id]
        if frame.empty:
            return None

        intervals = frame["ts"].diff()
        speed = frame["speed"].dropna()
        return {
            "officer": _officer_summary(badge_id, frame),
            "stats": {
                "sessions": int((intervals > SESSION_GAP).sum()) + 1,
                "medianIntervalSec": _num(intervals.dt.total_seconds().median(), 0),
                "heartRateP5": _num(frame["heart_rate"].quantile(0.05)),
                "heartRateP95": _num(frame["heart_rate"].quantile(0.95)),
                "spo2P5": _num(frame["spo2"].quantile(0.05)),
                "spo2P95": _num(frame["spo2"].quantile(0.95)),
                "medianSpeedKmh": _num(speed.median()),
                "p95SpeedKmh": _num(speed.quantile(0.95)),
            },
            "stressDrivers": _stress_drivers(frame),
            "movement": _movement(frame),
            "timeline": _timeline(frame),
            "daily": _daily(frame),
            "hourly": _hourly(frame),
            "recent": _recent(frame),
        }
