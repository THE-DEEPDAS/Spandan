'use client';

import React, { useEffect, useState } from 'react';
import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { ArrowLeft, Sparkles } from 'lucide-react';
import {
  AnalyticsOverview,
  fetchOfficerDetail,
  OfficerDetail as OfficerDetailData,
  OfficerSummary,
  TimelinePoint,
} from '../../lib/police-health/analytics-api';
import { AIRecommendation, getOfficerAssessment } from '../../lib/police-health/ai-service';
import {
  formatDate,
  formatDateTime,
  formatDay,
  formatHour,
  formatInt,
  formatPercent,
  formatShortDate,
  formatTime,
  formatValue,
  shareOf,
  totalOf,
} from './format';
import {
  Card,
  ChartCard,
  COUNT_MODE_OPTIONS,
  CountBars,
  CountMode,
  ErrorPanel,
  Legend,
  LoadingPanel,
  Segmented,
  STATE_META,
  StateBreakdown,
  StateColumnChart,
  StateMixBar,
  StatTile,
  StatusBadge,
  StressDriversCard,
  Swatch,
  TooltipCard,
  stateLegendItems,
  tooltipDatum,
  xAxisProps,
  yAxisProps,
} from './ui';

type Thresholds = AnalyticsOverview['thresholds'];

export default function OfficerDetailView({
  badgeId,
  officers,
  thresholds,
  onBack,
  onSelectOfficer,
}: {
  badgeId: string;
  officers: OfficerSummary[];
  thresholds: Thresholds;
  onBack: () => void;
  onSelectOfficer: (badgeId: string) => void;
}) {
  const [result, setResult] = useState<{ badgeId: string; detail?: OfficerDetailData; error?: string } | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchOfficerDetail(badgeId).then(
      detail => !cancelled && setResult({ badgeId, detail }),
      (error: Error) => !cancelled && setResult({ badgeId, error: error.message })
    );
    return () => {
      cancelled = true;
    };
  }, [badgeId]);

  const loading = result?.badgeId !== badgeId;
  const sortedOfficers = [...officers].sort((a, b) => a.name.localeCompare(b.name));

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <button
          type="button"
          onClick={onBack}
          className="inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-sm text-ink-2 hover:bg-sunken hover:text-ink"
        >
          <ArrowLeft size={16} aria-hidden />
          All officers
        </button>
        <label className="flex items-center gap-2 text-xs text-ink-2">
          Officer
          <select
            value={badgeId}
            onChange={event => onSelectOfficer(event.target.value)}
            className="max-w-72 rounded-md border border-line bg-surface px-2 py-1.5 text-sm text-ink"
          >
            {sortedOfficers.map(officer => (
              <option key={officer.badgeId} value={officer.badgeId}>
                {officer.name} ({officer.badgeId})
              </option>
            ))}
          </select>
        </label>
      </div>

      {!loading && result?.error && <ErrorPanel title="Officer data unavailable" message={result.error} />}
      {loading && !result?.detail && <LoadingPanel label="Loading officer profile…" />}
      {result?.detail && (
        // While the next officer loads, hold the previous profile at reduced opacity.
        <div aria-busy={loading} className={`transition-opacity ${loading ? 'opacity-50' : ''}`}>
          <OfficerProfile detail={result.detail} thresholds={thresholds} />
        </div>
      )}
    </div>
  );
}

function OfficerProfile({ detail, thresholds }: { detail: OfficerDetailData; thresholds: Thresholds }) {
  const { officer, stats, timeline } = detail;
  const [dailyMode, setDailyMode] = useState<CountMode>('count');
  const [hourlyMode, setHourlyMode] = useState<CountMode>('count');
  const bucketLabel = formatBucket(timeline.bucketMinutes);
  const movementTotal = detail.movement.reduce((sum, bucket) => sum + bucket.count, 0);

  return (
    <div className="space-y-6">
      <section className="rounded-xl border border-line bg-surface p-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <p className="text-xs font-medium uppercase tracking-wide text-ink-2">{officer.rank}</p>
            <h2 className="mt-1 text-2xl font-semibold tracking-tight text-ink">{officer.name}</h2>
            <p className="mt-1 text-sm text-ink-2">
              Badge {officer.badgeId} · {formatDate(officer.firstSeen)} – {formatDate(officer.lastSeen)} ·{' '}
              {officer.activeDays} active {officer.activeDays === 1 ? 'day' : 'days'} · {stats.sessions} recording{' '}
              {stats.sessions === 1 ? 'session' : 'sessions'}
            </p>
          </div>
          {officer.lowSample && (
            <StatusBadge status="warning" label={`Low sample: fewer than ${thresholds.lowSampleReadings} readings`} />
          )}
        </div>
        <div className="mt-5">
          <StateMixBar counts={officer.states} size="lg" showLabels />
        </div>
        <div className="mt-4">
          <StateBreakdown counts={officer.states} />
        </div>
      </section>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <StatTile
          label="Readings"
          value={formatInt(officer.readings)}
          detail={`Every ${formatValue(stats.medianIntervalSec, ' s')} (median)`}
        />
        <StatTile
          label="Median heart rate"
          value={formatValue(officer.medianHeartRate)}
          unit="bpm"
          detail={`5th–95th pct: ${formatValue(stats.heartRateP5)}–${formatValue(stats.heartRateP95)} bpm`}
        />
        <StatTile
          label="Heart rate measured"
          value={formatPercent(officer.hrMeasuredShare, 0)}
          detail="Remaining readings were filled"
        />
        <StatTile
          label="Median SpO2"
          value={formatValue(officer.medianSpo2)}
          unit="%"
          detail={`5th–95th pct: ${formatValue(stats.spo2P5)}–${formatValue(stats.spo2P95)}%`}
        />
        <StatTile
          label={`SpO2 below ${thresholds.lowSpo2}%`}
          value={formatPercent(officer.lowSpo2Share, 0)}
          detail={`${formatPercent(officer.severeSpo2Share, 0)} below ${thresholds.severeSpo2}%`}
        />
        <StatTile
          label="Median GPS speed"
          value={formatValue(stats.medianSpeedKmh, '', 1)}
          unit="km/h"
          detail={`95th pct: ${formatValue(stats.p95SpeedKmh, ' km/h', 1)}`}
        />
      </div>

      <ChartCard
        title="Heart rate over time"
        subtitle="IST. Breaks in the line are periods without readings."
        height={220}
        legend={timelineLegend(bucketLabel, `${thresholds.stressHeartRate} bpm`)}
        table={timelineTable(timeline.points, 'heartRate', 'Heart rate (bpm)')}
      >
        <TimelineChart points={timeline.points} dataKey="heartRate" threshold={thresholds.stressHeartRate} />
      </ChartCard>

      <ChartCard
        title="SpO2 over time"
        subtitle="IST. Hover either chart to read both."
        height={220}
        legend={timelineLegend(bucketLabel, `${thresholds.stressSpo2}%`)}
        table={timelineTable(timeline.points, 'spo2', 'SpO2 (%)')}
      >
        <TimelineChart points={timeline.points} dataKey="spo2" threshold={thresholds.stressSpo2} ceiling={100} />
      </ChartCard>

      <div className="grid gap-6 lg:grid-cols-2">
        <ChartCard
          title="Readings per day"
          subtitle="By physical-state label, IST calendar days"
          legend={<Legend items={stateLegendItems} />}
          controls={<Segmented label="Daily scale" value={dailyMode} options={COUNT_MODE_OPTIONS} onChange={setDailyMode} />}
          table={{
            columns: ['Date', 'Stress', 'Physical activity', 'Normal', 'Total'],
            rows: detail.daily.map(day => [formatDay(day.date), day.stress, day.activity, day.normal, totalOf(day)]),
          }}
        >
          <StateColumnChart
            data={detail.daily}
            formatX={day => formatDay(day.date)}
            formatTitle={day => formatDay(day.date)}
            mode={dailyMode}
          />
        </ChartCard>
        <ChartCard
          title="Hour of day"
          subtitle="When this officer's readings were recorded (IST)"
          legend={<Legend items={stateLegendItems} />}
          controls={<Segmented label="Hourly scale" value={hourlyMode} options={COUNT_MODE_OPTIONS} onChange={setHourlyMode} />}
          table={{
            columns: ['Hour', 'Stress', 'Physical activity', 'Normal', 'Median HR'],
            rows: detail.hourly.map(hour => [
              formatHour(hour.hour),
              hour.stress,
              hour.activity,
              hour.normal,
              formatValue(hour.medianHeartRate, ' bpm'),
            ]),
          }}
        >
          <StateColumnChart
            data={detail.hourly}
            formatX={hour => formatHour(hour.hour)}
            formatTitle={hour => `${formatHour(hour.hour)}–${formatHour((hour.hour + 1) % 24)} IST`}
            mode={hourlyMode}
          />
        </ChartCard>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <Card title="Movement" subtitle="Readings by GPS speed. Readings without a fix or with implausible jumps are excluded.">
          <CountBars
            total={movementTotal}
            items={detail.movement.map(bucket => ({
              label: bucket.label,
              count: bucket.count,
              color: bucket.key === 'unknown' ? 'var(--neutral-mark)' : undefined,
            }))}
          />
        </Card>
        <StressDriversCard drivers={detail.stressDrivers} thresholds={thresholds} />
        <AssessmentCard key={officer.badgeId} badgeId={officer.badgeId} />
      </div>

      <Card title="Most recent readings" subtitle="Last readings in the training split, newest first">
        <RecentReadings detail={detail} />
      </Card>
    </div>
  );
}

function formatBucket(minutes: number) {
  if (minutes % 1440 === 0) return `${minutes / 1440}-day`;
  if (minutes % 60 === 0) return `${minutes / 60}-hour`;
  return `${minutes}-minute`;
}

function timelineTable(points: TimelinePoint[], key: 'heartRate' | 'spo2', label: string) {
  return {
    columns: ['Window start (IST)', label, 'Readings', 'Stress share'],
    rows: points
      .filter(point => point.readings > 0)
      .map(point => [
        formatDateTime(point.t),
        formatValue(point[key], '', 1),
        point.readings,
        formatPercent(shareOf(point, 'stress'), 0),
      ]),
  };
}

function timelineLegend(bucketLabel: string, threshold: string) {
  return (
    <Legend
      items={[
        { label: `Mean per ${bucketLabel} window`, color: 'var(--measure)', shape: 'line' },
        { label: `Stress threshold (${threshold})`, color: 'var(--state-stress)', shape: 'dashed' },
      ]}
    />
  );
}

const MINUTE_MS = 60_000;
const DAY_MS = 1440 * MINUTE_MS;
const IST_OFFSET_MS = 330 * MINUTE_MS;
const TICK_STEPS_MS = [15, 30, 60, 180, 360, 720, 1440, 2880, 10080].map(minutes => minutes * MINUTE_MS);

/** At most ~10 ticks on IST clock boundaries (quarter hours up to weeks), so labels never repeat. */
function timelineTicks(start: number, end: number) {
  const span = end - start;
  const step = TICK_STEPS_MS.find(candidate => span / candidate <= 10) ?? TICK_STEPS_MS[TICK_STEPS_MS.length - 1];
  const ticks: number[] = [];
  for (let tick = Math.ceil((start + IST_OFFSET_MS) / step) * step - IST_OFFSET_MS; tick <= end; tick += step) {
    ticks.push(tick);
  }
  const format = step >= DAY_MS ? formatShortDate : span > DAY_MS ? formatDateTime : formatTime;
  return { ticks, format };
}

function TimelineChart({
  points,
  dataKey,
  threshold,
  ceiling,
}: {
  points: TimelinePoint[];
  dataKey: 'heartRate' | 'spo2';
  threshold: number;
  ceiling?: number;
}) {
  const { ticks, format: formatTick } = timelineTicks(points[0]?.t ?? 0, points[points.length - 1]?.t ?? 0);

  // A reading surrounded by empty windows has no line segment, so draw it as a dot.
  const renderDot = (props: { cx?: number; cy?: number; index?: number }) => {
    const { cx, cy, index = 0 } = props;
    const isolated =
      points[index]?.[dataKey] != null && points[index - 1]?.[dataKey] == null && points[index + 1]?.[dataKey] == null;
    if (!isolated || cx == null || cy == null) return <g key={`dot-${index}`} />;
    return <circle key={`dot-${index}`} cx={cx} cy={cy} r={4} fill="var(--measure)" stroke="var(--surface)" strokeWidth={2} />;
  };

  return (
    <ResponsiveContainer width="100%" height="100%" initialDimension={{ width: 1, height: 1 }}>
      <LineChart data={points} syncId="officer-timeline" margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
        <CartesianGrid vertical={false} stroke="var(--grid)" />
        <XAxis
          dataKey="t"
          type="number"
          scale="time"
          domain={['dataMin', 'dataMax']}
          ticks={ticks}
          tickFormatter={formatTick}
          minTickGap={24}
          {...xAxisProps}
        />
        <YAxis
          {...yAxisProps}
          domain={[
            (min: number) => Math.floor((Math.min(min, threshold) - 2) / 5) * 5,
            (max: number) => {
              const top = Math.ceil((Math.max(max, threshold) + 2) / 5) * 5;
              return ceiling ? Math.min(top, ceiling) : top;
            },
          ]}
          allowDecimals={false}
        />
        <ReferenceLine y={threshold} stroke="var(--state-stress)" strokeDasharray="4 4" />
        <Tooltip
          cursor={{ stroke: 'var(--axis)' }}
          isAnimationActive={false}
          content={props => {
            const point = tooltipDatum<TimelinePoint>(props);
            if (!point) return null;
            if (!point.readings) return <TooltipCard title={formatDateTime(point.t)} rows={[{ label: 'No readings', value: '—' }]} />;
            return (
              <TooltipCard
                title={`${formatDateTime(point.t)} IST`}
                rows={[
                  { label: 'heart rate', value: `${formatValue(point.heartRate, '', 1)} bpm`, color: dataKey === 'heartRate' ? 'var(--measure)' : undefined },
                  { label: 'SpO2', value: `${formatValue(point.spo2, '', 1)}%`, color: dataKey === 'spo2' ? 'var(--measure)' : undefined },
                  { label: 'labelled Stress', value: formatPercent(shareOf(point, 'stress'), 0) },
                ]}
                footer={`${formatInt(point.readings)} readings in window`}
              />
            );
          }}
        />
        <Line
          dataKey={dataKey}
          stroke="var(--measure)"
          strokeWidth={2}
          strokeLinejoin="round"
          strokeLinecap="round"
          connectNulls={false}
          dot={renderDot}
          activeDot={{ r: 4, fill: 'var(--measure)', stroke: 'var(--surface)', strokeWidth: 2 }}
          isAnimationActive={false}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}

function RecentReadings({ detail }: { detail: OfficerDetailData }) {
  return (
    <div className="-mx-5 overflow-x-auto">
      <table className="w-full min-w-xl text-left text-xs tabular-nums">
        <thead className="text-ink-2">
          <tr className="border-b border-line">
            <th scope="col" className="py-2 pl-5 pr-3 font-medium">Time (IST)</th>
            <th scope="col" className="px-3 py-2 text-right font-medium">Heart rate</th>
            <th scope="col" className="px-3 py-2 text-right font-medium">SpO2</th>
            <th scope="col" className="px-3 py-2 text-right font-medium">GPS speed</th>
            <th scope="col" className="py-2 pl-3 pr-5 font-medium">Label</th>
          </tr>
        </thead>
        <tbody>
          {detail.recent.map(reading => (
            <tr key={reading.timestamp} className="border-b border-line text-ink last:border-0">
              <td className="py-2 pl-5 pr-3">{formatDateTime(reading.timestamp)}</td>
              <td className="px-3 py-2 text-right">
                {formatValue(reading.heartRate, ' bpm')}
                {!reading.heartRateMeasured && <span className="ml-1 text-ink-2">(filled)</span>}
              </td>
              <td className="px-3 py-2 text-right">{formatValue(reading.spo2, '%')}</td>
              <td className="px-3 py-2 text-right">{formatValue(reading.speedKmh, ' km/h', 1)}</td>
              <td className="py-2 pl-3 pr-5">
                <span className="inline-flex items-center gap-1.5">
                  <Swatch color={STATE_META[reading.state].color} />
                  {STATE_META[reading.state].label}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const ASSESSMENT_STATUS = {
  normal: { status: 'good', label: 'Normal' },
  warning: { status: 'warning', label: 'Warning' },
  anomaly: { status: 'critical', label: 'Anomaly' },
} as const;

function AssessmentCard({ badgeId }: { badgeId: string }) {
  const [state, setState] = useState<{ loading: boolean; result?: AIRecommendation; error?: string }>({ loading: false });

  const run = async () => {
    setState({ loading: true });
    try {
      setState({ loading: false, result: await getOfficerAssessment(badgeId) });
    } catch (error) {
      setState({ loading: false, error: error instanceof Error ? error.message : 'AI assessment failed' });
    }
  };

  const status = state.result && ASSESSMENT_STATUS[state.result.status];

  return (
    <Card title="AI assessment" subtitle="Generated from this officer's aggregated figures. Not a medical diagnosis.">
      {state.result && status && (
        <div className="space-y-3">
          <StatusBadge status={status.status} label={status.label} />
          <p className="text-sm leading-relaxed text-ink">{state.result.message}</p>
          <p className="rounded-lg bg-sunken px-3 py-2.5 text-xs leading-relaxed text-ink-2">
            <span className="font-medium text-ink">Recommendation: </span>
            {state.result.recommendation}
          </p>
        </div>
      )}
      {state.error && (
        <div className="space-y-1">
          <StatusBadge status="critical" label="Assessment unavailable" />
          <p className="text-xs leading-relaxed text-ink-2">{state.error}</p>
        </div>
      )}
      <button
        type="button"
        onClick={run}
        disabled={state.loading}
        className="mt-4 inline-flex items-center gap-1.5 rounded-md bg-ink px-3 py-1.5 text-xs font-medium text-surface hover:opacity-90 disabled:opacity-50"
      >
        <Sparkles size={14} aria-hidden />
        {state.loading ? 'Analysing…' : state.result ? 'Regenerate' : 'Generate assessment'}
      </button>
    </Card>
  );
}
