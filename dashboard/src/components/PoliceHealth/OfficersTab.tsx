'use client';

import React, { useMemo, useState } from 'react';
import { ArrowDown, ArrowUp, Search } from 'lucide-react';
import type { AnalyticsOverview, OfficerSummary } from '../../lib/police-health/analytics-api';
import { formatInt, formatPercent, formatPeriod, formatValue, shareOf } from './format';
import { Card, Legend, StateMixBar, stateLegendItems } from './ui';

interface Column {
  key: string;
  label: string;
  numeric?: boolean;
  sortValue: (officer: OfficerSummary) => number | string;
  render: (officer: OfficerSummary) => React.ReactNode;
}

const COLUMNS: Column[] = [
  {
    key: 'name',
    label: 'Officer',
    sortValue: officer => officer.name,
    render: officer => (
      <>
        <span className="block font-medium text-ink">{officer.name}</span>
        <span className="block text-ink-2">
          {officer.badgeId}
          {officer.lowSample && ' · low sample'}
        </span>
      </>
    ),
  },
  { key: 'rank', label: 'Rank', sortValue: officer => officer.rank, render: officer => officer.rank },
  {
    key: 'readings',
    label: 'Readings',
    numeric: true,
    sortValue: officer => officer.readings,
    render: officer => formatInt(officer.readings),
  },
  {
    key: 'activeDays',
    label: 'Active days',
    numeric: true,
    sortValue: officer => officer.activeDays,
    render: officer => officer.activeDays,
  },
  {
    key: 'period',
    label: 'Period (IST)',
    sortValue: officer => officer.firstSeen,
    render: officer => formatPeriod(officer.firstSeen, officer.lastSeen),
  },
  {
    key: 'medianHeartRate',
    label: 'Median HR',
    numeric: true,
    sortValue: officer => officer.medianHeartRate ?? -1,
    render: officer => formatValue(officer.medianHeartRate, ' bpm'),
  },
  {
    key: 'medianSpo2',
    label: 'Median SpO2',
    numeric: true,
    sortValue: officer => officer.medianSpo2 ?? -1,
    render: officer => formatValue(officer.medianSpo2, '%'),
  },
  {
    key: 'lowSpo2Share',
    label: 'SpO2 < 90%',
    numeric: true,
    sortValue: officer => officer.lowSpo2Share,
    render: officer => formatPercent(officer.lowSpo2Share, 0),
  },
  {
    key: 'mix',
    label: 'Label mix',
    sortValue: officer => shareOf(officer.states, 'activity'),
    render: officer => (
      <span className="block w-32">
        <StateMixBar counts={officer.states} />
      </span>
    ),
  },
  {
    key: 'stress',
    label: 'Stress',
    numeric: true,
    sortValue: officer => shareOf(officer.states, 'stress'),
    render: officer => formatPercent(shareOf(officer.states, 'stress'), 0),
  },
];

export default function OfficersTab({
  overview,
  onSelectOfficer,
}: {
  overview: AnalyticsOverview;
  onSelectOfficer: (badgeId: string) => void;
}) {
  const [query, setQuery] = useState('');
  const [rank, setRank] = useState('all');
  const [hideLowSample, setHideLowSample] = useState(false);
  const [sort, setSort] = useState<{ key: string; descending: boolean }>({ key: 'readings', descending: true });

  const officers = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const column = COLUMNS.find(candidate => candidate.key === sort.key) ?? COLUMNS[0];
    return overview.officers
      .filter(officer => rank === 'all' || officer.rank === rank)
      .filter(officer => !hideLowSample || !officer.lowSample)
      .filter(officer => !needle || `${officer.name} ${officer.badgeId}`.toLowerCase().includes(needle))
      .sort((a, b) => {
        const left = column.sortValue(a);
        const right = column.sortValue(b);
        const order = typeof left === 'string' ? left.localeCompare(String(right)) : left - (right as number);
        return sort.descending ? -order : order;
      });
  }, [overview.officers, query, rank, hideLowSample, sort]);

  const toggleSort = (key: string) =>
    setSort(current => (current.key === key ? { key, descending: !current.descending } : { key, descending: key !== 'name' }));

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <label className="relative">
          <span className="sr-only">Search officers</span>
          <Search size={14} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-ink-3" aria-hidden />
          <input
            type="search"
            value={query}
            onChange={event => setQuery(event.target.value)}
            placeholder="Search name or badge"
            className="w-60 rounded-md border border-line bg-surface py-1.5 pl-8 pr-3 text-sm text-ink placeholder:text-ink-3 focus:outline-2 focus:outline-ink"
          />
        </label>
        <label className="flex items-center gap-2 text-xs text-ink-2">
          Rank
          <select
            value={rank}
            onChange={event => setRank(event.target.value)}
            className="rounded-md border border-line bg-surface px-2 py-1.5 text-sm text-ink"
          >
            <option value="all">All ranks</option>
            {overview.ranks.map(option => (
              <option key={option.rank} value={option.rank}>
                {option.rank}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-2 text-xs text-ink-2">
          <input type="checkbox" checked={hideLowSample} onChange={event => setHideLowSample(event.target.checked)} />
          Hide officers with fewer than {overview.thresholds.lowSampleReadings} readings
        </label>
      </div>

      <Card
        title={`${officers.length} of ${overview.officers.length} officers`}
        subtitle="Select a row to open the officer's profile. Column headers sort the table."
        actions={<Legend items={stateLegendItems} />}
      >
        <div className="-mx-5 overflow-x-auto">
          <table className="w-full min-w-240 text-left text-xs tabular-nums">
            <thead className="text-ink-2">
              <tr className="border-b border-line">
                {COLUMNS.map(column => (
                  <th
                    key={column.key}
                    scope="col"
                    aria-sort={sort.key === column.key ? (sort.descending ? 'descending' : 'ascending') : undefined}
                    className={`px-3 py-2 font-medium first:pl-5 last:pr-5 ${column.numeric ? 'text-right' : ''}`}
                  >
                    <button
                      type="button"
                      onClick={() => toggleSort(column.key)}
                      className={`inline-flex items-center gap-1 hover:text-ink ${sort.key === column.key ? 'text-ink' : ''}`}
                    >
                      {column.label}
                      {sort.key === column.key &&
                        (sort.descending ? <ArrowDown size={12} aria-hidden /> : <ArrowUp size={12} aria-hidden />)}
                    </button>
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
                  {COLUMNS.map(column => (
                    <td
                      key={column.key}
                      className={`px-3 py-2.5 first:pl-5 last:pr-5 ${column.numeric ? 'text-right' : ''} ${
                        officer.lowSample && column.key !== 'name' ? 'text-ink-2' : ''
                      }`}
                    >
                      {column.render(officer)}
                    </td>
                  ))}
                </tr>
              ))}
              {officers.length === 0 && (
                <tr>
                  <td colSpan={COLUMNS.length} className="px-5 py-10 text-center text-sm text-ink-2">
                    No officers match these filters.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
