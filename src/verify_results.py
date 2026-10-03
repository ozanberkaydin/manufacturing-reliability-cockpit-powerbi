"""Compare retained live MCP results with independently prepared Python outputs."""
from pathlib import Path
import json
import math
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
def main():
    expected = json.loads((ROOT/'validation/python_expected.json').read_text())
    cases = {c['case']: c['rows'] for c in json.loads((ROOT/'validation/live_dax_results.json').read_text())}
    full = cases['full'][0]
    mapping = {'Failures':'failure_events','Machines':'machines_with_failure','Errors':'error_events','Replacements':'replacement_records','Hours':'telemetry_hours','GapCount':'completed_gap_count','Rate':'failure_events_per_1000_observed_hours','MeanGap':'mean_completed_gap_hours'}
    for name,key in mapping.items():
        assert math.isclose(full['['+name+']'],expected[key],abs_tol=0.0001), name
    for e in expected['filter_expectations']:
        row = cases['filter'+str(e['machine']).lower().replace('none','null')][0]
        for name,key in [('Failures','failures'),('Errors','errors'),('Hours','hours')]:assert row['['+name+']']==e[key]
    actual = {r['Machines[Machine ID]']:r for r in cases['priority']}
    scores = sorted({r['Priority Score'] for r in expected['priority_top_10_at_2015_12_31']},reverse=True)
    for r in expected['priority_top_10_at_2015_12_31']:
        a=actual[r['Machine ID']]
        assert a['[Score]']==r['Priority Score'] and a['[Reasons]']==r['Priority Reasons']
        assert a['[Rank]']==scores.index(r['Priority Score'])+1
    data=ROOT/'data/processed'
    daily=pd.read_csv(data/'daily_health.csv')
    daily['Date']=pd.to_datetime(daily['Date']).dt.strftime('%Y-%m-%d')
    sel=daily[daily['Date'].between('2015-01-01','2015-12-31')]
    assert cases['2015'][0]['[Hours]']==int(sel['Reading Count'].sum())
    for filename,col in [('failures','Failures'),('errors','Errors'),('maintenance','Replacements')]:
        df=pd.read_csv(data/(filename+'.csv'))
        df['Date']=pd.to_datetime(df['Date']).dt.strftime('%Y-%m-%d')
        assert cases['2015'][0]['['+col+']']==int(df['Date'].between('2015-01-01','2015-12-31').sum())
    sensors=pd.read_csv(data/'sensor_daily.csv')
    sensors['Date']=pd.to_datetime(sensors['Date']).dt.strftime('%Y-%m-%d')
    row=sensors[(sensors['Machine ID']==88)&(sensors['Date']=='2015-12-31')&(sensors['Sensor']=='Voltage')].iloc[0]
    actual_measures=cases['all_41_measures'][0]
    for name,col in [('Sensor Daily Mean','Mean Reading'),('Prior 30 Day Mean','Prior Mean'),('Sensor Deviation Z','Deviation Z')]:
        assert math.isclose(actual_measures['['+name+']'],row[col],abs_tol=0.0001),name
    assert len(actual_measures)==41
    summary={'status':'passed','full_totals':'matched','date_machine_filters':3,'default_2015_totals':'matched','top_10_scores_reasons_dense_ranks':'matched','sensor_mean_prior_reference_z':'matched','measures_executed':41,'numeric_tolerance':0.0001}
    (ROOT/'validation/comparison_results.json').write_text(json.dumps(summary,indent=2))
    print(json.dumps(summary))
if __name__=='__main__':main()
