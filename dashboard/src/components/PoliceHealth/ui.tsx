'use client';

import React, { useState } from 'react';
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import type { TooltipContentProps } from 'recharts';
import { ChartColumn, CircleCheck, Info, OctagonAlert, RefreshCw, Table2, TriangleAlert } from 'lucide-react';
import type { AnalyticsOverview, StateCounts, StateKey, StressDrivers } from '../../lib/police-health/analytics-api';
import { formatCompact, formatInt, formatPercent, shareOf, totalOf } from './format';

export const STATE_ORDER: StateKey[] = ['stress', 'activity', 'normal'];

/** Labelling rules from 18_09_26/code/prepare_temporal_splits.py. */
export const STATE_META: Record<StateKey, { label: string; color: string; rule: string }> = {
  stress: {
    label: 'Stress',
    color: 'var(--state-stress)',
    rule: 'Stationary, with heart rate above 90 bpm or SpO2 below 91%.',
  },
  activity: {
    label: 'Physical activity',
    color: 'var(--state-activity)',
    rule: 'Wrist-motion variance above 0.12 g or GPS speed above 4.5 km/h.',
  },
  normal: {
    label: 'Normal',
    color: 'var(--state-normal)',
    rule: 'Neither the activity nor the stress conditions are met.',
  },
};

export const stateLegendItems = STATE_ORDER.map(key => ({ label: STATE_META[key].label, color: STATE_META[key].color }));

const AXIS_TICK = { fill: 'var(--ink-muted)', fontSize: 11 };
export const xAxisProps = { tick: AXIS_TICK, tickLine: false, axisLine: { stroke: 'var(--axis)' } } as const;
export const yAxisProps = { tick: AXIS_TICK, tickLine: false, axisLine: false, width: 44 } as const;

export type CountMode = 'count' | 'share';
export const COUNT_MODE_OPTIONS: { value: CountMode; label: string }[] = [
  { value: 'count', label: 'Count' },
  { value: 'share', label: 'Share' },
];

// ---------------------------------------------------------------------------
// Layout
// ---------------------------------------------------------------------------

export function Card({
  title,
  subtitle,
  actions,
  className = '',
  children,
}: {
  title?: string;
  subtitle?: React.ReactNode;
  actions?: React.ReactNode;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <section className={`min-w-0 rounded-xl border border-line bg-surface p-5 ${className}`}>
      {(title || actions) && (
        <header className="mb-4 flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
          <div className="min-w-0 flex-1 basis-56">
            {title && <h3 className="text-sm font-semibold text-ink">{title}</h3>}
            {subtitle && <p className="mt-0.5 text-xs leading-relaxed text-ink-2">{subtitle}</p>}
          </div>
          {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
        </header>
      )}
      {children}
    </section>
  );
}

export interface TableData {
  columns: string[];
  rows: (string | number)[][];
}

export function DataTable({ columns, rows, maxHeight }: TableData & { maxHeight?: number }) {
  return (
    <div className="overflow-auto rounded-lg border border-line" style={{ maxHeight }}>
      <table className="w-full text-left text-xs tabular-nums">
        <thead className="sticky top-0 bg-sunken text-ink-2">
          <tr>
            {columns.map((column, index) => (
              <th key={column} scope="col" className={`whitespace-nowrap px-3 py-2 font-medium ${index ? 'text-right' : ''}`}>
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, rowIndex) => (
            <tr key={rowIndex} className="border-t border-line text-ink">
              {row.map((cell, index) => (
                <td key={index} className={`whitespace-nowrap px-3 py-1.5 ${index ? 'text-right' : ''}`}>
                  {typeof cell === 'number' ? formatInt(cell) : cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Card holding a chart, with a table-view toggle as its accessible twin. */
export function ChartCard({
  title,
  subtitle,
  controls,
  legend,
  table,
  height = 260,
  className,
  children,
}: {
  title: string;
  subtitle?: React.ReactNode;
  controls?: React.ReactNode;
  legend?: React.ReactNode;
  table?: TableData;
  height?: number;
  className?: string;
  children: React.ReactNode;
}) {
  const [showTable, setShowTable] = useState(false);
  const toggle = table && (
    <button
      type="button"
      onClick={() => setShowTable(value => !value)}
      className="inline-flex items-center gap-1.5 rounded-md border border-line px-2.5 py-1 text-xs font-medium text-ink-2 hover:bg-sunken hover:text-ink"
    >
      {showTable ? <ChartColumn size={14} aria-hidden /> : <Table2 size={14} aria-hidden />}
      {showTable ? 'Chart' : 'Table'}
    </button>
  );

  return (
    <Card title={title} subtitle={subtitle} className={className} actions={(controls || toggle) && <>{!showTable && controls}{toggle}</>}>
      {showTable && table ? (
        <DataTable {...table} maxHeight={height + 40} />
      ) : (
        <>
          {legend && <div className="mb-3">{legend}</div>}
          <div style={{ height }}>{children}</div>
        </>
      )}
    </Card>
  );
}

export function StatTile({
  label,
  value,
  unit,
  detail,
}: {
  label: string;
  value: string;
  unit?: string;
  detail?: React.ReactNode;
}) {
  return (
    <div className="min-w-0 rounded-xl border border-line bg-surface px-4 py-4">
      <p className="text-xs font-medium text-ink-2">{label}</p>
      <p className="mt-2 flex flex-wrap items-baseline gap-x-1">
        <span className="text-2xl font-semibold tracking-tight text-ink">{value}</span>
        {unit && <span className="text-sm text-ink-2">{unit}</span>}
      </p>
      {detail && <p className="mt-1 text-xs leading-relaxed text-ink-2">{detail}</p>}
    </div>
  );
}

export function Segmented<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T;
  options: { value: T; label: string }[];
  onChange: (value: T) => void;
}) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex rounded-md border border-line bg-sunken p-0.5 text-xs">
      {options.map(option => (
        <button
          key={option.value}
          type="button"
          role="radio"
          aria-checked={option.value === value}
          onClick={() => onChange(option.value)}
          className={`rounded px-2.5 py-0.5 font-medium transition-colors ${
            option.value === value ? 'bg-surface text-ink shadow-sm' : 'text-ink-2 hover:text-ink'
          }`}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Status, legends and state bars
// ---------------------------------------------------------------------------

const STATUS_META = {
  good: { label: 'Good', icon: CircleCheck, color: 'var(--status-good)' },
  warning: { label: 'Warning', icon: TriangleAlert, color: 'var(--status-warning)' },
  critical: { label: 'Critical', icon: OctagonAlert, color: 'var(--status-critical)' },
  info: { label: 'Note', icon: Info, color: 'var(--ink-muted)' },
};

export type Status = keyof typeof STATUS_META;

export function StatusBadge({ status, label }: { status: Status; label?: string }) {
  const meta = STATUS_META[status];
  const Icon = meta.icon;
  return (
    <span className="inline-flex items-center gap-1.5 text-xs font-medium text-ink-2">
      <Icon size={14} style={{ color: meta.color }} aria-hidden />
      {label ?? meta.label}
    </span>
  );
}

type SwatchShape = 'square' | 'line' | 'dashed';

export function Swatch({ color, shape = 'square' }: { color: string; shape?: SwatchShape }) {
  if (shape === 'dashed') {
    return <span aria-hidden className="inline-block w-3 shrink-0 border-t-2 border-dashed" style={{ borderColor: color }} />;
  }
  return shape === 'line' ? (
    <span aria-hidden className="inline-block h-0.5 w-3 shrink-0 rounded-full" style={{ background: color }} />
  ) : (
    <span aria-hidden className="inline-block size-2.5 shrink-0 rounded-[3px]" style={{ background: color }} />
  );
}

export function Legend({ items }: { items: { label: string; color: string; shape?: SwatchShape }[] }) {
  return (
    <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-2">
      {items.map(item => (
        <li key={item.label} className="flex items-center gap-1.5">
          <Swatch color={item.color} shape={item.shape} />
          {item.label}
        </li>
      ))}
    </ul>
  );
}

const BAR_HEIGHT = { sm: 'h-2', md: 'h-3', lg: 'h-9' };

/** 100% stacked bar of physical-state shares, with 2px surface gaps between segments. */
export function StateMixBar({
  counts,
  size = 'sm',
  showLabels = false,
}: {
  counts: StateCounts;
  size?: keyof typeof BAR_HEIGHT;
  showLabels?: boolean;
}) {
  const total = totalOf(counts);
  const description = STATE_ORDER.map(key => `${STATE_META[key].label} ${formatPercent(shareOf(counts, key))}`).join(' · ');
  return (
    <div role="img" aria-label={description} title={description} className={`flex w-full gap-0.5 overflow-hidden rounded ${BAR_HEIGHT[size]}`}>
      {STATE_ORDER.map(key => {
        const share = total ? counts[key] / total : 0;
        if (!share) return null;
        return (
          <div
            key={key}
            className="flex h-full min-w-0.5 items-center justify-center"
            style={{ width: `${share * 100}%`, background: STATE_META[key].color }}
          >
            {/* Ink reads at >= 4.4:1 on every state fill in both themes. */}
            {showLabels && share >= 0.1 && <span className="text-xs font-semibold text-[#0b0b0b]">{formatPercent(share, 0)}</span>}
          </div>
        );
      })}
    </div>
  );
}

/** Legend for a state mix that doubles as its value table. */
export function StateBreakdown({ counts, showRules = false }: { counts: StateCounts; showRules?: boolean }) {
  return (
    <dl className="grid gap-4 sm:grid-cols-3">
      {STATE_ORDER.map(key => (
        <div key={key} className="min-w-0">
          <dt className="flex items-center gap-2 text-sm font-medium text-ink">
            <Swatch color={STATE_META[key].color} />
            {STATE_META[key].label}
          </dt>
          <dd className="mt-1 text-xl font-semibold text-ink">
            {formatPercent(shareOf(counts, key))}
            <span className="ml-1.5 text-sm font-normal text-ink-2">{formatInt(counts[key])} readings</span>
          </dd>
          {showRules && <dd className="mt-1 text-xs leading-relaxed text-ink-2">{STATE_META[key].rule}</dd>}
        </div>
      ))}
    </dl>
  );
}

/** Horizontal bars for a short list of labelled counts. */
export function CountBars({
  items,
  total,
  color = 'var(--measure)',
}: {
  items: { label: string; count: number; color?: string }[];
  total: number;
  color?: string;
}) {
  return (
    <ul className="space-y-3">
      {items.map(item => (
        <li key={item.label}>
          <div className="flex items-baseline justify-between gap-3 text-xs">
            <span className="text-ink-2">{item.label}</span>
            <span className="shrink-0 tabular-nums text-ink">
              <span className="font-medium">{formatInt(item.count)}</span>
              <span className="ml-1.5 text-ink-2">{formatPercent(total ? item.count / total : 0)}</span>
            </span>
          </div>
          <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-sunken">
            <div className="h-full rounded-full" style={{ width: `${total ? (item.count / total) * 100 : 0}%`, background: item.color ?? color }} />
          </div>
        </li>
      ))}
    </ul>
  );
}

export function StressDriversCard({
  drivers,
  thresholds,
}: {
  drivers: StressDrivers;
  thresholds: AnalyticsOverview['thresholds'];
}) {
  const hrDriven = drivers.heartRateOnly + drivers.both;
  return (
    <Card title="What triggers the Stress label" subtitle="Condition behind each stress-labelled (stationary) reading">
      {drivers.total === 0 ? (
        <p className="text-sm text-ink-2">No readings were labelled Stress.</p>
      ) : (
        <>
          <p className="text-3xl font-semibold tracking-tight text-ink">{formatPercent(drivers.spo2Only / drivers.total)}</p>
          <p className="mt-1 text-xs text-ink-2">of Stress labels come from low SpO2 alone</p>
          <div className="mt-5">
            <CountBars
              total={drivers.total}
              color="var(--state-stress)"
              items={[
                { label: `SpO2 below ${thresholds.stressSpo2}% only`, count: drivers.spo2Only },
                { label: `Heart rate above ${thresholds.stressHeartRate} bpm only`, count: drivers.heartRateOnly },
                { label: 'Both conditions', count: drivers.both },
              ]}
            />
          </div>
          {hrDriven / drivers.total < 0.1 && (
            <p className="mt-5 text-xs leading-relaxed text-ink-2">
              Heart rate rarely exceeds {thresholds.stressHeartRate} bpm here, so this class mostly reflects low SpO2 while
              stationary. Read it alongside the SpO2 checks on the Data quality tab.
            </p>
          )}
        </>
      )}
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Charts
// ---------------------------------------------------------------------------

export function TooltipCard({
  title,
  rows,
  footer,
}: {
  title: string;
  rows: { label: string; value: string; color?: string }[];
  footer?: string;
}) {
  return (
    <div className="min-w-44 rounded-lg border border-line bg-surface px-3 py-2.5 text-xs shadow-lg">
      <p className="mb-1.5 font-medium text-ink-2">{title}</p>
      <ul className="space-y-1">
        {rows.map(row => (
          <li key={row.label} className="flex items-center gap-2">
            {row.color && <Swatch color={row.color} shape="line" />}
            <span className="font-semibold tabular-nums text-ink">{row.value}</span>
            <span className="text-ink-2">{row.label}</span>
          </li>
        ))}
      </ul>
      {footer && <p className="mt-1.5 border-t border-line pt-1.5 text-ink-2">{footer}</p>}
    </div>
  );
}

/** The data row under the pointer, or null when the tooltip is inactive. */
export function tooltipDatum<T>(props: Pick<TooltipContentProps, 'active' | 'payload'>): T | null {
  if (!props.active || !props.payload?.length) return null;
  return (props.payload[0].payload as T) ?? null;
}

export function StateCountsTooltip({ title, counts }: { title: string; counts: StateCounts }) {
  const total = totalOf(counts);
  return (
    <TooltipCard
      title={title}
      rows={STATE_ORDER.map(key => ({
        label: STATE_META[key].label,
        value: `${formatInt(counts[key])} · ${formatPercent(shareOf(counts, key), 0)}`,
        color: STATE_META[key].color,
      }))}
      footer={`${formatInt(total)} readings`}
    />
  );
}

/** Stacked columns of state counts (or shares) over a category axis. */
export function StateColumnChart<T extends StateCounts>({
  data,
  formatX,
  formatTitle,
  mode,
}: {
  data: T[];
  formatX: (datum: T) => string;
  formatTitle: (datum: T) => string;
  mode: CountMode;
}) {
  const rows = data.map(datum => ({ ...datum, x: formatX(datum) }));
  return (
    <ResponsiveContainer width="100%" height="100%" initialDimension={{ width: 1, height: 1 }}>
      <BarChart
        data={rows}
        stackOffset={mode === 'share' ? 'expand' : 'none'}
        margin={{ top: 4, right: 4, bottom: 0, left: 0 }}
        barCategoryGap="18%"
      >
        <CartesianGrid vertical={false} stroke="var(--grid)" />
        <XAxis dataKey="x" minTickGap={12} {...xAxisProps} />
        <YAxis
          {...yAxisProps}
          tickFormatter={mode === 'share' ? (value: number) => `${Math.round(value * 100)}%` : formatCompact}
        />
        <Tooltip
          cursor={{ fill: 'var(--surface-sunken)' }}
          isAnimationActive={false}
          content={props => {
            const datum = tooltipDatum<T>(props);
            return datum ? <StateCountsTooltip title={formatTitle(datum)} counts={datum} /> : null;
          }}
        />
        {STATE_ORDER.map((key, index) => (
          <Bar
            key={key}
            dataKey={key}
            name={STATE_META[key].label}
            stackId="state"
            fill={STATE_META[key].color}
            stroke="var(--surface)"
            strokeWidth={2}
            maxBarSize={24}
            radius={index === STATE_ORDER.length - 1 ? [4, 4, 0, 0] : 0}
            isAnimationActive={false}
          />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}

export interface HistogramBin {
  label: string;
  count: number;
  highlight: boolean;
}

/** Single-series histogram: neutral bars, threshold-crossing bins in the Stress colour. */
export function HistogramChart({ data, total }: { data: HistogramBin[]; total: number }) {
  return (
    <ResponsiveContainer width="100%" height="100%" initialDimension={{ width: 1, height: 1 }}>
      <BarChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: 0 }} barCategoryGap={2}>
        <CartesianGrid vertical={false} stroke="var(--grid)" />
        <XAxis dataKey="label" minTickGap={8} {...xAxisProps} />
        <YAxis {...yAxisProps} tickFormatter={formatCompact} />
        <Tooltip
          cursor={{ fill: 'var(--surface-sunken)' }}
          isAnimationActive={false}
          content={props => {
            const datum = tooltipDatum<HistogramBin>(props);
            if (!datum) return null;
            return (
              <TooltipCard
                title={datum.label}
                rows={[
                  {
                    label: 'readings',
                    value: `${formatInt(datum.count)} · ${formatPercent(total ? datum.count / total : 0)}`,
                    color: datum.highlight ? 'var(--state-stress)' : 'var(--neutral-mark)',
                  },
                ]}
              />
            );
          }}
        />
        <Bar dataKey="count" maxBarSize={24} radius={[4, 4, 0, 0]} isAnimationActive={false}>
          {data.map(bin => (
            <Cell key={bin.label} fill={bin.highlight ? 'var(--state-stress)' : 'var(--neutral-mark)'} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

// ---------------------------------------------------------------------------
// Loading and error states
// ---------------------------------------------------------------------------

export function LoadingPanel({ label }: { label: string }) {
  return (
    <div className="flex items-center justify-center gap-3 rounded-xl border border-line bg-surface px-6 py-16 text-sm text-ink-2">
      <RefreshCw size={16} className="animate-spin" aria-hidden />
      {label}
    </div>
  );
}

export function ErrorPanel({ title, message, onRetry }: { title: string; message: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="rounded-xl border border-line bg-surface px-6 py-8">
      <StatusBadge status="critical" label={title} />
      <p className="mt-2 text-sm text-ink">{message}</p>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="mt-4 inline-flex items-center gap-1.5 rounded-md bg-ink px-3 py-1.5 text-xs font-medium text-surface hover:opacity-90"
        >
          <RefreshCw size={14} aria-hidden />
          Try again
        </button>
      )}
    </div>
  );
}
