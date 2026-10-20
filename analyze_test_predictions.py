import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import torch
import torch.nn as nn
from joblib import load
from scipy.signal import find_peaks
from scipy.stats import entropy

BASE = os.path.dirname(os.path.abspath(__file__))
TEST = os.path.join(BASE, 'data', 'test', 'combined_test.csv')
OUT = os.path.join(BASE, 'test_predictions')
os.makedirs(OUT, exist_ok=True)

PHYS = ['heart_rate','spo2','skin_temperature','accel_x','accel_y','accel_z','gyro_x','gyro_y','gyro_z','lat_delta','lon_delta','altitude','time_delta']

class WearableMLP(nn.Module):
    def __init__(self):
        super().__init__(); self.net = nn.Sequential(nn.Linear(13,256),nn.BatchNorm1d(256),nn.ReLU(),nn.Dropout(.3),nn.Linear(256,128),nn.BatchNorm1d(128),nn.ReLU(),nn.Dropout(.3),nn.Linear(128,64),nn.BatchNorm1d(64),nn.ReLU(),nn.Dropout(.3),nn.Linear(64,3))
    def forward(self,x): return self.net(x)
class DistractionNet(nn.Module):
    def __init__(self):
        super().__init__(); self.net = nn.Sequential(nn.Linear(7,64),nn.BatchNorm1d(64),nn.ReLU(),nn.Dropout(.3),nn.Linear(64,32),nn.BatchNorm1d(32),nn.ReLU(),nn.Dropout(.2),nn.Linear(32,1),nn.Sigmoid())
    def forward(self,x): return self.net(x).squeeze(1)

def wf(w):
    a=np.sqrt(w.accel_x**2+w.accel_y**2+w.accel_z**2); g=np.sqrt(w.gyro_x**2+w.gyro_y**2+w.gyro_z**2); d=np.sqrt(w.lat_delta**2+w.lon_delta**2)
    h,_=np.histogram(a,bins=10,density=True); h+=1e-8
    return [np.var(a),np.var(g),entropy(h),len(find_peaks(a)[0]),np.var(w.heart_rate),(w.heart_rate.iloc[-1]-w.heart_rate.iloc[0])/len(w),np.mean(d/(w.time_delta+1e-6))]

df=pd.read_csv(TEST); df['timestamp']=pd.to_datetime(df.timestamp); df=df.sort_values(['badge_id','timestamp']).reset_index(drop=True)
phys_scaler=load(os.path.join(BASE,'deployment','artifacts','physical_scaler.joblib')); dist_scaler=load(os.path.join(BASE,'deployment','artifacts','distraction_scaler.joblib'))
pm=WearableMLP(); pm.load_state_dict(torch.load(os.path.join(BASE,'best_models','model_1c_state_scratch.pt'),map_location='cpu')); pm.eval()
dm=DistractionNet(); dm.load_state_dict(torch.load(os.path.join(BASE,'best_models','model_2c_distraction_scratch.pt'),map_location='cpu')); dm.eval()
with torch.inference_mode():
    pp=torch.softmax(pm(torch.tensor(phys_scaler.transform(df[PHYS]),dtype=torch.float32)),1).numpy()
df['physical_prediction']=pp.argmax(1); df['physical_state']=df.physical_prediction.map({0:'STRESS',1:'PHYSICAL ACTIVITY',2:'NORMAL'}); df['physical_confidence']=pp.max(1)
df['stress_probability']=pp[:,0]; df['activity_probability']=pp[:,1]; df['normal_probability']=pp[:,2]

rows=[]
for badge,g in df.groupby('badge_id',sort=False):
    g=g.sort_values('timestamp').reset_index(drop=True)
    for start in range(0,max(0,len(g)-60),10):
        if len(g.iloc[start:start+60])<60: continue
        f=np.asarray(wf(g.iloc[start:start+60]),dtype=np.float32).reshape(1,-1)
        with torch.inference_mode(): p=float(dm(torch.tensor(dist_scaler.transform(f),dtype=torch.float32))[0])
        rows.append({'badge_id':badge,'officer_name':g.officer_name.iloc[0],'rank':g['rank'].iloc[0],'window_start':g.timestamp.iloc[start],'window_end':g.timestamp.iloc[start+59],'distraction_probability':p,'focus_prediction':'DISTRACTED' if p>=.5 else 'FOCUSED'})
win=pd.DataFrame(rows)
df.to_csv(os.path.join(OUT,'physical_state_predictions.csv'),index=False); win.to_csv(os.path.join(OUT,'focus_distraction_predictions.csv'),index=False)

ps=df.groupby(['badge_id','officer_name','rank']).agg(test_rows=('badge_id','size'),stress_pct=('physical_state',lambda x:(x=='STRESS').mean()*100),activity_pct=('physical_state',lambda x:(x=='PHYSICAL ACTIVITY').mean()*100),normal_pct=('physical_state',lambda x:(x=='NORMAL').mean()*100),mean_hr=('heart_rate','mean'),low_spo2_pct=('spo2',lambda x:(x<91).mean()*100),mean_confidence=('physical_confidence','mean')).reset_index()
if len(win):
    ws=win.groupby(['badge_id','officer_name','rank']).agg(distraction_windows=('focus_prediction','size'),distracted_pct=('focus_prediction',lambda x:(x=='DISTRACTED').mean()*100),mean_distraction_probability=('distraction_probability','mean')).reset_index(); ps=ps.merge(ws,on=['badge_id','officer_name','rank'],how='left')
else: ps['distraction_windows']=0; ps['distracted_pct']=np.nan; ps['mean_distraction_probability']=np.nan
ps.to_csv(os.path.join(OUT,'officer_summary.csv'),index=False)

plt.style.use('seaborn-v0_8-whitegrid')
order=ps.sort_values('test_rows',ascending=False)
fig,ax=plt.subplots(figsize=(12,7)); bottom=np.zeros(len(order)); colors=['#d95f02','#1b9e77','#7570b3']
for col,label,c in [('stress_pct','Stress',colors[0]),('activity_pct','Physical activity',colors[1]),('normal_pct','Normal',colors[2])]: ax.barh(order.officer_name,order[col],left=bottom,label=label,color=c); bottom+=order[col].to_numpy()
ax.set_xlabel('Share of test observations (%)'); ax.set_title('Predicted physical state by officer — chronological test set'); ax.legend(ncol=3,loc='lower right'); ax.invert_yaxis(); plt.tight_layout(); plt.savefig(os.path.join(OUT,'physical_state_by_officer.png'),dpi=180); plt.close()
if len(win):
    order=ps.sort_values('distracted_pct',ascending=False); fig,ax=plt.subplots(figsize=(12,7)); ax.barh(order.officer_name,order.distracted_pct,color='#c0392b'); ax.set_xlabel('Windows predicted distracted (%)'); ax.set_title('Predicted distraction exposure by officer'); ax.invert_yaxis(); plt.tight_layout(); plt.savefig(os.path.join(OUT,'distraction_by_officer.png'),dpi=180); plt.close()
fig,ax=plt.subplots(figsize=(10,5)); ax.bar(['Stress','Physical activity','Normal'],[ (df.physical_state=='STRESS').mean()*100,(df.physical_state=='PHYSICAL ACTIVITY').mean()*100,(df.physical_state=='NORMAL').mean()*100],color=colors); ax.set_ylabel('All test rows (%)'); ax.set_title('Overall physical-state prediction mix'); plt.tight_layout(); plt.savefig(os.path.join(OUT,'overall_state_mix.png'),dpi=180); plt.close()

top=ps.sort_values('test_rows',ascending=False).head(6)
lines=['# Test-Set Prediction Report','',f'Generated: 20 October 2026','', '## Scope', f'Two trained real-data models were applied to the chronological held-out test set: {len(df):,} telemetry rows from {df.badge_id.nunique()} officers, plus {len(win):,} non-overlapping-by-step 60-sample focus windows.', '', '## Model outputs', f"Physical state mix: Stress {(df.physical_state=='STRESS').mean()*100:.1f}%, Physical activity {(df.physical_state=='PHYSICAL ACTIVITY').mean()*100:.1f}%, Normal {(df.physical_state=='NORMAL').mean()*100:.1f}%.", f"Focus model: {((win.focus_prediction=='DISTRACTED').mean()*100 if len(win) else 0):.1f}% of windows predicted distracted.", '', '## Officer-level analysis', 'The complete officer-level table is in `officer_summary.csv`. The six officers with the largest test samples are listed below; all officers are included in the CSV.', '', '| Officer | Test rows | Stress % | Activity % | Normal % | Distracted windows % | Observation | Recommendation |','|---|---:|---:|---:|---:|---:|---|---|']
for _,r in top.iterrows():
    risk=max(r.stress_pct,r.distracted_pct if pd.notna(r.distracted_pct) else 0); obs=('Stress exposure is prominent' if r.stress_pct>=20 else 'Activity exposure is prominent' if r.activity_pct>=20 else 'Mostly normal predictions'); rec=('Review sustained high-HR stationary periods and add a supervisor check' if r.stress_pct>=20 else 'Review high-motion periods and verify duty context' if r.activity_pct>=20 else 'Continue routine monitoring; investigate only persistent changes')
    lines.append(f"| {r.officer_name} | {int(r.test_rows)} | {r.stress_pct:.1f} | {r.activity_pct:.1f} | {r.normal_pct:.1f} | {r.distracted_pct:.1f} | {obs} | {rec} |")
lines += ['', '## Observations and recommendations','- Treat model outputs as screening signals, not medical diagnoses or disciplinary evidence.','- Stress predictions are most useful when sustained across multiple readings and accompanied by elevated heart rate while movement is low.','- Physical-activity predictions are less reliable across different duty contexts; confirm against patrol, traffic, arrest, or training logs.','- Prioritize repeated distracted windows for fatigue/attention checks, hydration, rest, or supervisor review; do not act on a single isolated window.','- Because labels are heuristic and the physical-activity class has weaker historical F1 than the other classes, collect confirmed field annotations and recalibrate before operational escalation.', '', '## Figures','- `physical_state_by_officer.png`: compact officer comparison.','- `distraction_by_officer.png`: focus-risk comparison.','- `overall_state_mix.png`: overall prediction mix.']
open(os.path.join(OUT,'TEST_SET_REPORT.md'),'w',encoding='utf-8').write('\n'.join(lines))
print('Saved outputs to',OUT); print(ps.to_string(index=False))
