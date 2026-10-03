"""Generate MCP request payloads; the MCP owns semantic-model serialization."""
from pathlib import Path
import json
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data/processed'
TABLES = {
    'Machines': ('machines', 'One row per machine; static model and recorded age in years.'),
    'Dates': ('dates', 'One row per calendar day; covers maintenance history and telemetry.'),
    'Components': ('components', 'One row per coded component; physical identities are unspecified.'),
    'Sensors': ('sensors', 'One row per sensor. Physical units are unspecified in the authoritative notebook.'),
    'Failures': ('failures', 'One row per timestamp, machine, component failure/replacement record; simultaneous components preserved.'),
    'Errors': ('errors', 'One row per timestamp, machine, error code; non-breaking errors.'),
    'Maintenance': ('maintenance', 'One row per timestamp, machine, component replacement; includes failure-related replacements.'),
    'Daily Health': ('daily_health', 'One row per machine, date with end-of-day score and daily telemetry summary. Only past/current records contribute.'),
    'Sensor Daily': ('sensor_daily', 'One row per machine, date, sensor. Prior reference uses preceding 30 days with minimum 7 days.'),
    'Failure Windows': ('failure_windows', 'One row per component failure event, relative day (-3 through +2), sensor; event-weighted hourly mean. Date is failure date.'),
    'Failure Intervals': ('failure_intervals', 'One row per completed gap between distinct consecutive machine failure timestamps. Date is ending event date.')}

def create_payloads():
    tables, relationships, measures = [], [], []
    for table, (filename, grain) in TABLES.items():
        df = pd.read_csv(OUT / (filename + '.csv'), nrows=1000)
        columns, types = [], []
        for col in df:
            if col in ['Date', 'Timestamp', 'Latest Timestamp', 'As Of Timestamp', 'Previous Failure']:
                dtype, mtype = 'DateTime', 'type datetime'
            elif pd.api.types.is_integer_dtype(df[col]): dtype, mtype = 'Int64', 'Int64.Type'
            elif pd.api.types.is_numeric_dtype(df[col]): dtype, mtype = 'Decimal', 'type number'
            else: dtype, mtype = 'String', 'type text'
            visible = (table in ['Machines', 'Dates', 'Components', 'Sensors'] or col in ['Date', 'Component', 'Error', 'Relative Day', 'Sensor', 'Priority Band']) and col not in ['Machine ID', 'Month Number', 'In Telemetry Period']
            columns.append({'name': col, 'sourceColumn': col, 'dataType': dtype, 'summarizeBy': 'None', 'isHidden': not visible,
                'isKey': (table == 'Machines' and col == 'Machine ID') or (table == 'Dates' and col == 'Date') or (table in ['Components', 'Sensors'] and col == table[:-1]),
                'formatString': 'yyyy-MM-dd' if col == 'Date' else ('0.00' if dtype == 'Decimal' else '0' if dtype == 'Int64' else None),
                'description': (grain if col in ['Machine ID', 'Date'] else f'{col}. '+ ('Source sample units, unspecified.' if col in ['Mean Reading','Prior Mean','Prior Std'] else 'See README for definitions.'))})
            types.append('{"' + col + '", ' + mtype + '}')
        m = 'let\n    Source = Csv.Document(File.Contents(#"Data Folder" & "/' + filename + '.csv"), [Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.Csv]),\n    Headers = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),\n    Typed = Table.TransformColumnTypes(Headers, {' + ', '.join(types) + '}, "en-US")\nin\n    Typed'
        tables.append({'name': table, 'description': grain, 'mode': 'Import', 'partitionName': table, 'mExpression': m, 'columns': columns})
        if table not in ['Machines','Dates','Components','Sensors']:
            pairs = [('Machine ID','Machines','Machine ID'), ('Date','Dates','Date')]
            if 'Component' in df: pairs.append(('Component','Components','Component'))
            if 'Sensor' in df: pairs.append(('Sensor','Sensors','Sensor'))
            for src, dest, key in pairs:
                relationships.append({'name': table + ' to ' + dest, 'fromTable': table, 'fromColumn': src, 'toTable': dest, 'toColumn': key,
                    'fromCardinality': 'Many', 'toCardinality': 'One', 'crossFilteringBehavior': 'OneDirection', 'isActive': True})
    def add(table, name, expression, desc, fmt='#,##0', folder='Reliability'):
        measures.append({'tableName': table,'name': name,'expression': expression,'description': desc,'formatString': fmt,'displayFolder': folder})
    add('Failures', 'Failure Events', "COALESCE(COUNTROWS('Failures'), 0)", 'Component failure records in selected period. Simultaneous component failures count separately.')
    add('Failures', 'Machines With Failures', "COALESCE(DISTINCTCOUNT('Failures'[Machine ID]), 0)", 'Distinct machines with at least one failure record in selected period; not failure event count.')
    add('Errors', 'Error Events', "COALESCE(COUNTROWS('Errors'), 0)", 'Non-breaking error records in selected period.')
    add('Maintenance', 'Replacement Records', "COALESCE(COUNTROWS('Maintenance'), 0)", 'Component replacement records including replacements related to failure. Do not add this to failures as unique incidents.')
    add('Daily Health', 'Observed Telemetry Hours', "SUM('Daily Health'[Reading Count])", 'One timestamped hourly sample is one observed telemetry hour; not proof of productive uptime.')
    add('Daily Health', 'Observed Machines', "DISTINCTCOUNT('Daily Health'[Machine ID])", 'Distinct machines with telemetry in selected period.')
    add('Failures', 'Failures per 1000 Observed Hours', 'DIVIDE([Failure Events] * 1000, [Observed Telemetry Hours])', 'Numerator: component failure records in date/machine selection. Denominator: hourly telemetry samples in same selection. Multiplied by 1000. Component filters apply to numerator only.', '0.000')
    add('Failures', 'Component Cumulative Share', "VAR _n = [Failure Events]\nVAR _components = ADDCOLUMNS(ALLSELECTED('Components'[Component]), \"Events\", [Failure Events])\nRETURN DIVIDE(SUMX(FILTER(_components, [Events] >= _n), [Events]), CALCULATE([Failure Events], ALLSELECTED('Components'[Component])))", 'Pareto cumulative fraction by descending component failure count; ties share a position.', '0.0%')
    add('Failures', 'Plant Insight', 'VAR _n = [Failure Events]\nVAR _top = TOPN(1, ADDCOLUMNS(ALLSELECTED(\'Components\'[Component]), "Events", [Failure Events]), [Events], DESC, \'Components\'[Component], ASC)\nRETURN FORMAT(_n,"#,##0") & " component failure events; " & FORMAT([Machines With Failures],"0") & " machines with records. " & IF(_n=0,"No failures in selected scope.",CONCATENATEX(_top,\'Components\'[Component] & " leads (" & FORMAT([Events],"0") & " events)."))', 'Dynamic count and leading component for current report filters.', 'General', 'Context')
    add('Failure Intervals','Mean Completed Failure Gap Hours', "VAR _start = MIN('Dates'[Date])\nRETURN CALCULATE(AVERAGE('Failure Intervals'[Gap Hours]), KEEPFILTERS('Failure Intervals'[Previous Failure] >= _start))", 'Mean observed gap between distinct machine failure timestamps, both inside selected continuous period. Not MTBF: censored first/last intervals and operating exposure unavailable.', '0.0')
    add('Failure Intervals','Completed Gap Sample', "VAR _start = MIN('Dates'[Date])\nRETURN CALCULATE(COUNTROWS('Failure Intervals'), KEEPFILTERS('Failure Intervals'[Previous Failure] >= _start))", 'Number of completed gaps contributing to mean; simultaneous components at one timestamp collapse only for this calculation.')
    for name, col in [('Sensor Daily Mean','Mean Reading'),('Prior 30 Day Mean','Prior Mean'),('Sensor Deviation Z','Deviation Z')]:
        add('Sensor Daily',name,f"AVERAGE('Sensor Daily'[{col}])", 'Daily sensor average; use one sensor at a time. Reference excludes current day and requires 7 previous daily means.', '0.00', 'Sensors')
    add('Failure Windows','Failure Window Mean', "CALCULATE(AVERAGE('Failure Windows'[Mean Reading]), 'Failure Windows'[Complete Bin] = 1)", 'Mean of full 24-hour event-relative bins; equal component-event weighting. Descriptive association, not causal.', '0.00','Failure Windows')
    add('Failure Windows','Window Event Sample', "CALCULATE(DISTINCTCOUNT('Failure Windows'[Event ID]), 'Failure Windows'[Complete Bin] = 1)", 'Distinct component failure records contributing to full 24-hour bins in selected relative day and sensor.', '#,##0', 'Failure Windows')
    add('Failure Windows','Window Hour Sample', "CALCULATE(SUM('Failure Windows'[Sample Hours]), 'Failure Windows'[Complete Bin] = 1)", 'Sum of event-relative sample hours; overlapping windows reuse telemetry and are not independent observations.', '#,##0', 'Failure Windows')
    add('Daily Health','As Of Date', "VAR _selected = MAX('Dates'[Date])\nVAR _last = CALCULATE(MAX('Daily Health'[Date]), REMOVEFILTERS('Dates'), 'Daily Health'[Date] <= _selected)\nRETURN _last", 'Latest available daily snapshot no later than maximum selected date; historical end-of-day convention.', 'yyyy-MM-dd','Priority')
    for name,col,fmt in [('Priority Score','Priority Score','0.0'),('Recent Failures 14 Days','Failures 14 Days','0'),('Recent Errors 7 Days','Errors 7 Days','0'),('Maximum Sensor Deviation','Sensor Deviation Max','0.00'),('Oldest Component Replacement Days','Oldest Component Days','0'),('Failure Score Points','Failure Points','0'),('Error Score Points','Error Points','0'),('Sensor Score Points','Sensor Points','0.0'),('Maintenance Score Points','Maintenance Points','0'),('Baseline Sensor Count','Baseline Sensors','0'),('Component History Count','Components With History','0')]:
        add('Daily Health', name, f"VAR _asOf = [As Of Date]\nRETURN IF(NOT ISBLANK(_asOf), CALCULATE(MAX('Daily Health'[{col}]), REMOVEFILTERS('Dates'), 'Daily Health'[Date] = _asOf))", 'Latest selected as-of snapshot. For scores and reasons select an individual machine or use the ranking table.',fmt,'Priority')
    for name,col in [('Priority Reasons','Priority Reasons'),('Suggested Inspection','Suggested Inspection'),('Priority Status','Priority Band')]:
        add('Daily Health',name,f"VAR _asOf = [As Of Date]\nRETURN IF(HASONEVALUE('Machines'[Machine ID]), CALCULATE(SELECTEDVALUE('Daily Health'[{col}]), REMOVEFILTERS('Dates'), 'Daily Health'[Date] = _asOf), \"Select one machine\")", 'Rule-based prioritization, not probability; analytical recommendations requiring engineering review.', 'General', 'Priority')
    add('Daily Health','Priority Rank', "IF(HASONEVALUE('Machines'[Machine ID]), RANKX(ALLSELECTED('Machines'), [Priority Score], , DESC, Dense))", 'Dense rank within model/machine selection at the selected end date.', '0','Priority')
    add('Daily Health','High Priority Machines', "SUMX(VALUES('Machines'[Machine ID]), IF([Priority Score] >= 60, 1, 0))", 'Count of machines at rule-based score >=60 as of selected date.', '0','Priority')
    add('Daily Health','Watch Priority Machines', "SUMX(VALUES('Machines'[Machine ID]), IF([Priority Score] >= 30 && [Priority Score] < 60, 1, 0))", 'Count at 30<=score<60 as of selected date.', '0','Priority')
    add('Daily Health','Latest Observed Timestamp', "VAR _asOf = [As Of Date]\nRETURN CALCULATE(MAX('Daily Health'[Latest Timestamp]), REMOVEFILTERS('Dates'), 'Daily Health'[Date] = _asOf)", 'Latest telemetry actually observed at selected snapshot. No live feed.', 'yyyy-MM-dd HH:mm','Context')
    add('Machines','Machine Context', "SELECTEDVALUE('Machines'[Machine], \"Select one machine\") & \" | \" & SELECTEDVALUE('Machines'[Model], \"multiple models\") & \" | recorded age \" & FORMAT(SELECTEDVALUE('Machines'[Age Years]), \"0\") & \" years\"", 'Static recorded machine age; does not automatically age through history.', 'General','Context')
    add('Failures','Machine History Note', 'IF([Failure Events]=0,"No recorded failure in this period. ",FORMAT([Failure Events],"0") & " component failure records. ") & IF([Replacement Records]=0,"No replacement record in this period; earlier history may exist.",FORMAT([Replacement Records],"0") & " component replacements in this period.")', 'Separates absence of records from evidence of perfect health.', 'General','Context')
    add('Failures','Top Machine Failure Events', "VAR _rank = RANKX(ALLSELECTED('Machines'), [Failure Events], , DESC, Dense)\nRETURN IF(_rank <= 10, [Failure Events])", 'Top 10 dense ranks; ties retained.')
    add('Daily Health','Priority Date Label', '"As of " & FORMAT([As Of Date], "dd MMM yyyy") & " | rule-based score, not ML probability"', 'Historical cutoff and score meaning.', 'General','Priority')
    add('Sensor Daily','Sensor Context', 'SELECTEDVALUE(\'Sensors\'[Sensor], "Select one sensor") & " | source sample units (physical units unspecified)"', 'Sensor identity and unit limitation.', 'General','Sensors')
    payload = {'tables': tables,'relationships': relationships,'measures': measures}
    # Desktop prohibits a measure and a column with the same name in one table.
    reserved=['Priority Score','Priority Reasons','Suggested Inspection']
    for table in tables:
        if table['name']=='Daily Health':
            for column in table['columns']:
                if column['name'] in reserved:column['name']='Recorded '+column['name']
    for measure in measures:
        for name in reserved:measure['expression']=measure['expression'].replace("'Daily Health'["+name+"]", "'Daily Health'[Recorded "+name+"]")
    (ROOT/'src/model_payloads.json').write_text(json.dumps(payload, indent=2), encoding='utf-8')
    print(json.dumps({'tables':len(tables),'relationships':len(relationships),'measures':len(measures)}))

if __name__ == '__main__':create_payloads()
