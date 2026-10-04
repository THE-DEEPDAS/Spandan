/**
 * Utility for calculating derived health and physical metrics from raw sensor data.
 */

export interface RawData {
  heartRate: number;
  spo2: number;
  temp: number;
  accel: { x: number; y: number; z: number };
  gyro: { x: number; y: number; z: number };
}

export interface DerivedMetrics {
  physicalLoad: number;    // Resultant of acceleration
  rotationalStress: number; // Resultant of gyro
  metabolicStrain: number;  // Combined HR and Temp intensity
  stabilityScore: number;   // Variance-based measure
}

export const calculateDerivedMetrics = (raw: RawData): DerivedMetrics => {
  // Physical Load: Standard magnitude of acceleration vector (G-force approximation)
  const accelMag = Math.sqrt(raw.accel.x ** 2 + raw.accel.y ** 2 + raw.accel.z ** 2);
  
  // Rotational Stress: Magnitude of angular velocity
  const gyroMag = Math.sqrt(raw.gyro.x ** 2 + raw.gyro.y ** 2 + raw.gyro.z ** 2);
  
  // Metabolic Strain: Simplified index (HR weighted + Temperature deviation)
  // Base HR ~70, Base Temp ~37
  const hrComponent = (raw.heartRate - 70) / 100;
  const tempComponent = (raw.temp - 37) / 2;
  const metabolicStrain = Math.max(0, (hrComponent * 0.7 + tempComponent * 0.3) * 10);

  // Stability Score: High stability (100) means low erratic movement
  // Note: For a real app, this would use a sliding window variance. 
  // Here we use current magnitude as a proxy for "instability".
  const stability = Math.max(0, 100 - (accelMag * 5 + gyroMag * 2));

  return {
    physicalLoad: Number(accelMag.toFixed(2)),
    rotationalStress: Number(gyroMag.toFixed(2)),
    metabolicStrain: Number(metabolicStrain.toFixed(2)),
    stabilityScore: Number(stability.toFixed(2))
  };
};

export const generateRandomData = (prev?: RawData): RawData => {
  const drift = (val: number, range: number) => val + (Math.random() - 0.5) * range;
  
  // Chance of anomaly (approx once every 50-100 updates)
  const isAnomaly = Math.random() < 0.05;
  const anomalyType = Math.floor(Math.random() * 3);

  let hr = drift(prev?.heartRate || 75, 5);
  let spo2 = drift(prev?.spo2 || 98.5, 0.5);
  let temp = drift(prev?.temp || 36.8, 0.2);

  if (isAnomaly) {
    if (anomalyType === 0) hr += 40; // Tachycardia burst
    if (anomalyType === 1) spo2 -= 4; // Hypoxia dip
    if (anomalyType === 2) hr += 20; temp += 1.5; // Fever / Heat stress
  }

  return {
    heartRate: Math.max(60, Math.min(180, hr)),
    spo2: Math.max(85, Math.min(100, spo2)),
    temp: Math.max(36, Math.min(40, temp)),
    accel: {
      x: (Math.random() - 0.5) * 2,
      y: (Math.random() - 0.5) * 2,
      z: 9.8 + (Math.random() - 0.5) * 1 
    },
    gyro: {
      x: (Math.random() - 0.5) * 0.5,
      y: (Math.random() - 0.5) * 0.5,
      z: (Math.random() - 0.5) * 0.5
    }
  };
};
