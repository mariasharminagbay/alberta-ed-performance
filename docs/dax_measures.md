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
