# DAX measures

All measures for the Power BI report, grouped as they appear in the `_Measures` table.
Paste only the lines inside each ```` ```dax ```` box. A `Format:` line below a box applies to the measure just above it; a line that says "Format all ..." covers
the whole group named. Set it in **Properties > Formatting** (or **Measure tools > Format**) after creating the measure.
Every count, rate and percentile uses the NHAMCS visit weight (`fact_ed_visit[weight]`),
so the figures are national estimates, not counts of sampled records.

The **Expected values** table at the end comes from the SQL views and Python (Phase 5 and 6).
Power BI must show the same numbers; if one differs, the measure is wrong.

## Volume

```dax
Visits =
SUM ( fact_ed_visit[weight] )
```
Format: Whole number, 0 decimal places, thousands separator on (`#,0`)

```dax
Visits (M) =
DIVIDE ( [Visits], 1000000 )
```
Format: Decimal number, 1 decimal place (`0.0`)

```dax
Sample Visits =
COUNTROWS ( fact_ed_visit )
```
Format: Whole number, 0 decimal places, thousands separator on (`#,0`)
Unweighted: how many sampled records sit behind a figure.

```dax
Sample Size Check =
IF ( [Sample Visits] >= 30, "OK", "Low sample (<30)" )
```
Project screening rule. The full NCHS reliability standard also needs design-based confidence intervals.

## Rates

The denominator removes any outcome filter, so a slicer on outcome can't push a rate above 100%.

```dax
Admitted % =
DIVIDE (
    CALCULATE ( [Visits], dim_outcome[outcome] = "Admitted" ),
    CALCULATE ( [Visits], ALL ( dim_outcome ) )
)
```

```dax
Left Without Being Seen % =
DIVIDE (
    CALCULATE ( [Visits], dim_outcome[outcome] = "Left without being seen" ),
    CALCULATE ( [Visits], ALL ( dim_outcome ) )
)
```

```dax
Wait Missing % =
DIVIDE (
    CALCULATE ( [Visits], ISBLANK ( fact_ed_visit[waittime_min] ) ),
    [Visits]
)
```
Format all three: Percentage, 1 decimal place (`0.0%`)

## Times (weighted percentiles)

DAX's built-in `MEDIAN` and `PERCENTILE.INC` ignore weights, so they'd treat every sampled
record as one visit. These measures do it by hand:

1. Take each distinct minute value and the total weight of the visits with that value.
2. Add the weights up from the shortest time to the longest (a running total).
3. Return the first minute where the running total reaches 50% (median) or 90% of all weight.

This is the same rule as `sql/03_views.sql` and `clean.py`, so the results match exactly.

```dax
Median Wait (min) =
VAR Minutes =
    ADDCOLUMNS (
        FILTER ( VALUES ( fact_ed_visit[waittime_min] ), NOT ISBLANK ( fact_ed_visit[waittime_min] ) ),
        "@Weight", CALCULATE ( SUM ( fact_ed_visit[weight] ) )
    )
VAR Target = 0.5 * SUMX ( Minutes, [@Weight] )
VAR Running =
    ADDCOLUMNS (
        Minutes,
        "@RunningWeight",
            VAR ThisMinute = fact_ed_visit[waittime_min]
            RETURN SUMX ( FILTER ( Minutes, fact_ed_visit[waittime_min] <= ThisMinute ), [@Weight] )
    )
RETURN
    MINX ( FILTER ( Running, [@RunningWeight] >= Target ), fact_ed_visit[waittime_min] )
```

```dax
P90 Wait (min) =
VAR Minutes =
    ADDCOLUMNS (
        FILTER ( VALUES ( fact_ed_visit[waittime_min] ), NOT ISBLANK ( fact_ed_visit[waittime_min] ) ),
        "@Weight", CALCULATE ( SUM ( fact_ed_visit[weight] ) )
    )
VAR Target = 0.9 * SUMX ( Minutes, [@Weight] )
VAR Running =
    ADDCOLUMNS (
        Minutes,
        "@RunningWeight",
            VAR ThisMinute = fact_ed_visit[waittime_min]
            RETURN SUMX ( FILTER ( Minutes, fact_ed_visit[waittime_min] <= ThisMinute ), [@Weight] )
    )
RETURN
    MINX ( FILTER ( Running, [@RunningWeight] >= Target ), fact_ed_visit[waittime_min] )
```

```dax
Median Visit (min) =
VAR Minutes =
    ADDCOLUMNS (
        FILTER ( VALUES ( fact_ed_visit[lov_min] ), NOT ISBLANK ( fact_ed_visit[lov_min] ) ),
        "@Weight", CALCULATE ( SUM ( fact_ed_visit[weight] ) )
    )
VAR Target = 0.5 * SUMX ( Minutes, [@Weight] )
VAR Running =
    ADDCOLUMNS (
        Minutes,
        "@RunningWeight",
            VAR ThisMinute = fact_ed_visit[lov_min]
            RETURN SUMX ( FILTER ( Minutes, fact_ed_visit[lov_min] <= ThisMinute ), [@Weight] )
    )
RETURN
    MINX ( FILTER ( Running, [@RunningWeight] >= Target ), fact_ed_visit[lov_min] )
```

```dax
P90 Visit (min) =
VAR Minutes =
    ADDCOLUMNS (
        FILTER ( VALUES ( fact_ed_visit[lov_min] ), NOT ISBLANK ( fact_ed_visit[lov_min] ) ),
        "@Weight", CALCULATE ( SUM ( fact_ed_visit[weight] ) )
    )
VAR Target = 0.9 * SUMX ( Minutes, [@Weight] )
VAR Running =
    ADDCOLUMNS (
        Minutes,
        "@RunningWeight",
            VAR ThisMinute = fact_ed_visit[lov_min]
            RETURN SUMX ( FILTER ( Minutes, fact_ed_visit[lov_min] <= ThisMinute ), [@Weight] )
    )
RETURN
    MINX ( FILTER ( Running, [@RunningWeight] >= Target ), fact_ed_visit[lov_min] )
```

Boarding only applies to admitted patients, so this one keeps admitted visits only.
`KEEPFILTERS` means an outcome slicer set to anything else returns blank instead of a wrong number.

```dax
Median Boarding (min) =
VAR Minutes =
    CALCULATETABLE (
        ADDCOLUMNS (
            FILTER ( VALUES ( fact_ed_visit[boarded_min] ), NOT ISBLANK ( fact_ed_visit[boarded_min] ) ),
            "@Weight", CALCULATE ( SUM ( fact_ed_visit[weight] ) )
        ),
        KEEPFILTERS ( dim_outcome[outcome] = "Admitted" )
    )
VAR Target = 0.5 * SUMX ( Minutes, [@Weight] )
VAR Running =
    ADDCOLUMNS (
        Minutes,
        "@RunningWeight",
            VAR ThisMinute = fact_ed_visit[boarded_min]
            RETURN SUMX ( FILTER ( Minutes, fact_ed_visit[boarded_min] <= ThisMinute ), [@Weight] )
    )
RETURN
    MINX ( FILTER ( Running, [@RunningWeight] >= Target ), fact_ed_visit[boarded_min] )
```

Format all five: Whole number, 0 decimal places (`0`)

## Change over time

There's no date table: the data has survey years only, so these use `dim_year[year]`
directly instead of Power BI's time-intelligence functions, which need real dates.

```dax
Median Visit Prior Year (min) =
VAR ThisYear = SELECTEDVALUE ( dim_year[year] )
RETURN
    IF ( NOT ISBLANK ( ThisYear ), CALCULATE ( [Median Visit (min)], dim_year[year] = ThisYear - 1 ) )
```

```dax
Median Visit Change vs Prior Year (min) =
IF (
    NOT ISBLANK ( [Median Visit Prior Year (min)] ),
    [Median Visit (min)] - [Median Visit Prior Year (min)]
)
```
Format both prior-year measures: Whole number, 0 decimal places (`0`)

```dax
Median Visit Change since 2018 % =
VAR Base = CALCULATE ( [Median Visit (min)], dim_year[year] = 2018 )
RETURN DIVIDE ( [Median Visit (min)] - Base, Base )
```

```dax
P90 Visit Change since 2018 % =
VAR Base = CALCULATE ( [P90 Visit (min)], dim_year[year] = 2018 )
RETURN DIVIDE ( [P90 Visit (min)] - Base, Base )
```
Format the two % measures: Percentage, 1 decimal place (`0.0%`)

## Alberta page (CIHI 2025-2026)

`cihi_ed_los` has no relationship to the NHAMCS tables: it's a different country, year and
definition. Use these with `cihi_ed_los[patient_group]` on the axis or in a slicer.

```dax
CIHI Alberta Median (h) =
CALCULATE ( MAX ( cihi_ed_los[median_los_hours] ), cihi_ed_los[province_code] = "Alta." )
```

```dax
CIHI Canada Median (h) =
CALCULATE ( MAX ( cihi_ed_los[median_los_hours] ), cihi_ed_los[province_code] = "Total" )
```

```dax
CIHI Alberta P90 (h) =
CALCULATE ( MAX ( cihi_ed_los[p90_los_hours] ), cihi_ed_los[province_code] = "Alta." )
```

```dax
CIHI Canada P90 (h) =
CALCULATE ( MAX ( cihi_ed_los[p90_los_hours] ), cihi_ed_los[province_code] = "Total" )
```

```dax
CIHI Alberta vs Canada P90 (h) =
[CIHI Alberta P90 (h)] - [CIHI Canada P90 (h)]
```
Format all five CIHI measures: Decimal number, 1 decimal place (`0.0`). Whole number would round
Alberta's 13.2 hours to 13 and hide the gaps the Alberta page is meant to show.

## Expected values

Build a matrix with `dim_year[year]` as rows and the measures below as values.
The **All years** row is the matrix total.

| Year | Visits (M) | Median Wait | P90 Wait | Median Visit | P90 Visit | Median Boarding | Admitted % | Left Without Being Seen % | Wait Missing % |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2018 | 130.0 | 15 | 88 | 168 | 418 | 19 | 12.4% | 1.2% | 11.1% |
| 2019 | 150.6 | 14 | 93 | 167 | 428 | 40 | 11.2% | 1.3% | 15.8% |
| 2020 | 131.3 | 11 | 64 | 175 | 442 | 41 | 14.1% | 1.0% | 13.4% |
| 2021 | 139.8 | 16 | 90 | 192 | 481 | 30 | 13.1% | 1.7% | 12.8% |
| 2022 | 155.4 | 16 | 98 | 189 | 514 | 62 | 11.5% | 1.9% | 14.2% |
| All years | 707.1 | 14 | 88 | 178 | 459 | 40 | 12.4% | 1.4% | 13.5% |

Also: `P90 Visit Change since 2018 %` for 2022 = **23.0%**; `Median Visit Change since 2018 %` for 2022 = **12.5%**.

CIHI, Alberta vs Canada (hours): urgent discharged median 4.1 vs 4.1, P90 10.2 vs 10.2;
less urgent discharged median 2.4 vs 2.7, P90 6.3 vs 7.8; admitted median 13.2 vs 15.5, P90 42.3 vs 46.5.

## Phase 8 measures (report pages)

Add these to `_Measures` the same way. Expected values follow at the end of this section.

```dax
Triage Unknown % =
DIVIDE (
    CALCULATE ( [Visits], dim_triage[triage_group] = "Unknown" ),
    CALCULATE ( [Visits], ALL ( dim_triage ) )
)
```

```dax
Ambulance % =
DIVIDE (
    CALCULATE ( [Visits], dim_arrival_mode[arrival_mode] = "Ambulance" ),
    CALCULATE ( [Visits], ALL ( dim_arrival_mode ) )
)
```

```dax
Boarding Missing % =
DIVIDE (
    CALCULATE ( [Visits], dim_outcome[outcome] = "Admitted", ISBLANK ( fact_ed_visit[boarded_min] ) ),
    CALCULATE ( [Visits], dim_outcome[outcome] = "Admitted" )
)
```
Share of admitted visits with no boarding time recorded.

Format all three: Percentage, 1 decimal place (`0.0%`)

`Median Boarding (min)` stays on the Model check page only. 35-46% of recorded boarding times are
exactly 0, so that median jumps around. The report uses this one instead, and the Data quality page explains why.

```dax
Median Boarding above 0 (min) =
VAR Minutes =
    CALCULATETABLE (
        ADDCOLUMNS (
            FILTER (
                VALUES ( fact_ed_visit[boarded_min] ),
                NOT ISBLANK ( fact_ed_visit[boarded_min] ) && fact_ed_visit[boarded_min] > 0
            ),
            "@Weight", CALCULATE ( SUM ( fact_ed_visit[weight] ) )
        ),
        KEEPFILTERS ( dim_outcome[outcome] = "Admitted" )
    )
VAR Target = 0.5 * SUMX ( Minutes, [@Weight] )
VAR Running =
    ADDCOLUMNS (
        Minutes,
        "@RunningWeight",
            VAR ThisMinute = fact_ed_visit[boarded_min]
            RETURN SUMX ( FILTER ( Minutes, fact_ed_visit[boarded_min] <= ThisMinute ), [@Weight] )
    )
RETURN
    MINX ( FILTER ( Running, [@RunningWeight] >= Target ), fact_ed_visit[boarded_min] )
```
Format: Whole number, 0 decimal places (`0`)

```dax
Low Sample Flag =
IF ( NOT ISBLANK ( [Sample Visits] ) && [Sample Visits] < 30, 1, 0 )
```
Format: Whole number. Returns 1 when fewer than 30 sampled records sit behind a figure; used for conditional formatting.

```dax
CIHI Bar Colour =
SWITCH (
    SELECTEDVALUE ( cihi_ed_los[province_code] ),
    "Alta.", "#1F6FB2",
    "Total", "#5B5B5B",
    "#B8C4CE"
)
```
Text: no number format. Colours each province bar: Alberta blue, Canada dark grey, other provinces light grey.

```dax
Selected Group =
SWITCH (
    TRUE (),
    ISFILTERED ( dim_age_group[age_group] ), "Age " & SELECTEDVALUE ( dim_age_group[age_group] ),
    ISFILTERED ( dim_arrival_mode[arrival_mode] ), "Arrival: " & SELECTEDVALUE ( dim_arrival_mode[arrival_mode] ),
    ISFILTERED ( dim_payer[payer_group] ), "Payer: " & SELECTEDVALUE ( dim_payer[payer_group] ),
    ISFILTERED ( dim_region[region] ), "Region: " & SELECTEDVALUE ( dim_region[region] ),
    ISFILTERED ( dim_metro[metro_status] ), SELECTEDVALUE ( dim_metro[metro_status] ),
    ISFILTERED ( dim_triage[triage_group] ), "Triage: " & SELECTEDVALUE ( dim_triage[triage_group] ),
    "All visits (no group selected)"
)
```
Text: no number format. Used on the Visit detail drill-through page to name the group the reader drilled into
(for example, right-clicking the Ambulance bar on page 2 shows "Arrival: Ambulance").

### Expected values: new measures

| Year | Triage Unknown % | Boarding Missing % | Median Boarding above 0 (min) | Ambulance % |
| --- | --- | --- | --- | --- |
| 2018 | 22.7% | 29.0% | 83 | 16.0% |
| 2019 | 22.5% | 28.9% | 101 | 15.5% |
| 2020 | 30.1% | 26.9% | 116 | 19.7% |
| 2021 | 23.1% | 20.7% | 132 | 17.6% |
| 2022 | 25.8% | 21.2% | 141 | 17.0% |
| All years | 24.8% | 25.2% | 114 | 17.1% |

### Expected values: page 2, P90 Visit (min), all years

| Group | P90 Visit | Median Visit | Sample visits |
| --- | --- | --- | --- |
| Age 65+ | 571 | 233 | 16,127 |
| Age 45-64 | 515 | 200 | 20,107 |
| Age 20-44 | 428 | 168 | 29,793 |
| Age 0-19 | 341 | 136 | 20,837 |
| Ambulance | 712 | 249 | 14,983 |
| Walk-in or other | 413 | 165 | 68,984 |
| Arrival unknown | 516 | 184 | 2,897 |
| Medicare | 552 | 224 | 17,139 |
| Payer unknown | 499 | 187 | 9,554 |
| Other payer | 435 | 168 | 2,463 |
| Medicaid / CHIP | 432 | 159 | 30,039 |
| Private insurance | 422 | 175 | 21,412 |
| Self-pay or no charge | 386 | 155 | 6,257 |
| Northeast | 560 | 213 | 18,502 |
| West | 476 | 190 | 19,262 |
| Midwest | 445 | 168 | 20,830 |
| South | 413 | 165 | 28,270 |
| Metro | 476 | 185 | 75,881 |
| Non-metro | 336 | 140 | 10,983 |
| Triage 1 - Immediate | 827 | 214 | 846 |
| Triage 2 - Emergent | 741 | 262 | 8,597 |
| Triage 3 - Urgent | 463 | 208 | 29,568 |
| Triage 4 - Semi-urgent | 280 | 117 | 16,715 |
| Triage 5 - Nonurgent | 294 | 96 | 2,398 |
| No triage | 425 | 165 | 6,476 |
| Triage unknown | 497 | 175 | 22,264 |

No group falls below 30 sampled visits even when split by single year (smallest: Other payer in 2020, 330).

### Expected values: page 3, outcome mix (% of visits)

| Year | Discharged or other | Admitted | Left against medical advice | Left without being seen |
| --- | --- | --- | --- | --- |
| 2018 | 85.7% | 12.4% | 0.7% | 1.2% |
| 2019 | 86.6% | 11.2% | 0.9% | 1.3% |
| 2020 | 83.7% | 14.1% | 1.2% | 1.0% |
| 2021 | 84.2% | 13.1% | 1.0% | 1.7% |
| 2022 | 85.4% | 11.5% | 1.2% | 1.9% |

### Expected values: page 5, wait by triage level (all years, from `vw_triage_wait`)

| Triage group | Median Wait (min) | P90 Wait (min) |
| --- | --- | --- |
| 1 - Immediate | 10 | 65 |
| 2 - Emergent | 11 | 64 |
| 3 - Urgent | 14 | 89 |
| 4 - Semi-urgent | 15 | 83 |
| 5 - Nonurgent | 16 | 82 |
| No triage | 17 | 105 |
| Unknown | 16 | 98 |

### Expected values: drill-through, share of visits by reason module (all years)

Symptom 75.4%, Injury or adverse effect 14.4%, Disease 5.1%, Treatment 1.8%,
Diagnostic/screening/preventive 1.6%, Test results 0.8%, Blank 0.5%, Uncodable 0.4%, Administrative 0.2%.

### Expected values: drill-through tests (all years)

| Drilled from | Selected Group | P90 Visit | Median Visit | Sample Visits | Sample Size Check |
| --- | --- | --- | --- | --- | --- |
| Ambulance bar | Arrival: Ambulance | 712 | 249 | 14,983 | OK |
| 65+ bar | Age 65+ | 571 | 233 | 16,127 | OK |
