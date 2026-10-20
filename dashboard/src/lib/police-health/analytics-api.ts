/**
 * Typed client for the training-split analytics served by police_health_api.py.
 */

export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';

export type StateKey = 'stress' | 'activity' | 'normal';
export type StateCounts = Record<StateKey, number>;

export interface OfficerSummary {
  badgeId: string;
  name: string;
  rank: string;
  readings: number;
  activeDays: number;
  firstSeen: string;
  lastSeen: string;
  medianHeartRate: number | null;
  medianSpo2: number | null;
  lowSpo2Share: number;
  severeSpo2Share: number;
  hrMeasuredShare: number;
  modalHeartRateShare: number;
  gpsFixShare: number;
  states: StateCounts;
  lowSample: boolean;
}

export interface StressDrivers {
  total: number;
  spo2Only: number;
  heartRateOnly: number;
  both: number;
}

export interface DailyStates extends StateCounts {
  date: string;
}

export interface HourlyStates extends StateCounts {
  hour: number;
  medianHeartRate: number | null;
}

export interface HeartRateBin {
  label: string;
  start: number;
  count: number;
  aboveStressThreshold: boolean;
}

export interface Spo2Bin {
  value: number;
  count: number;
  belowStressThreshold: boolean;
}

export interface RankSummary {
  rank: string;
  officers: number;
  readings: number;
  medianHeartRate: number | null;
  medianSpo2: number | null;
  states: StateCounts;
}

export interface SensorCoverage {
  key: string;
  label: string;
  coverage: number;
  note: string;
}

export interface QualityIssue {
  key: string;
  severity: 'critical' | 'warning' | 'info';
  title: string;
  count: number;
  share: number;
  denominator: string;
  detail: string;
}

export interface LabelledCount {
  label: string;
  count: number;
}

export interface AnalyticsOverview {
  dataset: {
    split: string;
    source: string;
    directory: string;
    readings: number;
    officers: number;
    lowSampleOfficers: number;
    start: string;
    end: string;
    activeDays: number;
    timezone: string;
  };
  thresholds: {
    stressHeartRate: number;
    stressSpo2: number;
    lowSpo2: number;
    severeSpo2: number;
    lowSampleReadings: number;
  };
  kpis: {
    medianHeartRate: number | null;
    medianSpo2: number | null;
    lowSpo2Share: number;
    hrMeasuredShare: number;
  };
  states: StateCounts;
  stressDrivers: StressDrivers;
  daily: DailyStates[];
  hourly: HourlyStates[];
  heartRateHistogram: HeartRateBin[];
  spo2Histogram: Spo2Bin[];
  ranks: RankSummary[];
  officers: OfficerSummary[];
  quality: {
    sensors: SensorCoverage[];
    issues: QualityIssue[];
    samplingIntervals: LabelledCount[];
  };
}

export interface TimelinePoint extends StateCounts {
  t: number;
  heartRate: number | null;
  spo2: number | null;
  readings: number;
}

export interface RecentReading {
  timestamp: string;
  heartRate: number | null;
  heartRateMeasured: boolean;
  spo2: number | null;
  speedKmh: number | null;
  state: StateKey;
}

export interface OfficerDetail {
  officer: OfficerSummary;
  stats: {
    sessions: number;
    medianIntervalSec: number | null;
    heartRateP5: number | null;
    heartRateP95: number | null;
    spo2P5: number | null;
    spo2P95: number | null;
    medianSpeedKmh: number | null;
    p95SpeedKmh: number | null;
  };
  stressDrivers: StressDrivers;
  movement: (LabelledCount & { key: string })[];
  timeline: { bucketMinutes: number; points: TimelinePoint[] };
  daily: DailyStates[];
  hourly: HourlyStates[];
  recent: RecentReading[];
}

export async function getJson<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, init);
  } catch {
    throw new Error(`Cannot reach the analytics API at ${API_BASE_URL}. Is police_health_api.py running?`);
  }
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(body?.detail ?? `Request failed with status ${response.status}`);
  }
  return body as T;
}

export const fetchOverview = () => getJson<AnalyticsOverview>('/api/analytics/overview');

export const fetchOfficerDetail = (badgeId: string) =>
  getJson<OfficerDetail>(`/api/analytics/officers/${encodeURIComponent(badgeId)}`);
