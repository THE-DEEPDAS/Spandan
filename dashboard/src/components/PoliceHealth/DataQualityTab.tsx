'use client';

import React from 'react';
import { TriangleAlert } from 'lucide-react';
import type { AnalyticsOverview, OfficerSummary, SensorCoverage } from '../../lib/police-health/analytics-api';
import { formatInt, formatPercent } from './format';
import { Card, CountBars, Status, StatusBadge } from './ui';

function coverageStatus(coverage: number): { status: Status; label: string; color: string } {
  if (coverage >= 0.9) return { status: 'good', label: 'Available', color: 'var(--status-good)' };
  if (coverage >= 0.5) return { status: 'warning', label: 'Partial', color: 'var(--status-warning)' };
  return { status: 'info', label: coverage === 0 ? 'Not recorded' : 'Rarely recorded', color: 'var(--ink-muted)' };
}

/** Per-officer checks; a value past its limit gets a warning icon next to it. */
const OFFICER_CHECKS: {
  key: string;
  label: string;
  value: (officer: OfficerSummary) => number;
  flagged: (value: number) => boolean;
}[] = [
  { key: 'hr', label: 'HR measured', value: officer => officer.hrMeasuredShare, flagged: value => value < 0.9 },
  { key: 'modal', label: 'HR at most common value', value: officer => officer.modalHeartRateShare, flagged: value => value > 0.4 },
  { key: 'spo2', label: 'SpO2 < 85%', value: officer => officer.severeSpo2Share, flagged: value => value > 0.25 },
  { key: 'gps', label: 'GPS fix', value: officer => officer.gpsFixShare, flagged: value => value < 0.9 },
];

export default function DataQualityTab({
  overview,
  onSelectOfficer,
}: {
  overview: AnalyticsOverview;
  onSelectOfficer: (badgeId: string) => void;
}) {
  const { quality, dataset } = overview;
  const samplingTotal = quality.samplingIntervals.reduce((sum, bucket) => sum + bucket.count, 0);
  const officers = [...overview.officers].sort((a, b) => b.readings - a.readings);

  return (
    <div className="space-y-6">
      <section>
        <h2 className="text-sm font-semibold text-ink">Findings</h2>
        <p className="mt-0.5 text-xs text-ink-2">
          Checks on {dataset.source} ({formatInt(dataset.readings)} readings) to read before relying on the charts.
        </p>
        <div className="mt-3 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {quality.issues.map(issue => (
            <article key={issue.key} className="flex flex-col rounded-xl border border-line bg-surface p-5">
              <StatusBadge status={issue.severity} />
              <h3 className="mt-2 text-sm font-semibold text-ink">{issue.title}</h3>
              <p className="mt-3 flex flex-wrap items-baseline gap-x-2">
                <span className="text-2xl font-semibold tracking-tight text-ink">{formatPercent(issue.share)}</span>
                <span className="text-xs text-ink-2">
                  {issue.denominator} · {formatInt(issue.count)}
                </span>
              </p>
              <p className="mt-2 text-xs leading-relaxed text-ink-2">{issue.detail}</p>
            </article>
          ))}
        </div>
      </section>

      <div className="grid gap-6 lg:grid-cols-5">
        <Card className="lg:col-span-3" title="Sensor coverage" subtitle="Share of readings carrying a genuine value from each sensor">
          <ul className="divide-y divide-line">
            {quality.sensors.map(sensor => (
              <SensorRow key={sensor.key} sensor={sensor} />
            ))}
          </ul>
        </Card>
        <Card
          className="lg:col-span-2 lg:self-start"
          title="Sampling interval"
          subtitle="Time since the officer's previous reading. The watch reports every 30 s while recording."
        >
          <CountBars total={samplingTotal} items={quality.samplingIntervals} />
        </Card>
      </div>

      <Card
        title="Quality by officer"
        subtitle="Values past a check's limit are marked. Select a row to open the officer's profile."
      >
        <div className="-mx-5 overflow-x-auto">
          <table className="w-full min-w-176 text-left text-xs tabular-nums">
            <thead className="text-ink-2">
              <tr className="border-b border-line">
                <th scope="col" className="py-2 pl-5 pr-3 font-medium">Officer</th>
                <th scope="col" className="px-3 py-2 text-right font-medium">Readings</th>
                {OFFICER_CHECKS.map(check => (
                  <th key={check.key} scope="col" className="px-3 py-2 text-right font-medium last:pr-5">
                    {check.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {officers.map(officer => (
                <tr
                  key={officer.badgeId}
                  tabIndex={0}
                  onClick={() => onSelectOfficer(officer.badgeId)}
                  onKeyDown={event => {
                    if (event.key === 'Enter' || event.key === ' ') {
                      event.preventDefault();
                      onSelectOfficer(officer.badgeId);
                    }
                  }}
                  className="cursor-pointer border-b border-line text-ink last:border-0 hover:bg-sunken focus:bg-sunken focus:outline-none"
                >
                  <td className="py-2.5 pl-5 pr-3">
                    <span className="block font-medium">{officer.name}</span>
                    <span className="block text-ink-2">{officer.badgeId}</span>
                  </td>
                  <td className="px-3 py-2.5 text-right">{formatInt(officer.readings)}</td>
                  {OFFICER_CHECKS.map(check => {
                    const value = check.value(officer);
                    const flagged = check.flagged(value);
                    return (
                      <td key={check.key} className="px-3 py-2.5 text-right last:pr-5">
                        <span className="inline-flex items-center gap-1">
                          {flagged && (
                            <TriangleAlert size={12} style={{ color: 'var(--status-warning)' }} aria-label="Past limit" />
                          )}
                          {formatPercent(value, 0)}
                        </span>
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}

function SensorRow({ sensor }: { sensor: SensorCoverage }) {
  const status = coverageStatus(sensor.coverage);
  return (
    <li className="grid grid-cols-1 gap-x-6 gap-y-2 py-3 sm:grid-cols-[minmax(0,1fr)_11rem_7rem] sm:items-center">
      <div className="min-w-0">
        <p className="text-sm font-medium text-ink">{sensor.label}</p>
        <p className="text-xs text-ink-2">{sensor.note}</p>
      </div>
      <div className="flex items-center gap-3">
        <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-sunken">
          <div className="h-full rounded-full" style={{ width: `${sensor.coverage * 100}%`, background: status.color }} />
        </div>
        <span className="w-12 text-right text-xs font-medium tabular-nums text-ink">{formatPercent(sensor.coverage)}</span>
      </div>
      <StatusBadge status={status.status} label={status.label} />
    </li>
  );
}
