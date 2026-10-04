import { RawData, DerivedMetrics } from './data-logic';

export interface AIRecommendation {
  status: 'normal' | 'anomaly' | 'warning';
  message: string;
  recommendation: string;
}

/**
 * Service to interact with Groq API using Gemini models.
 * Pass specific data points to the model for context-aware health analysis.
 */
export async function getPoliceHealthInsights(
  apiKey: string,
  history: { raw: RawData, derived: DerivedMetrics }[]
): Promise<AIRecommendation> {
  const latest = history[history.length - 1];

  // Format history for context
  const contextData = history.slice(-5).map(h => ({
    hr: h.raw.heartRate.toFixed(1),
    spo2: h.raw.spo2.toFixed(1),
    load: h.derived.physicalLoad,
    stability: h.derived.stabilityScore
  }));

  const prompt = `
    Analyze this live health data for a police officer wearing an AI-enhanced watch:
    ${JSON.stringify(contextData)}

    Rules:
    1. Provide 100% genuine, non-exaggerated recommendations.
    2. Focus on health deviations (HR vs Load), SpO2 anomalies, or stability issues.
    3. If everything is normal, state it clearly and explain what the current stable graph indicates.
    4. Target Output: JSON format { "status": "...", "message": "...", "recommendation": "..." }
  `;

  try {
    const response = await fetch('https://api.groq.com/openai/v1/chat/completions', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${apiKey}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        model: 'llama-3.1-8b-instant', // High-performance, fast model available on Groq
        messages: [
          { role: 'system', content: 'You are a specialized medical AI analyzing police personnel health metrics. Return ONLY valid JSON.' },
          { role: 'user', content: prompt }
        ],
        response_format: { type: 'json_object' },
        temperature: 0.1
      })
    });

    const result = await response.json();
    console.log('Groq API Raw Result:', result);

    if (result.error) {
      throw new Error(result.error.message);
    }

    const content = result.choices[0].message.content;
    return JSON.parse(content);
  } catch (error) {
    console.error('AI Analysis Error:', error);
    return {
      status: 'normal',
      message: 'Self-monitoring active. API Connection pending.',
      recommendation: 'Check browser console for details. Ensure NEXT_PUBLIC_GROQ_API_KEY is valid.'
    };
  }
}
