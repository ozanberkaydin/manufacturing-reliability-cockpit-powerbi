# Manufacturing Reliability & Maintenance Cockpit

A historical reliability and maintenance analysis for a manufacturing maintenance manager. Python prepares auditable data and time-safe rule-based priorities. Power BI provides four connected pages: Plant Overview, Machine Health, Failure Analysis, and Maintenance Priorities. No machine learning is used.

> **Scope:** This is historical reliability analytics on a simulated Microsoft sample. The priority score is a transparent rule-based ranking for engineering review, not a failure prediction, not ML, not a live monitoring system, and not production-deployed.

Companion project on the same dataset: [azure-predictive-maintenance-sql](https://github.com/ozanberkaydin/azure-predictive-maintenance-sql) (PostgreSQL analysis). Shared headline figures (761 component failure records, comp2 = 34.0%, 1,107.29 h mean completed failure gap over 621 gaps) agree across both projects.

## Report pages

| Plant Overview | Machine Health |
|---|---|
| ![Plant Overview](screenshots/Plant%20Overview.png) | ![Machine Health](screenshots/Machine%20Health.png) |
| **Failure Analysis** | **Maintenance Priorities** |
| ![Failure Analysis](screenshots/Failure%20Analysis.png) | ![Maintenance Priorities](screenshots/Maintenance%20Priorities.png) |

Tech stack: Python (pandas, numpy) · Power BI Desktop (PBIP / PBIR, TMDL) · DAX · Power Query

## Data source and terms

The five source CSVs are downloaded by `src/pipeline.py` from Microsoft's public [sqlworkshops sample data folder](https://github.com/microsoft/sqlworkshops/tree/master/SQLServerAndAzureMachineLearning/ML%20Services%20for%20SQL%20Server/data). The [authoritative Microsoft notebook](https://github.com/microsoft/sqlworkshops/blob/master/SQLServerAndAzureMachineLearning/ML%20Services%20for%20SQL%20Server/notebooks/Predictive%20Maintenance%20in%20Python%20Notebook.ipynb) explicitly describes the data as created by simulation methods. This is a portfolio sample, not a measured production plant or live feed.

Microsoft's repository supplies an [MIT license](https://github.com/microsoft/sqlworkshops/blob/master/LICENSE), retained verbatim in `docs/MICROSOFT_SAMPLE_LICENSE.txt`. It permits use/modification/distribution subject to retaining the notice and provides the sample as-is without warranty. No additional dataset-specific terms were found in the source folder. Raw source files, download URLs, and SHA-256 hashes are recorded in `validation/data_quality.json`. Source URLs currently target `master`; hashes identify this build and should be compared after future downloads.

| Dataset | Actual rows | Grain and meaning | Coverage |
|---|---:|---|---|
| Machines | 100 | One machine; model code and static recorded age in years | Static metadata |
| Telemetry | 876,100 | One machine/hour; hourly voltage, rotation, pressure, vibration averages | 2015-01-01 06:00 to 2016-01-01 06:00 |
| Errors | 3,919 | One machine/timestamp/error code; non-breaking error | 2015-01-01 06:00 to 2016-01-01 05:00 |
| Maintenance | 3,286 | One machine/timestamp/component replacement, scheduled or failure-related | 2014-06-01 06:00 to 2016-01-01 06:00 |
| Failures | 761 | One machine/timestamp/component failure replacement | 2015-01-02 03:00 to 2015-12-31 06:00 |

Timestamps have no supplied timezone; they remain source-local, naive timestamps. Do not infer UTC or plant geography. Components `comp1`–`comp4`, error codes, and model codes have no documented physical mapping. The authoritative notebook does not state physical units for the four sensor columns; report labels use **source sample units**, rather than assuming V, rpm, psi, or g. Recorded machine age is not recalculated through the year.

## Architecture and files

```text
Microsoft CSVs -> Python validation/cleaning -> processed CSVs
              -> daily features and historical priority snapshots
              -> Power BI MCP offline TOM model -> exported TMDL
              -> PBIP / native PBIR visuals -> Power BI Desktop
```

`src/pipeline.py` downloads missing files and writes clean machine, telemetry, error, replacement, and failure data. `daily_health.csv` has one row per machine/day (36,600); `sensor_daily.csv` has one row per machine/day/sensor (146,400). `failure_windows.csv` stores event-relative bins at component-event/day-offset/sensor grain; `failure_intervals.csv` stores completed gaps between distinct machine failure timestamps. Daily aggregation does not overwrite or collapse the clean source event files.

The 11-table star model uses Machines and a contiguous marked Dates dimension. Components connects to Failures, Maintenance, and Failure Windows; Sensors connects to Sensor Daily and Failure Windows. All 19 relationships are active, many-to-one, single-direction dimension-to-fact. There are no fact-to-fact, bidirectional, or many-to-many joins. Dates includes earlier replacement history; the report starts with a selectable 2015 date range. Date, model, and machine filters are visible. Date/model selections sync across pages; Machine Health keeps its machine picker independent to support drill-through.

## KPI definitions

- **Failure Events:** component failure records within selected dates/machines. Simultaneous failed components count separately.
- **Machines With Failures:** distinct machines with at least one failure record in the selection. This is not the failure-event count.
- **Observed Telemetry Hours:** number of hourly samples in the same selected dates/machines. It measures observed telemetry exposure, not productive uptime.
- **Failures per 1000 Observed Hours:** `1000 × selected component failure events / selected hourly samples`. Selected period is the date slicer range. Model/age comparisons use each group's observed exposure. A component filter affects the numerator; the denominator remains selected machine exposure. This is an event frequency, not a probability or component survival rate.
- **Replacement Records:** component replacements, including failure-related replacements. Do not add replacements and failures together as unique incidents.
- **Component Cumulative Share:** cumulative failure counts in descending component order / failure events in selected component scope. Shown as a Pareto combo chart: bars = failure events, line = cumulative share on the secondary axis.
- **Mean Completed Failure Gap Hours:** mean elapsed gap between distinct consecutive machine failure timestamps where both endpoints lie inside the selected continuous period. Simultaneous component failures collapse only for this metric. First/last censored intervals are excluded; only machines with repeat events contribute. This is deliberately **not labeled MTBF**, because true operating exposure, repair completion, censoring adjustments, and machine state are unavailable. Full-source mean is 1,107.29 hours over 621 completed gaps. The measure exists for exploration; no misleading MTBF headline is shown.
- **Failure Window Mean:** equally weighted full 24-hour bins around individual component failure records, offsets -3 through +2; day 0 begins at the failure timestamp. Partial bins are excluded from the visual's mean and sample count. Tooltips show event and hour samples. Overlapping windows reuse observations, so they are not independent; post-event values can reflect replacement. Associations are not causal evidence.

## Explainable rule-based priority score

Every machine has a historical end-of-day snapshot; selecting a range uses its **maximum date** as the cutoff. The measure selects the most recent available snapshot on or before that date, without extending the data into the future. There is no intraday selector. Lower date bound does not truncate replacement history or the recent-event windows.

| Contribution | Rule | Maximum points |
|---|---|---:|
| Recent failures | 20 points per component failure in current day and prior 13 days | 40 |
| Recent errors | 3 points per error in current day and prior 6 days | 15 |
| Sensor deviation | `15 × clip(max absolute z − 2, 0, 2)` | 30 |
| Maintenance recency | Oldest **known component** replacement: 8 points at 60–89 days; 15 at 90+ days | 15 |

Sum gives 0–100. **High – inspect:** >=60. **Watch – review:** 30–<60. **Routine – monitor:** <30. These weights and thresholds are transparent analyst choices, not calibrated failure probabilities, certified alarms, or economic optimization.

For each sensor and machine, z compares the current daily mean with the mean and sample standard deviation of the **preceding 30 observed daily means** (minimum 7), explicitly shifting by one day. Contiguous hourly coverage is verified before using these daily windows. Reference variance near zero or insufficient history yields no z score and zero sensor points; baseline coverage is exposed as a measure. Missing component history stays unknown, contributes no overdue points, and is not treated as proof of a recent replacement. Component history count is exposed. A new component replacement resets only that component's age; the oldest of the four known ages drives recency.

The queue includes recent counts, maximum deviation, oldest replacement age, status text, dense rank within selected machines/model, and each point contribution. Reasons and suggested inspections are available per machine. Suggestions are analytical recommendations for review by qualified maintenance staff. A prefix recomputation at 2015-06-30 verifies that later telemetry, failures, errors, and replacements do not change scores through that date.

## Findings from the sample

- 761 component failure records affect 98 of 100 machines; two machines have no failure record in the observed period.
- `comp2` contributes 259 records (34.0%), followed by `comp1` 192, `comp4` 179, and `comp3` 131. This concentrates inspection attention, but does not identify physical component causes.
- Full-source event frequency is 0.8686 component failures per 1,000 observed telemetry hours. Group comparisons must use exposure rather than raw counts alone.
- On 2015-12-31, Machine 088 leads the priority queue at 71.0: one failure over 14 days, two errors over 7 days, maximum absolute z about 8.3, and an oldest component replacement age of 91 days. Machine 015 scores 68.0; Machine 021 scores 61.0. These are review priorities, not predictions.

## Reproduce and open

Prerequisites: Python 3.11+ with pandas/numpy, Node.js 20+, the Power BI Authoring MCP package, report-authoring CLI, and a recent Power BI Desktop with PBIP/PBIR support. The build was run with Python 3.14.4, pandas 3.0.3, numpy 2.4.4. Run these commands from this project folder:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python src/pipeline.py
python src/model_spec.py
npm install -g @microsoft/powerbi-report-authoring-cli@latest
# Review https://go.microsoft.com/fwlink/?LinkId=2381247 before the next command.
python src/build_model.py --accept-eula
python src/report.py
powerbi-report-author --out validation/pbir_validation.json validate .\Manufacturing_Reliability_Cockpit.Report
```

Open `Manufacturing_Reliability_Cockpit.pbip` in Power BI Desktop and choose **Refresh** to load the processed CSVs if the local cache is absent. If you move the folder, update **Transform data > Manage Parameters > Data Folder** to the new `data/processed` folder, or rebuild with `build_model.py` (which resolves it from its own project root). Python/download paths are relative to the source-file location; Power Query uses one centralized absolute folder parameter because Desktop does not reliably resolve project-relative File.Contents paths.

Supported preview sequence (all commands from the project folder):

```powershell
# Microsoft Store installs may need the actual installed PBIDesktop.exe path:
# $env:PBI_DESKTOP_PATH = '<verified path to PBIDesktop.exe>'
powerbi-report-author preview .\Manufacturing_Reliability_Cockpit.pbip --host desktop --status
powerbi-report-author preview .\Manufacturing_Reliability_Cockpit.pbip --host desktop
# After changing PBIR, use status then --reload. After model file changes,
# use status then --reload-with-model, followed by appropriate MCP refresh.
powerbi-report-author preview .\Manufacturing_Reliability_Cockpit.pbip --host desktop --screenshot '<absolute path to retained screenshots>' --all-pages
```

Right-click a Machine row in the overview ranking or priority queue and choose **Drill through > Machine Health**, then use **Back to source**. Choose one sensor on Machine Health or Failure Analysis. All machines is a fleet-average sensor view; choose a single machine for a diagnostic profile. Inspect tooltips for event-window sample sizes and normalized-count denominators. Clear a prior local Machine Health selection before drilling into a different machine if Desktop retains it.

## Validation and limitations

See `validation/data_quality.json`, `python_expected.json`, `report_layout.json`, `pbir_validation.json`, and Desktop/model validation artifacts for actual outcomes. Python checks schemas, types, nulls, duplicate records, machine keys, timestamp alignment, continuous telemetry, failure/replacement matching, bounds of scores, and future-data invariance. Exact duplicate event records stop the pipeline for review; simultaneous different components/error codes remain. Layout checks verify canvas bounds and non-overlap. PBIR validation passed with zero errors and warnings before Desktop loading.

Live DAX totals, selected date/machine comparisons, visual rendering, and interactive verification must be assessed separately from on-disk checks. Screenshots, when successfully captured, are retained in `screenshots/` as requested delivery artifacts and can contain visible report data.

Source dates have partial first/last telemetry days. There is no production, repair duration, downtime, causal component mapping, savings, or cost data. No OEE, downtime costs, production losses, or maintenance savings are invented. Priority thresholds require local calibration before operational use. Model codes and static ages are descriptive strata; model/age differences do not prove causes. Raw data and the large cleaned hourly telemetry CSV are excluded from Git; they can be regenerated. Power BI cache files are excluded. Processed model inputs, source code, PBIP definitions, QA summaries, and retained screenshots form the delivery.

## Repository structure

```text
manufacturing-reliability-cockpit-powerbi/
├── Manufacturing_Reliability_Cockpit.pbip            # Open in Power BI Desktop
├── Manufacturing_Reliability_Cockpit.Report/         # PBIR report definition (4 pages)
├── Manufacturing_Reliability_Cockpit.SemanticModel/  # TMDL semantic model (11 tables)
├── src/                  # Python pipeline, model spec and report builders
├── data/processed/       # Model-ready CSVs (raw data and hourly telemetry are git-ignored)
├── validation/           # Data-quality, expected-value and layout checks
├── screenshots/          # Report page captures
├── docs/MICROSOFT_SAMPLE_LICENSE.txt
├── requirements.txt
├── LICENSE
└── README.md
```

## License

The [MIT License](LICENSE) applies to this repository's code, model definitions and documentation. The source data is Microsoft sample data under Microsoft's MIT license, retained in `docs/MICROSOFT_SAMPLE_LICENSE.txt`.

## Author

Ozan Berk Aydin
