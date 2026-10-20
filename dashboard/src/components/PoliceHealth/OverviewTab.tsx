'use client';

import React, { useMemo, useState } from 'react';
import type { AnalyticsOverview, RankSummary } from '../../lib/police-health/analytics-api';
import {
  formatDay,
  formatHour,
  formatInt,
  formatPercent,
  formatPeriod,
  formatValue,
  shareOf,
  totalOf,
} from './format';
import {
  Card,
  ChartCard,
  COUNT_MODE_OPTIONS,
  CountMode,
  HistogramChart,
  Legend,
  Segmented,
  StateBreakdown,
  StateColumnChart,
  StateMixBar,
  StatTile,
  StressDriversCard,
  stateLegendItems,
} from './ui';

export default function OverviewTab({
  overview,
  onSelectOfficer,
}: {
  overview: AnalyticsOverview;
  onSelectOfficer: (badgeId: string) => void;
}) {
  const { dataset, kpis, states, thresholds } = overview;
  const [dailyMode, setDailyMode] = useState<CountMode>('count');
  const [hourlyMode, setHourlyMode] = useState<CountMode>('count');

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <StatTile
          label="Officers"
          value={formatInt(dataset.officers)}
          detail={`${dataset.lowSampleOfficers} with fewer than ${thresholds.lowSampleReadings} readings`}
        />
        <StatTile label="Readings" value={formatInt(dataset.readings)} detail={`Across ${dataset.activeDays} active days`} />
        <StatTile label="Monitoring window" value={formatPeriod(dataset.start, dataset.end)} detail={dataset.timezone} />
        <StatTile
          label="Median heart rate"
          value={formatValue(kpis.medianHeartRate)}
          unit="bpm"
          detail={`${formatPercent(kpis.hrMeasuredShare)} measured, the rest filled`}
        />
        <StatTile
          label="Median SpO2"
          value={formatValue(kpis.medianSpo2)}
          unit="%"
          detail={`${formatPercent(kpis.lowSpo2Share)} of readings below ${thresholds.lowSpo2}%`}
        />
        <StatTile
          label="Labelled Stress"
          value={formatPercent(shareOf(states, 'stress'))}
          detail={`${formatInt(states.stress)} readings`}
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <Card
          className="lg:col-span-2"
          title="Physical-state labels"
          subtitle="Silver-standard labels used to train the physical-state classifier (Model 1)"
        >
          <StateMixBar counts={states} size="lg" showLabels />
          <div className="mt-5">
            <StateBreakdown counts={states} showRules />
          </div>
        </Card>
        <StressDriversCard drivers={overview.stressDrivers} thresholds={thresholds} />
      </div>

      <ChartCard
        title="Readings per day"
        subtitle="Daily volume by physical-state label, IST calendar days"
        legend={<Legend items={stateLegendItems} />}
        controls={<Segmented label="Daily scale" value={dailyMode} options={COUNT_MODE_OPTIONS} onChange={setDailyMode} />}
        table={{
          columns: ['Date', 'Stress', 'Physical activity', 'Normal', 'Total'],
          rows: overview.daily.map(day => [formatDay(day.date), day.stress, day.activity, day.normal, totalOf(day)]),
        }}
      >
        <StateColumnChart
          data={overview.daily}
          formatX={day => formatDay(day.date)}
          formatTitle={day => formatDay(day.date)}
          mode={dailyMode}
        />
      </ChartCard>

      <div className="grid gap-6 lg:grid-cols-2">
        <ChartCard
          title="Hour of day"
          subtitle="When readings were recorded, by label (IST)"
          legend={<Legend items={stateLegendItems} />}
          controls={<Segmented label="Hourly scale" value={hourlyMode} options={COUNT_MODE_OPTIONS} onChange={setHourlyMode} />}
          table={{
            columns: ['Hour', 'Stress', 'Physical activity', 'Normal', 'Median HR'],
            rows: overview.hourly.map(hour => [
              formatHour(hour.hour),
              hour.stress,
              hour.activity,
              hour.normal,
              formatValue(hour.medianHeartRate, ' bpm'),
            ]),
          }}
        >
          <StateColumnChart
            data={overview.hourly}
            formatX={hour => formatHour(hour.hour)}
            formatTitle={hour => `${formatHour(hour.hour)}–${formatHour((hour.hour + 1) % 24)} IST`}
            mode={hourlyMode}
          />
        </ChartCard>
        <Card title="By rank" subtitle="Ordered by seniority">
          <RankTable ranks={overview.ranks} />
        </Card>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <ChartCard
          title="Heart rate distribution"
          subtitle="All readings in 5 bpm bins"
          legend={
            <Legend
              items={[
                { label: `Above stress threshold (> ${thresholds.stressHeartRate} bpm)`, color: 'var(--state-stress)' },
                { label: 'At or below threshold', color: 'var(--neutral-mark)' },
              ]}
            />
          }
          table={{
            columns: ['Heart rate (bpm)', 'Readings', 'Share'],
            rows: overview.heartRateHistogram.map(bin => [bin.label, bin.count, formatPercent(bin.count / dataset.readings)]),
          }}
        >
          <HistogramChart
            total={dataset.readings}
            data={overview.heartRateHistogram.map(bin => ({
              label: bin.label,
              count: bin.count,
              highlight: bin.aboveStressThreshold,
            }))}
          />
        </ChartCard>
        <ChartCard
          title="SpO2 distribution"
          subtitle="All readings in 1% bins"
          legend={
            <Legend
              items={[
                { label: `Below stress threshold (< ${thresholds.stressSpo2}%)`, color: 'var(--state-stress)' },
                { label: 'At or above threshold', color: 'var(--neutral-mark)' },
              ]}
            />
          }
          table={{
            columns: ['SpO2', 'Readings', 'Share'],
            rows: overview.spo2Histogram.map(bin => [`${bin.value}%`, bin.count, formatPercent(bin.count / dataset.readings)]),
          }}
        >
          <HistogramChart
            total={dataset.readings}
            data={overview.spo2Histogram.map(bin => ({
              label: `${bin.value}%`,
              count: bin.count,
              highlight: bin.belowStressThreshold,
            }))}
          />
        </ChartCard>
      </div>

      <OfficerMixCard overview={overview} onSelectOfficer={onSelectOfficer} />
    </div>
  );
}

function RankTable({ ranks }: { ranks: RankSummary[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-136 text-left text-xs tabular-nums">
        <thead className="text-ink-2">
          <tr className="border-b border-line">
            <th scope="col" className="py-2 pr-3 font-medium">Rank</th>
            <th scope="col" className="px-3 py-2 text-right font-medium">Officers</th>
            <th scope="col" className="px-3 py-2 text-right font-medium">Readings</th>
            <th scope="col" className="px-3 py-2 text-right font-medium">Median HR</th>
            <th scope="col" className="px-3 py-2 text-right font-medium">Median SpO2</th>
            <th scope="col" className="w-32 px-3 py-2 font-medium">Label mix</th>
            <th scope="col" className="py-2 pl-3 text-right font-medium">Stress</th>
          </tr>
        </thead>
        <tbody>
          {ranks.map(rank => (
            <tr key={rank.rank} className="border-b border-line text-ink last:border-0">
              <td className="py-2.5 pr-3 font-medium">{rank.rank}</td>
              <td className="px-3 py-2.5 text-right">{rank.officers}</td>
              <td className="px-3 py-2.5 text-right">{formatInt(rank.readings)}</td>
              <td className="px-3 py-2.5 text-right">{formatValue(rank.medianHeartRate, ' bpm')}</td>
              <td className="px-3 py-2.5 text-right">{formatValue(rank.medianSpo2, '%')}</td>
              <td className="px-3 py-2.5">
                <StateMixBar counts={rank.states} />
              </td>
              <td className="py-2.5 pl-3 text-right">{formatPercent(shareOf(rank.states, 'stress'), 0)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function OfficerMixCard({
  overview,
  onSelectOfficer,
}: {
  overview: AnalyticsOverview;
  onSelectOfficer: (badgeId: string) => void;
}) {
  const officers = useMemo(
    () =>
      [...overview.officers].sort(
        (a, b) => shareOf(b.states, 'stress') - shareOf(a.states, 'stress') || b.readings - a.readings
      ),
    [overview.officers]
  );

  return (
    <Card
      title="Label mix by officer"
      subtitle="Sorted by Stress share. Select an officer to open their profile."
      actions={<Legend items={stateLegendItems} />}
    >
      <ul className="-mx-2 divide-y divide-line">
        {officers.map(officer => (
          <li key={officer.badgeId}>
            <button
              type="button"
              onClick={() => onSelectOfficer(officer.badgeId)}
              className="grid w-full grid-cols-[minmax(0,1fr)_3rem] items-center gap-x-4 gap-y-2 rounded-md px-2 py-2 text-left hover:bg-sunken sm:grid-cols-[minmax(0,15rem)_minmax(0,1fr)_3.5rem]"
            >
              <span className="min-w-0">
                <span className="block truncate text-sm font-medium text-ink">{officer.name}</span>
                <span className="block truncate text-xs text-ink-2">
                  {officer.badgeId} · {formatInt(officer.readings)} readings
                  {officer.lowSample && ' · low sample'}
                </span>
              </span>
              <span className="order-last col-span-2 sm:order-0 sm:col-span-1">
                <StateMixBar counts={officer.states} size="md" />
              </span>
              <span className="text-right text-sm font-medium tabular-nums text-ink">
                {formatPercent(shareOf(officer.states, 'stress'), 0)}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </Card>
  );
}
