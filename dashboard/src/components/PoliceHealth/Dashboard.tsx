'use client';

import React, { useState, useEffect } from 'react';
import { 
  LineChart, Line, AreaChart, Area, BarChart, Bar, 
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend
} from 'recharts';
import { Shield, Activity, Heart, Thermometer, Zap, AlertTriangle, CheckCircle, User, Badge, MapPin, Wifi } from 'lucide-react';
import { RawData, DerivedMetrics, generateRandomData, calculateDerivedMetrics } from '../../lib/police-health/data-logic';
import { getPoliceHealthInsights, AIRecommendation } from '../../lib/police-health/ai-service';

// Officer metadata type
interface OfficerMetadata {
  name: string;
  id: string;
  phone?: string;
  station?: string;
  authenticatedId?: string;
}

// Metric Card Component - Shows title, large number, unit, and trend
const MetricCard = ({ 
  title, 
  value, 
  unit, 
  icon: Icon, 
  color, 
  normal_range,
  isWarning = false
}: { 
  title: string
  value: number
  unit: string
  icon: any
  color: string
  normal_range: string
  isWarning?: boolean
}) => (
  <div className={`bg-gradient-to-br ${isWarning ? 'from-red-900/30 to-red-900/10' : 'from-slate-800/50 to-slate-900/50'} border ${isWarning ? 'border-red-500/50' : 'border-slate-700'} p-5 rounded-lg shadow-lg hover:shadow-xl transition-all`}>
    <div className="flex justify-between items-start mb-3">
      <div>
        <p className="text-slate-400 text-xs uppercase tracking-widest font-semibold">{title}</p>
        <p className="text-slate-500 text-xs mt-1">Range: {normal_range}</p>
      </div>
      <div className={`p-2 rounded-lg ${isWarning ? 'bg-red-500/20' : 'bg-slate-700/50'}`}>
        <Icon size={20} className={color} />
      </div>
    </div>
    <div className="flex items-baseline gap-2 mt-4">
      <span className={`text-4xl font-bold ${isWarning ? 'text-red-400' : 'text-slate-100'}`}>
        {value.toFixed(1)}
      </span>
      <span className="text-slate-400 text-lg font-semibold">{unit}</span>
    </div>
  </div>
);

// Chart Card with visible axis and labels
const ChartCard = ({ 
  title, 
  children, 
  icon: Icon, 
  color 
}: { 
  title: string
  children: React.ReactNode
  icon: any
  color: string 
}) => (
  <div className="bg-slate-800/40 border border-slate-700 p-5 rounded-lg shadow-lg">
    <div className="flex items-center gap-2 mb-4">
      <Icon size={18} className={color} />
      <h3 className="text-slate-200 font-semibold text-sm uppercase tracking-wider">{title}</h3>
    </div>
    <div className="h-56 w-full">
      {children}
    </div>
  </div>
);

// Officer Info Card at top
const OfficerCard = ({ officer }: { officer?: OfficerMetadata }) => (
  <div className="bg-gradient-to-r from-blue-900/40 to-blue-800/20 border border-blue-700/50 rounded-lg p-6 mb-6 shadow-lg">
    <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
      <div className="flex items-center gap-4">
        <div className="p-3 bg-blue-600/30 rounded-lg">
          <User size={28} className="text-blue-400" />
        </div>
        <div>
          <p className="text-slate-400 text-xs uppercase tracking-wider">Officer Name</p>
          <p className="text-xl font-bold text-white">{officer?.name || 'N/A'}</p>
        </div>
      </div>
      <div className="flex items-center gap-4">
        <div className="p-3 bg-blue-600/30 rounded-lg">
          <Badge size={28} className="text-blue-400" />
        </div>
        <div>
          <p className="text-slate-400 text-xs uppercase tracking-wider">Officer ID</p>
          <p className="text-xl font-bold text-white">{officer?.id || 'N/A'}</p>
        </div>
      </div>
      <div className="flex items-center gap-4">
        <div className="p-3 bg-blue-600/30 rounded-lg">
          <MapPin size={28} className="text-blue-400" />
        </div>
        <div>
          <p className="text-slate-400 text-xs uppercase tracking-wider">Station</p>
          <p className="text-xl font-bold text-white">{officer?.station || 'N/A'}</p>
        </div>
      </div>
      <div className="flex items-center gap-4">
        <div className="p-3 bg-emerald-600/30 rounded-lg">
          <Wifi size={28} className="text-emerald-400" />
        </div>
        <div>
          <p className="text-slate-400 text-xs uppercase tracking-wider">Status</p>
          <p className="text-xl font-bold text-emerald-400">Live Monitoring</p>
        </div>
      </div>
    </div>
  </div>
);

export default function PoliceHealthDashboard() {
  const [history, setHistory] = useState<{ raw: RawData; derived: DerivedMetrics }[]>([]);
  const [recommendation, setRecommendation] = useState<AIRecommendation | null>(null);
  const [isLoadingAI, setIsLoadingAI] = useState(false);
  const [officer, setOfficer] = useState<OfficerMetadata | undefined>();

  useEffect(() => {
    // Fetch initial data from API
    const fetchInitialData = async () => {
      try {
        const response = await fetch('http://localhost:8000/api/telemetry/history?limit=30');
        const data = await response.json();
        if (data.items) {
          setHistory(data.items.map((point: any) => ({
            raw: point.raw,
            derived: point.derived
          })));
        }
      } catch (err) {
        console.log('Using fallback data...');
        // Fallback to random data
        const initialData = Array.from({ length: 20 }).reduce((acc: any[]) => {
          const prev = acc.length > 0 ? acc[acc.length - 1].raw : undefined;
          const raw = generateRandomData(prev);
          const derived = calculateDerivedMetrics(raw);
          return [...acc, { raw, derived }];
        }, []);
        setHistory(initialData);
      }
    };

    // Set default officer info 
    setOfficer({
      name: 'Live Police Officer Monitoring',
      id: 'LIVE-FEED-001',
      station: 'Real-Time CSV Data Stream',
    });

    fetchInitialData();

    // Live update interval
    const interval = setInterval(async () => {
      try {
        const response = await fetch('http://localhost:8000/api/telemetry/current');
        const data = await response.json();
        setHistory(prev => {
          const updated = [...prev, {
            raw: data.raw,
            derived: data.derived
          }];
          return updated.slice(-30);
        });
      } catch (err) {
        console.log('Failed to fetch from API, using generated data');
        setHistory(prev => {
          const last = prev[prev.length - 1].raw;
          const raw = generateRandomData(last);
          const derived = calculateDerivedMetrics(raw);
          return [...prev.slice(-29), { raw, derived }];
        });
      }
    }, 2000);

    return () => clearInterval(interval);
  }, []);

  const refreshAI = async () => {
    const apiKey = process.env.NEXT_PUBLIC_GROQ_API_KEY;
    if (!apiKey || history.length < 5) return;
    
    setIsLoadingAI(true);
    try {
      const insights = await getPoliceHealthInsights(apiKey, history as any);
      setRecommendation(insights);
    } catch (err) {
      console.error('AI Refresh failed:', err);
    } finally {
      setIsLoadingAI(false);
    }
  };

  useEffect(() => {
    if (history.length >= 5 && !recommendation && !isLoadingAI) {
      refreshAI();
    }
  }, [history.length]);

  useEffect(() => {
    const aiInterval = setInterval(refreshAI, 35000);
    return () => clearInterval(aiInterval);
  }, []);

  const latest = history[history.length - 1];

  // Check for warnings
  const isHeartRateWarning = latest?.raw.heartRate ? latest.raw.heartRate > 120 || latest.raw.heartRate < 60 : false;
  const isSpo2Warning = latest?.raw.spo2 ? latest.raw.spo2 < 90 : false;
  const isTempWarning = latest?.raw.temp ? latest.raw.temp > 38.5 || latest.raw.temp < 36.2 : false;

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-950 via-blue-950 to-slate-900 text-slate-100 p-8 font-sans">
      {/* Header */}
      <header className="mb-8">
        <div className="flex justify-between items-start mb-6">
          <div className="flex items-center gap-4">
            <div className="bg-gradient-to-br from-blue-600 to-blue-700 p-3 rounded-lg shadow-[0_0_20px_rgba(37,99,235,0.6)]">
              <Shield size={32} className="text-white" />
            </div>
            <div>
              <h1 className="text-4xl font-bold tracking-tight">Police Personnel Health Grid</h1>
              <p className="text-slate-300 text-sm uppercase tracking-[0.15em] font-medium">Real-Time Biometric Monitoring System</p>
            </div>
          </div>
          <div className="flex gap-3">
            <StatusPill label="CSV Data" status="active" />
            <StatusPill label="API Active" status="active" />
            <StatusPill label="AI Analysis" status={isLoadingAI ? 'loading' : 'active'} />
          </div>
        </div>
      </header>

      {/* Officer Information Card */}
      {officer && <OfficerCard officer={officer} />}

      {/* Key Metrics - Large Display */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
        <MetricCard 
          title="Heart Rate"
          value={latest?.raw.heartRate || 0}
          unit="BPM"
          icon={Heart}
          color="text-rose-400"
          normal_range="60-100"
          isWarning={isHeartRateWarning}
        />
        <MetricCard 
          title="Oxygen Saturation"
          value={latest?.raw.spo2 || 0}
          unit="%"
          icon={Activity}
          color="text-cyan-400"
          normal_range="95-100"
          isWarning={isSpo2Warning}
        />
        <MetricCard 
          title="Body Temperature"
          value={latest?.raw.temp || 0}
          unit="°C"
          icon={Thermometer}
          color="text-amber-400"
          normal_range="36.5-37.5"
          isWarning={isTempWarning}
        />
        <MetricCard 
          title="Stability Index"
          value={latest?.derived.stabilityScore || 0}
          unit="/ 100"
          icon={Shield}
          color="text-emerald-400"
          normal_range="60-100"
          isWarning={false}
        />
      </div>

      {/* Charts Section */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
        {/* Heart Rate Chart */}
        <ChartCard title="Heart Rate Trend (Last 30 readings)" icon={Heart} color="text-rose-400">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={history} margin={{ top: 5, right: 10, left: -20, bottom: 5 }}>
              <defs>
                <linearGradient id="colorHR" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#f43f5e" stopOpacity={0.4}/>
                  <stop offset="95%" stopColor="#f43f5e" stopOpacity={0}/>
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis stroke="#94a3b8" style={{ fontSize: '12px' }} />
              <YAxis stroke="#94a3b8" style={{ fontSize: '12px' }} domain={[50, 150]} />
              <Tooltip 
                contentStyle={{
                  backgroundColor: '#1e293b',
                  border: '1px solid #475569',
                  borderRadius: '8px',
                  color: '#f1f5f9'
                }}
                formatter={(value: any) => value ? `${Number(value).toFixed(1)} BPM` : 'N/A'}
              />
              <Area type="monotone" dataKey="raw.heartRate" stroke="#f43f5e" fillOpacity={1} fill="url(#colorHR)" />
            </AreaChart>
          </ResponsiveContainer>
        </ChartCard>

        {/* SpO2 Chart */}
        <ChartCard title="Oxygen Level Trend (Last 30 readings)" icon={Activity} color="text-cyan-400">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={history} margin={{ top: 5, right: 10, left: -20, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis stroke="#94a3b8" style={{ fontSize: '12px' }} />
              <YAxis stroke="#94a3b8" style={{ fontSize: '12px' }} domain={[85, 100]} />
              <Tooltip 
                contentStyle={{
                  backgroundColor: '#1e293b',
                  border: '1px solid #475569',
                  borderRadius: '8px',
                  color: '#f1f5f9'
                }}
                formatter={(value: any) => value ? `${Number(value).toFixed(1)} %` : 'N/A'}
              />
              <Line type="linear" dataKey="raw.spo2" stroke="#22d3ee" strokeWidth={3} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </ChartCard>

        {/* Temperature Chart */}
        <ChartCard title="Body Temperature Trend (Last 30 readings)" icon={Thermometer} color="text-amber-400">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={history} margin={{ top: 5, right: 10, left: -20, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis stroke="#94a3b8" style={{ fontSize: '12px' }} />
              <YAxis stroke="#94a3b8" style={{ fontSize: '12px' }} domain={[35, 40]} />
              <Tooltip 
                contentStyle={{
                  backgroundColor: '#1e293b',
                  border: '1px solid #475569',
                  borderRadius: '8px',
                  color: '#f1f5f9'
                }}
                formatter={(value: any) => value ? `${Number(value).toFixed(1)} °C` : 'N/A'}
              />
              <Area type="monotone" dataKey="raw.temp" stroke="#fbbf24" fill="#fbbf2433" />
            </AreaChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      {/* Detailed Metrics */}
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6 mb-8">
        {/* Physical Activity */}
        <ChartCard title="Physical Load (Acceleration)" icon={Zap} color="text-orange-500">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={history} margin={{ top: 5, right: 10, left: -20, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis stroke="#94a3b8" style={{ fontSize: '11px' }} />
              <YAxis stroke="#94a3b8" style={{ fontSize: '11px' }} />
              <Tooltip 
                contentStyle={{
                  backgroundColor: '#1e293b',
                  border: '1px solid #475569',
                  borderRadius: '8px',
                  color: '#f1f5f9'
                }}
                formatter={(value: any) => value ? `${Number(value).toFixed(2)} g` : 'N/A'}
              />
              <Area type="monotone" dataKey="derived.physicalLoad" stroke="#f97316" fill="#f9731633" />
            </AreaChart>
          </ResponsiveContainer>
        </ChartCard>

        {/* Metabolic Strain */}
        <ChartCard title="Metabolic Strain Index" icon={Activity} color="text-red-500">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={history.slice(-15)} margin={{ top: 5, right: 10, left: -20, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis stroke="#94a3b8" style={{ fontSize: '11px' }} />
              <YAxis stroke="#94a3b8" style={{ fontSize: '11px' }} />
              <Tooltip 
                contentStyle={{
                  backgroundColor: '#1e293b',
                  border: '1px solid #475569',
                  borderRadius: '8px',
                  color: '#f1f5f9'
                }}
                formatter={(value: any) => value ? `${Number(value).toFixed(2)}` : 'N/A'}
              />
              <Bar dataKey="derived.metabolicStrain" fill="#ef4444" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        {/* Stability */}
        <ChartCard title="Movement Stability Index" icon={Shield} color="text-blue-400">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={history} margin={{ top: 5, right: 10, left: -20, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis stroke="#94a3b8" style={{ fontSize: '11px' }} />
              <YAxis stroke="#94a3b8" style={{ fontSize: '11px' }} domain={[0, 100]} />
              <Tooltip 
                contentStyle={{
                  backgroundColor: '#1e293b',
                  border: '1px solid #475569',
                  borderRadius: '8px',
                  color: '#f1f5f9'
                }}
                formatter={(value: any) => value ? `${Number(value).toFixed(1)} / 100` : 'N/A'}
              />
              <Area type="monotone" dataKey="derived.stabilityScore" stroke="#60a5fa" fill="#60a5fa22" />
            </AreaChart>
          </ResponsiveContainer>
        </ChartCard>

        {/* Rotational Stress */}
        <ChartCard title="Rotational Stress (Gyroscope)" icon={Zap} color="text-emerald-400">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={history} margin={{ top: 5, right: 10, left: -20, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis stroke="#94a3b8" style={{ fontSize: '11px' }} />
              <YAxis stroke="#94a3b8" style={{ fontSize: '11px' }} />
              <Tooltip 
                contentStyle={{
                  backgroundColor: '#1e293b',
                  border: '1px solid #475569',
                  borderRadius: '8px',
                  color: '#f1f5f9'
                }}
                formatter={(value: any) => value ? `${Number(value).toFixed(2)} deg/s` : 'N/A'}
              />
              <Line type="basis" dataKey="derived.rotationalStress" stroke="#34d399" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      {/* AI Recommendations Panel */}
      <div className="bg-gradient-to-br from-blue-900/30 to-blue-900/10 border border-blue-700/50 rounded-lg p-6 shadow-lg">
        <div className="flex items-center gap-3 mb-4">
          <div className="p-3 bg-blue-600/30 rounded-lg">
            <Activity className="text-blue-400" size={24} />
          </div>
          <h2 className="text-2xl font-bold">AI Health Analysis</h2>
        </div>

        {recommendation ? (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className={`p-5 rounded-lg border ${
              recommendation.status === 'anomaly' ? 'bg-red-500/20 border-red-500/50' : 
              recommendation.status === 'warning' ? 'bg-amber-500/20 border-amber-500/50' : 
              'bg-emerald-500/20 border-emerald-500/50'
            }`}>
              <div className="flex items-center gap-2 mb-3">
                {recommendation.status === 'normal' ? <CheckCircle size={20} className="text-emerald-400" /> : <AlertTriangle size={20} className="text-amber-400" />}
                <span className="text-sm font-bold uppercase tracking-wider">Status: {recommendation.status}</span>
              </div>
              <p className="text-base font-medium text-slate-100">{recommendation.message}</p>
            </div>

            <div className="bg-slate-800/40 border border-slate-700 p-5 rounded-lg md:col-span-2">
              <h4 className="text-xs font-bold text-slate-400 uppercase tracking-widest mb-3">Recommendation</h4>
              <p className="text-sm text-slate-200 leading-relaxed italic">
                "{recommendation.recommendation}"
              </p>
            </div>
          </div>
        ) : (
          <div className="flex items-center justify-center p-12">
            <div className="text-center">
              <div className="w-12 h-12 border-4 border-blue-500/30 border-t-blue-500 rounded-full animate-spin mx-auto mb-4" />
              <p className="text-slate-400">Analyzing biometric patterns...</p>
            </div>
          </div>
        )}

        <button 
          onClick={refreshAI} 
          disabled={isLoadingAI}
          className="mt-6 px-6 py-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white rounded-lg font-semibold text-sm shadow-[0_0_15px_rgba(37,99,235,0.3)] transition-all active:scale-95"
        >
          {isLoadingAI ? 'Analyzing...' : 'Manual Analysis'}
        </button>
      </div>
    </div>
  );
}

function StatusPill({ label, status }: { label: string, status: 'active' | 'loading' | 'offline' }) {
  return (
    <div className="bg-slate-800/60 px-4 py-2 rounded-full border border-slate-700 flex items-center gap-2 shadow-lg">
      <div className={`w-2 h-2 rounded-full ${status === 'loading' ? 'bg-blue-400 animate-pulse' : 'bg-emerald-500'}`} />
      <span className="text-xs font-semibold uppercase tracking-wider text-slate-300">{label}</span>
    </div>
  );
}
