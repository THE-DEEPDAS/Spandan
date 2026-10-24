"""Summarize per-officer heart-rate readings across data/train, val, and test."""

import argparse
import csv
import math
import statistics
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class OfficerSummary:
    heart_rates: list[float] = field(default_factory=list)
    rows: int = 0
    below_range: int = 0
    in_range: int = 0
    above_range: int = 0
    invalid_heart_rate: int = 0
    pulse_missing: int = 0
    pulse_nonpositive: int = 0
    pulse_invalid: int = 0
    pulse_column_rows: int = 0
    pulse_fallbacks: int = 0
    source_files: set[str] = field(default_factory=set)


def parse_number(value: str | None) -> float | None:
    if value is None or not value.strip():
        return None
    try:
        number = float(value)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def percentile(values: list[float], percentage: float) -> float:
    """Return a linearly interpolated percentile from an already sorted list."""
    position = (len(values) - 1) * percentage / 100
    lower_index = math.floor(position)
    upper_index = math.ceil(position)
    if lower_index == upper_index:
        return values[lower_index]
    fraction = position - lower_index
    return values[lower_index] * (1 - fraction) + values[upper_index] * fraction


def analyze(data_dir: Path, lower: float, upper: float) -> dict[tuple[str, str], OfficerSummary]:
    files = [
        path
        for split in ("train", "val", "test")
        for path in sorted((data_dir / split).glob("*.csv"))
        if not path.name.lower().startswith("combined_")
    ]
    if not files:
        raise FileNotFoundError(
            f"No per-officer CSV files found in {data_dir}\\train, val, or test."
        )

    officers: dict[tuple[str, str], OfficerSummary] = {}
    for path in files:
        with path.open("r", newline="", encoding="utf-8-sig") as csv_file:
            reader = csv.DictReader(csv_file)
            if not reader.fieldnames:
                raise ValueError(f"{path} has no CSV header.")
            columns = {column.strip().lower(): column for column in reader.fieldnames}
            badge_column = columns.get("badge_id")
            name_column = columns.get("officer_name")
            heart_rate_column = columns.get("heart_rate")
            pulse_column = columns.get("pulse")
            if not badge_column or not name_column:
                raise ValueError(f"{path} must contain badge_id and officer_name columns.")
            if not heart_rate_column and not pulse_column:
                raise ValueError(f"{path} must contain a heart_rate or pulse column.")

            for row in reader:
                badge_id = (row.get(badge_column) or "").strip()
                officer_name = (row.get(name_column) or "").strip()
                if not badge_id or not officer_name:
                    continue

                summary = officers.setdefault((badge_id, officer_name), OfficerSummary())
                summary.rows += 1
                summary.source_files.add(path.name)

                pulse_value = row.get(pulse_column) if pulse_column else None
                pulse = parse_number(pulse_value)
                if pulse_column:
                    summary.pulse_column_rows += 1
                    if pulse_value is None or not pulse_value.strip():
                        summary.pulse_missing += 1
                    elif pulse is None:
                        summary.pulse_invalid += 1
                    elif pulse <= 0:
                        summary.pulse_nonpositive += 1

                heart_rate = parse_number(row.get(heart_rate_column)) if heart_rate_column else None
                if heart_rate is None and pulse is not None:
                    heart_rate = pulse
                    summary.pulse_fallbacks += 1
                if heart_rate is None:
                    summary.invalid_heart_rate += 1
                    continue

                summary.heart_rates.append(heart_rate)
                if heart_rate < lower:
                    summary.below_range += 1
                elif heart_rate > upper:
                    summary.above_range += 1
                else:
                    summary.in_range += 1

    return officers


def build_report_rows(
    officers: dict[tuple[str, str], OfficerSummary], lower: float, upper: float
) -> list[dict[str, object]]:
    report_rows = []
    for (badge_id, officer_name), summary in sorted(officers.items()):
        rates = sorted(summary.heart_rates)
        valid_count = len(rates)
        report_rows.append(
            {
                "badge_id": badge_id,
                "officer_name": officer_name,
                "source_files": len(summary.source_files),
                "total_rows": summary.rows,
                "valid_heart_rate_readings": valid_count,
                f"below_{lower:g}_bpm": summary.below_range,
                f"in_{lower:g}_{upper:g}_bpm": summary.in_range,
                f"above_{upper:g}_bpm": summary.above_range,
                "observed_min_bpm": min(rates) if rates else "",
                "observed_max_bpm": max(rates) if rates else "",
                "p05_bpm": percentile(rates, 5) if rates else "",
                "p95_bpm": percentile(rates, 95) if rates else "",
                "mean_bpm": statistics.mean(rates) if rates else "",
                "median_bpm": statistics.median(rates) if rates else "",
                "invalid_or_missing_heart_rate": summary.invalid_heart_rate,
                "raw_pulse_missing": summary.pulse_missing,
                "raw_pulse_nonpositive": summary.pulse_nonpositive,
                "raw_pulse_invalid": summary.pulse_invalid,
                "heart_rate_fallbacks_to_pulse": summary.pulse_fallbacks,
            }
        )
    return report_rows


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Count per-officer heart-rate readings below, within, and above a reference range."
    )
    parser.add_argument("--data-dir", type=Path, default=Path(__file__).parent / "data")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).parent / "data" / "heart_rate_sensor_analysis.csv",
    )
    parser.add_argument(
        "--min-hr",
        type=float,
        default=60,
        help="Lower reference bound in bpm (inclusive for in-range; default: 60).",
    )
    parser.add_argument(
        "--max-hr",
        type=float,
        default=100,
        help="Upper reference bound in bpm (inclusive for in-range; default: 100).",
    )
    args = parser.parse_args()
    if args.min_hr < 0 or args.max_hr <= args.min_hr:
        parser.error("--min-hr must be nonnegative and --max-hr must be greater.")

    try:
        officers = analyze(args.data_dir, args.min_hr, args.max_hr)
    except (FileNotFoundError, ValueError) as error:
        parser.error(str(error))

    report_rows = build_report_rows(officers, args.min_hr, args.max_hr)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=report_rows[0].keys())
        writer.writeheader()
        writer.writerows(report_rows)

    below_label = f"<{args.min_hr:g}"
    range_label = f"{args.min_hr:g}-{args.max_hr:g}"
    above_label = f">{args.max_hr:g}"
    print(
        f"{'Badge':<12} {'Officer':<32} {'Rows':>7} "
        f"{below_label:>8} {range_label:>12} {above_label:>8} "
        f"{'Observed bpm':>16} {'P05-P95 bpm':>16}"
    )
    for row in report_rows:
        observed = (
            f"{row['observed_min_bpm']:g}-{row['observed_max_bpm']:g}"
            if row["valid_heart_rate_readings"]
            else "n/a"
        )
        p05_p95 = (
            f"{row['p05_bpm']:.1f}-{row['p95_bpm']:.1f}"
            if row["valid_heart_rate_readings"]
            else "n/a"
        )
        print(
            f"{row['badge_id']:<12} {row['officer_name'][:32]:<32} "
            f"{row['valid_heart_rate_readings']:>7} "
            f"{row[f'below_{args.min_hr:g}_bpm']:>8} "
            f"{row[f'in_{args.min_hr:g}_{args.max_hr:g}_bpm']:>12} "
            f"{row[f'above_{args.max_hr:g}_bpm']:>8} "
            f"{observed:>16} {p05_p95:>16}"
        )

    print(f"\nReference range: {args.min_hr:g}-{args.max_hr:g} bpm (inclusive).")
    print(
        "This is a general adult resting-heart-rate reference; readings above it "
        "during active duty are not by themselves abnormal or diagnostic."
    )
    print(f"Detailed counts and raw pulse quality indicators saved to: {args.output}")


if __name__ == "__main__":
    main()
