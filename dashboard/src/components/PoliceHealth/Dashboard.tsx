'use client';

import React, { useEffect, useState } from 'react';
import { Shield } from 'lucide-react';
import { AnalyticsOverview, fetchOverview } from '../../lib/police-health/analytics-api';
import { formatInt, formatPeriod } from './format';
import { ErrorPanel, LoadingPanel } from './ui';
import OverviewTab from './OverviewTab';
import OfficersTab from './OfficersTab';
import OfficerDetailView from './OfficerDetail';
import DataQualityTab from './DataQualityTab';
import ThemeToggle from './ThemeToggle';

type Tab = 'overview' | 'officers' | 'quality';

const TABS: { key: Tab; label: string }[] = [
  { key: 'overview', label: 'Overview' },
  { key: 'officers', label: 'Officers' },
  { key: 'quality', label: 'Data quality' },
];

export default function PoliceHealthDashboard() {
  const [overview, setOverview] = useState<AnalyticsOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [tab, setTab] = useState<Tab>('overview');
  const [selectedBadge, setSelectedBadge] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchOverview().then(
      data => !cancelled && setOverview(data),
      (err: Error) => !cancelled && setError(err.message)
    );
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  const retry = () => {
    setError(null);
    setAttempt(value => value + 1);
  };

  const selectTab = (next: Tab) => {
    setTab(next);
    setSelectedBadge(null);
  };

  const openOfficer = (badgeId: string) => {
    setTab('officers');
    setSelectedBadge(badgeId);
    window.scrollTo({ top: 0 });
  };

  return (
    <div className="min-h-screen bg-page text-ink">
      <header className="border-b border-line bg-surface">
        <div className="mx-auto flex max-w-350 flex-wrap items-center justify-between gap-x-8 gap-y-4 px-4 pt-5 sm:px-6 lg:px-8">
          <div className="flex items-center gap-3">
            <div className="rounded-lg bg-ink p-2 text-surface">
              <Shield size={20} aria-hidden />
            </div>
            <div>
              <h1 className="text-lg font-semibold tracking-tight">Police Personnel Health Analytics</h1>
              <p className="text-xs text-ink-2">Spandan smartwatch telemetry · labelled training split</p>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-x-8 gap-y-3">
            {overview && (
              <dl className="flex flex-wrap gap-x-6 gap-y-2 text-xs">
                <HeaderFact label="Source" value={overview.dataset.source} />
                <HeaderFact label="Readings" value={formatInt(overview.dataset.readings)} />
                <HeaderFact label="Officers" value={formatInt(overview.dataset.officers)} />
                <HeaderFact label="Window (IST)" value={formatPeriod(overview.dataset.start, overview.dataset.end)} />
              </dl>
            )}
            <ThemeToggle />
          </div>
        </div>
        <nav className="mx-auto mt-4 max-w-350 px-4 sm:px-6 lg:px-8" aria-label="Dashboard sections">
          <div role="tablist" className="-mb-px flex gap-6 overflow-x-auto">
            {TABS.map(item => (
              <button
                key={item.key}
                type="button"
                role="tab"
                aria-selected={tab === item.key}
                onClick={() => selectTab(item.key)}
                className={`whitespace-nowrap border-b-2 pb-3 text-sm font-medium transition-colors ${
                  tab === item.key ? 'border-ink text-ink' : 'border-transparent text-ink-2 hover:text-ink'
                }`}
              >
                {item.label}
              </button>
            ))}
          </div>
        </nav>
      </header>

      <main className="mx-auto max-w-350 px-4 py-6 sm:px-6 lg:px-8">
        {error && <ErrorPanel title="Training data unavailable" message={error} onRetry={retry} />}
        {!error && !overview && <LoadingPanel label="Loading training data…" />}
        {overview && tab === 'overview' && <OverviewTab overview={overview} onSelectOfficer={openOfficer} />}
        {overview && tab === 'officers' && !selectedBadge && (
          <OfficersTab overview={overview} onSelectOfficer={openOfficer} />
        )}
        {overview && tab === 'officers' && selectedBadge && (
          <OfficerDetailView
            badgeId={selectedBadge}
            officers={overview.officers}
            thresholds={overview.thresholds}
            onBack={() => setSelectedBadge(null)}
            onSelectOfficer={setSelectedBadge}
          />
        )}
        {overview && tab === 'quality' && <DataQualityTab overview={overview} onSelectOfficer={openOfficer} />}
      </main>
    </div>
  );
}

function HeaderFact({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-ink-2">{label}</dt>
      <dd className="mt-0.5 font-medium text-ink">{value}</dd>
    </div>
  );
}
