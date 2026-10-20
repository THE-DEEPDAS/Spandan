import type { StateCounts, StateKey } from '../../lib/police-health/analytics-api';

const TIME_ZONE = 'Asia/Kolkata';

const integerFormat = new Intl.NumberFormat('en-IN');
const compactFormat = new Intl.NumberFormat('en-IN', { notation: 'compact', maximumFractionDigits: 1 });
const dateFormat = new Intl.DateTimeFormat('en-IN', { day: 'numeric', month: 'short', year: 'numeric', timeZone: TIME_ZONE });
const shortDateFormat = new Intl.DateTimeFormat('en-IN', { day: 'numeric', month: 'short', timeZone: TIME_ZONE });
const dateTimeFormat = new Intl.DateTimeFormat('en-IN', {
  day: 'numeric',
  month: 'short',
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
  timeZone: TIME_ZONE,
});
const timeFormat = new Intl.DateTimeFormat('en-IN', { hour: '2-digit', minute: '2-digit', hour12: false, timeZone: TIME_ZONE });

export const formatInt = (value: number) => integerFormat.format(value);
export const formatCompact = (value: number) => compactFormat.format(value);

export const formatPercent = (share: number, digits = 1) => `${(share * 100).toFixed(digits)}%`;

export const formatValue = (value: number | null | undefined, unit = '', digits = 0) =>
  value == null ? '—' : `${value.toFixed(digits)}${unit}`;

/** Calendar dates from the API ("2026-07-14") are already IST days. */
const parseDay = (day: string) => new Date(`${day}T12:00:00+05:30`);

export const formatDay = (day: string) => shortDateFormat.format(parseDay(day));
export const formatDate = (value: string | number) => dateFormat.format(new Date(value));
export const formatShortDate = (value: string | number) => shortDateFormat.format(new Date(value));
export const formatDateTime = (value: string | number) => dateTimeFormat.format(new Date(value));
export const formatTime = (value: string | number) => timeFormat.format(new Date(value));
export const formatHour = (hour: number) => `${String(hour).padStart(2, '0')}:00`;

export const formatPeriod = (start: string, end: string) => {
  const from = formatShortDate(start);
  const to = formatShortDate(end);
  return from === to ? from : `${from} – ${to}`;
};

export const totalOf = (counts: StateCounts) => counts.stress + counts.activity + counts.normal;

export const shareOf = (counts: StateCounts, key: StateKey) => {
  const total = totalOf(counts);
  return total ? counts[key] / total : 0;
};
