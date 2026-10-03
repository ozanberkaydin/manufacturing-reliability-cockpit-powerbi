"""Prepare the Microsoft simulated maintenance sample without inventing records."""
from pathlib import Path
import argparse
import hashlib
import json
import urllib.request
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'data/raw'
OUT = ROOT / 'data/processed'
QA = ROOT / 'validation'
BASE = ('https://raw.githubusercontent.com/microsoft/sqlworkshops/master/'
        'SQLServerAndAzureMachineLearning/ML%20Services%20for%20SQL%20Server/data/')
NAMES = ['machines', 'telemetry', 'errors', 'maint', 'failures']
SENSORS = {'volt': 'Voltage', 'rotate': 'Rotation', 'pressure': 'Pressure', 'vibration': 'Vibration'}

def acquire():
    RAW.mkdir(parents=True, exist_ok=True)
    for name in NAMES:
        path = RAW / f'PdM_{name}.csv'
        if not path.exists():
            urllib.request.urlretrieve(BASE + path.name, path)
    license_path = ROOT / 'docs/MICROSOFT_SAMPLE_LICENSE.txt'
    license_path.parent.mkdir(parents=True, exist_ok=True)
    if not license_path.exists():
        urllib.request.urlretrieve('https://raw.githubusercontent.com/microsoft/sqlworkshops/master/LICENSE', license_path)

def save(df, name):
    df.to_csv(OUT / f'{name}.csv', index=False, date_format='%Y-%m-%d %H:%M:%S', float_format='%.6f')

def features(daily, errors, failures, maintenance):
    """End-of-day snapshots; rolling references exclude the current observation."""
    daily = daily.sort_values(['Machine ID', 'Date']).copy()
    sensor_rows = []
    for sensor in SENSORS.values():
        grouped = daily.groupby('Machine ID')[sensor]
        reference = grouped.transform(lambda s: s.shift(1).rolling(30, min_periods=7).mean())
        spread = grouped.transform(lambda s: s.shift(1).rolling(30, min_periods=7).std(ddof=1))
        z = (daily[sensor] - reference) / spread.where(spread > 1e-8)
        daily[sensor + ' Z'] = z
        sensor_rows.append(pd.DataFrame({
            'Machine ID': daily['Machine ID'], 'Date': daily['Date'], 'Sensor': sensor,
            'Mean Reading': daily[sensor], 'Prior Mean': reference, 'Prior Std': spread,
            'Deviation Z': z, 'Reading Count': daily['Reading Count'],
            'Unit': 'sample units (not specified by source)'}))
    sensor_daily = pd.concat(sensor_rows, ignore_index=True)
    index = pd.MultiIndex.from_frame(daily[['Machine ID', 'Date']])
    for events, label, window in [(failures, 'Failures 14 Days', 14), (errors, 'Errors 7 Days', 7)]:
        counts = events.groupby(['Machine ID', 'Date']).size().reindex(index, fill_value=0)
        frame = counts.rename('Count').reset_index()
        daily[label] = frame.groupby('Machine ID')['Count'].transform(lambda s: s.rolling(window, min_periods=1).sum()).to_numpy().astype(int)
    # All four components are tracked separately. A replacement of one must not reset another.
    for comp in ['comp1', 'comp2', 'comp3', 'comp4']:
        ages = []
        for machine, group in daily.groupby('Machine ID', sort=False):
            hist = maintenance.loc[(maintenance['Machine ID'] == machine) & (maintenance['Component'] == comp), 'Timestamp'].sort_values().to_numpy()
            cutoffs = (group['Date'] + pd.Timedelta(days=1)).to_numpy()
            pos = np.searchsorted(hist, cutoffs, side='left') - 1
            last = np.full(len(group), np.datetime64('NaT'), dtype='datetime64[ns]')
            valid = pos >= 0
            last[valid] = hist[pos[valid]]
            # Calendar recency: same-day replacement has age zero at the daily grain.
            ages.extend((group['Date'].to_numpy() - last.astype('datetime64[D]')) / np.timedelta64(1, 'D'))
        daily[comp + ' Days Since Replacement'] = ages
    recency_cols = [c + ' Days Since Replacement' for c in ['comp1', 'comp2', 'comp3', 'comp4']]
    daily['Components With History'] = daily[recency_cols].notna().sum(axis=1)
    daily['Oldest Component Days'] = daily[recency_cols].max(axis=1)
    daily['Sensor Deviation Max'] = daily[[s + ' Z' for s in SENSORS.values()]].abs().max(axis=1)
    daily['Baseline Sensors'] = daily[[s + ' Z' for s in SENSORS.values()]].notna().sum(axis=1)
    daily['Failure Points'] = (daily['Failures 14 Days'] * 20).clip(upper=40)
    daily['Error Points'] = (daily['Errors 7 Days'] * 3).clip(upper=15)
    daily['Sensor Points'] = (daily['Sensor Deviation Max'].fillna(0) - 2).clip(lower=0, upper=2) * 15
    daily['Maintenance Points'] = np.select([daily['Oldest Component Days'] >= 90, daily['Oldest Component Days'] >= 60], [15, 8], default=0)
    daily['Priority Score'] = (daily['Failure Points'] + daily['Error Points'] + daily['Sensor Points'] + daily['Maintenance Points']).round(1)
    daily['Priority Band'] = np.select([daily['Priority Score'] >= 60, daily['Priority Score'] >= 30], ['High - inspect', 'Watch - review'], default='Routine - monitor')
    def reason(row):
        z = 'baseline pending' if pd.isna(row['Sensor Deviation Max']) else f"max |z| {row['Sensor Deviation Max']:.1f}"
        rec = 'no known component history' if pd.isna(row['Oldest Component Days']) else f"oldest component {row['Oldest Component Days']:.0f}d"
        return f"{row['Failures 14 Days']} failures /14d; {row['Errors 7 Days']} errors /7d; {z}; {rec}"
    daily['Priority Reasons'] = daily.apply(reason, axis=1)
    daily['Suggested Inspection'] = np.select([daily['Failure Points'] > 0, daily['Sensor Points'] > 0, daily['Maintenance Points'] > 0, daily['Error Points'] > 0],
        ['Review replaced components and recurring failure modes', 'Inspect sensors and compare with prior operating conditions', 'Review component replacement schedule', 'Review recent error log and inspect affected systems'], default='Continue routine observation')
    daily['As Of Timestamp'] = daily['Latest Timestamp']
    daily['Telemetry Completeness'] = daily['Reading Count'] / 24
    return daily, sensor_daily

def run():
    acquire()
    OUT.mkdir(parents=True, exist_ok=True)
    QA.mkdir(parents=True, exist_ok=True)
    data, audit = {}, {}
    expected = {'machines': ['machineID', 'model', 'age'], 'telemetry': ['datetime', 'machineID', *SENSORS],
                'errors': ['datetime', 'machineID', 'errorID'], 'maint': ['datetime', 'machineID', 'comp'], 'failures': ['datetime', 'machineID', 'failure']}
    for name in NAMES:
        path = RAW / f'PdM_{name}.csv'
        df = pd.read_csv(path)
        assert list(df.columns) == expected[name], f'Unexpected schema: {name}'
        missing = df.isna().sum().to_dict()
        assert not any(missing.values()), f'Missing required values: {name}'
        assert pd.api.types.is_integer_dtype(df.machineID), f'Invalid machine key: {name}'
        duplicates = int(df.duplicated().sum())
        # Exact duplicates in event logs cannot be adjudicated without source event IDs.
        # Fail rather than silently collapse or double-count them.
        assert duplicates == 0, f'Unresolved exact duplicates: {name}'
        if 'datetime' in df:
            df['datetime'] = pd.to_datetime(df.datetime, format='%Y-%m-%d %H:%M:%S', errors='raise')
            assert (df.datetime.dt.minute == 0).all() and (df.datetime.dt.second == 0).all()
        audit[name] = {'rows': len(df), 'missing': missing, 'exact_duplicates': duplicates,
                       'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'source': BASE + path.name}
        if 'datetime' in df:
            audit[name].update(min_timestamp=str(df.datetime.min()), max_timestamp=str(df.datetime.max()),
                simultaneous_extra_records=int(df.duplicated(['machineID', 'datetime']).sum()))
        data[name] = df
    machines = data['machines']
    assert machines.machineID.is_unique and (machines.age >= 0).all()
    assert set(machines.model) == {'model1', 'model2', 'model3', 'model4'}
    for name, df in data.items():
        assert df.machineID.isin(machines.machineID).all(), f'Orphan keys: {name}'
    telemetry = data['telemetry'].sort_values(['machineID', 'datetime'])
    assert not telemetry.duplicated(['machineID', 'datetime']).any()
    assert np.isfinite(telemetry[list(SENSORS)].to_numpy()).all()
    gaps = telemetry.groupby('machineID').datetime.diff().dropna()
    audit['telemetry']['non_hourly_gaps'] = int((gaps != pd.Timedelta(hours=1)).sum())
    assert (gaps == pd.Timedelta(hours=1)).all(), 'Unexpected telemetry gaps'
    for n, col, values in [('errors', 'errorID', [f'error{i}' for i in range(1, 6)]), ('maint', 'comp', [f'comp{i}' for i in range(1, 5)]), ('failures', 'failure', [f'comp{i}' for i in range(1, 5)])]:
        assert data[n][col].isin(values).all()
    machines = machines.rename(columns={'machineID': 'Machine ID', 'model': 'Model', 'age': 'Age Years'})
    machines['Machine'] = machines['Machine ID'].map(lambda i: f'Machine {i:03}')
    machines['Age Band'] = pd.cut(machines['Age Years'], [-1, 5, 10, 15, 100], labels=['00-05 years', '06-10 years', '11-15 years', '16+ years']).astype(str)
    save(machines, 'machines')
    cleaned = {}
    for name in ['telemetry', 'errors', 'maint', 'failures']:
        d = data[name].rename(columns={'datetime': 'Timestamp', 'machineID': 'Machine ID', 'errorID': 'Error', 'comp': 'Component', 'failure': 'Component', **SENSORS}).copy()
        d['Date'] = d.Timestamp.dt.normalize()
        cleaned[name] = d.sort_values(['Machine ID', 'Timestamp'])
        save(cleaned[name], 'maintenance' if name == 'maint' else name)
    joined = cleaned['failures'].merge(cleaned['maint'], on=['Machine ID', 'Timestamp', 'Component'], how='left', indicator=True)
    audit['failures']['failure_without_matching_replacement'] = int((joined['_merge'] == 'left_only').sum())
    assert len(joined) == len(cleaned['failures'])
    tele = cleaned['telemetry']
    agg = {s: (s, 'mean') for s in SENSORS.values()}
    agg.update({'Reading Count': ('Timestamp', 'size'), 'Latest Timestamp': ('Timestamp', 'max')})
    daily = tele.groupby(['Machine ID', 'Date']).agg(**agg).reset_index()
    daily, sensor_daily = features(daily, cleaned['errors'], cleaned['failures'], cleaned['maint'])
    assert daily['Priority Score'].between(0, 100).all()
    # Recompute a prefix to prove snapshots are unaffected by later observations/events.
    cutoff = pd.Timestamp('2015-06-30')
    prefix, prefix_sensors = features(daily.loc[daily.Date <= cutoff, ['Machine ID', 'Date', *SENSORS.values(), 'Reading Count', 'Latest Timestamp']],
        cleaned['errors'].loc[cleaned['errors'].Date <= cutoff], cleaned['failures'].loc[cleaned['failures'].Date <= cutoff], cleaned['maint'].loc[cleaned['maint'].Date <= cutoff])
    pd.testing.assert_frame_equal(prefix[['Machine ID', 'Date', 'Priority Score', 'Priority Reasons']].reset_index(drop=True), daily.loc[daily.Date <= cutoff, ['Machine ID', 'Date', 'Priority Score', 'Priority Reasons']].reset_index(drop=True))
    save(daily, 'daily_health'); save(sensor_daily, 'sensor_daily')
    dates = pd.DataFrame({'Date': pd.date_range(cleaned['maint'].Date.min(), max(tele.Date.max(), cleaned['maint'].Date.max()))})
    dates['Year'] = dates.Date.dt.year
    dates['Month'] = dates.Date.dt.strftime('%Y-%m')
    dates['Month Number'] = dates.Date.dt.month
    dates['Quarter'] = dates.Date.dt.to_period('Q').astype(str)
    dates['In Telemetry Period'] = dates.Date.between(tele.Date.min(), tele.Date.max()).astype(int)
    save(dates, 'dates')
    save(pd.DataFrame({'Component': [f'comp{i}' for i in range(1, 5)]}), 'components')
    save(pd.DataFrame({'Sensor': list(SENSORS.values()), 'Unit': ['sample units (unspecified)'] * 4}), 'sensors')
    # Event-relative windows use individual component failure records, not deduplicated machines.
    windows = []
    for event_id, row in cleaned['failures'].reset_index(drop=True).iterrows():
        segment = tele.loc[(tele['Machine ID'] == row['Machine ID']) & tele.Timestamp.between(row.Timestamp - pd.Timedelta(hours=72), row.Timestamp + pd.Timedelta(hours=72))].copy()
        segment['Relative Day'] = np.floor((segment.Timestamp - row.Timestamp).dt.total_seconds() / 86400).astype(int)
        for offset, g in segment.groupby('Relative Day'):
            if offset == 3: continue  # avoid a one-hour +72h endpoint bin
            for s in SENSORS.values():
                windows.append({'Event ID': event_id + 1, 'Machine ID': row['Machine ID'], 'Date': row.Date, 'Component': row.Component,
                    'Relative Day': offset, 'Sensor': s, 'Mean Reading': g[s].mean(), 'Sample Hours': len(g), 'Complete Bin': int(len(g) == 24)})
    windows = pd.DataFrame(windows); save(windows, 'failure_windows')
    intervals = cleaned['failures'][['Machine ID', 'Timestamp', 'Date']].drop_duplicates(['Machine ID', 'Timestamp']).sort_values(['Machine ID', 'Timestamp'])
    intervals['Previous Failure'] = intervals.groupby('Machine ID').Timestamp.shift(1)
    intervals['Gap Hours'] = (intervals.Timestamp - intervals['Previous Failure']).dt.total_seconds() / 3600
    intervals = intervals.dropna(); save(intervals, 'failure_intervals')
    summary = {'machines': len(machines), 'telemetry_hours': len(tele), 'failure_events': len(cleaned['failures']),
        'machines_with_failure': int(cleaned['failures']['Machine ID'].nunique()), 'error_events': len(cleaned['errors']),
        'replacement_records': len(cleaned['maint']), 'daily_rows': len(daily), 'sensor_daily_rows': len(sensor_daily),
        'failure_events_per_1000_observed_hours': len(cleaned['failures']) / len(tele) * 1000,
        'mean_completed_gap_hours': float(intervals['Gap Hours'].mean()), 'completed_gap_count': len(intervals),
        'priority_score_min': float(daily['Priority Score'].min()), 'priority_score_max': float(daily['Priority Score'].max()),
        'prefix_invariance': 'passed at 2015-06-30', 'telemetry_start': str(tele.Timestamp.min()), 'telemetry_end': str(tele.Timestamp.max())}
    slices = []
    for machine, start, end in [(1, '2015-01-01', '2015-01-31'), (42, '2015-04-01', '2015-06-30'), (None, '2015-07-01', '2015-07-31')]:
        f = cleaned['failures']; e = cleaned['errors']; t = daily
        def scope(d):return d.Date.between(pd.Timestamp(start), pd.Timestamp(end)) & (True if machine is None else d['Machine ID'].eq(machine))
        slices.append({'machine': machine, 'start': start, 'end': end, 'failures': int(scope(f).sum()), 'errors': int(scope(e).sum()), 'hours': int(t.loc[scope(t), 'Reading Count'].sum())})
    summary['filter_expectations'] = slices
    summary['failures_by_component'] = cleaned['failures'].groupby('Component').size().to_dict()
    summary['failures_by_model'] = cleaned['failures'].merge(machines, on='Machine ID').groupby('Model').size().to_dict()
    latest = daily.loc[daily.Date == pd.Timestamp('2015-12-31')].sort_values(['Priority Score', 'Machine ID'], ascending=[False, True])
    summary['priority_top_10_at_2015_12_31'] = latest[['Machine ID', 'Priority Score', 'Priority Reasons']].head(10).to_dict('records')
    (QA / 'python_expected.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    report = {'status': 'passed', 'sources': audit, 'checks': ['Exact schemas', 'No required nulls', 'No unresolved duplicates', 'Valid integer keys', 'No orphan machines', 'Hour-aligned timestamps', 'Contiguous hourly telemetry', 'Simultaneous records preserved', 'Failure/replacement matching audited', 'Score range 0-100', 'Future-data prefix invariance'], 'summary': summary}
    (QA / 'data_quality.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(summary, indent=2))

if __name__ == '__main__':
    run()
