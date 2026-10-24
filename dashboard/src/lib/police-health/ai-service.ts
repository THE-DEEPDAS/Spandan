import { RawData, DerivedMetrics } from './data-logic';
import { API_BASE_URL, getJson } from './analytics-api';

export interface AIRecommendation {
  status: 'normal' | 'anomaly' | 'warning';
  message: string;
  recommendation: string;
}

/** Pass recent telemetry to the backend for context-aware health analysis. */
export async function getPoliceHealthInsights(
  history: { timestamp?: string; raw: RawData; derived: DerivedMetrics }[]
): Promise<AIRecommendation> {
  const response = await fetch(`${API_BASE_URL}/api/ai/recommendation`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      history: history.slice(-30).map(point => ({
        timestamp: point.timestamp || new Date().toISOString(),
        raw: point.raw,
        derived: point.derived,
      })),
    }),
  });
  const result = await response.json();
  if (!response.ok) {
    throw new Error(result.detail || 'AI analysis request failed');
  }
  return result as AIRecommendation;
}

/** Ask the backend for an AI summary of one officer's aggregated training-period profile. */
export const getOfficerAssessment = (badgeId: string) =>
  getJson<AIRecommendation>(`/api/analytics/officers/${encodeURIComponent(badgeId)}/assessment`, {
    method: 'POST',
  });
