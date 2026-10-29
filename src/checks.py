"""Phase 6: data quality checks across every stage of the pipeline.
Run after transform.py. Prints PASS / WARN / FAIL per check, writes
docs/data_quality_report.md, and exits with an error if any check FAILs.

PASS = as expected.  WARN = worth knowing, kept as recorded.  FAIL = stop and fix."""
import sys
from datetime import date
import pandas as pd
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from config import ROOT, PROCESSED, get_engine
from clean import weighted_median

REPORT = ROOT / "docs" / "data_quality_report.md"

# CDC's own published national ED visit estimates, in millions. Sources:
# 2018 and 2019 summary tables (exact, thousands); 2020-2022 NCHS data briefs 452, 478, 503 (rounded).
CDC_PUBLISHED_M = {2018: 129.974, 2019: 150.650, 2020: 131, 2021: 140, 2022: 155}
CDC_TOLERANCE_M = 0.5        # the data briefs round to the nearest million

# Expected ranges for missing data, weighted % of visits per year (from Phase 3 profiling)
WAIT_MISSING_RANGE = (5, 20)
TRIAGE_UNKNOWN_RANGE = (15, 35)

MEASURES = ["waittime", "lov", "boarded"]
FACT_KEYS = 12


def connect():
    engine = get_engine()
    try:
        with engine.connect() as conn:
            conn.execute(text("select 1"))
    except OperationalError as e:
        print("Could not connect to PostgreSQL. Check .env and that PostgreSQL is running.\n"
              "Details:", str(e).splitlines()[0])
        sys.exit(1)
    return engine


def q(engine, sql):
    return pd.read_sql(text(sql), engine)   # text() lets "%" in a LIKE pattern through safely


def scalar(engine, sql):
    with engine.connect() as conn:
        return conn.execute(text(sql)).scalar()


# --- the checks: each returns (status, detail) ------------------------------------

def check_row_counts(engine, extracted, clean):
    fact = q(engine, "select year, count(*) as n from fact_ed_visit group by year").set_index("year")["n"]
    ext = extracted.groupby("year").size()
    cln = clean.groupby("year").size()
    bad = [y for y in ext.index if not (ext[y] == cln.get(y) == fact.get(y))]
    detail = ", ".join(f"{y}: {ext[y]:,}" for y in ext.index)
    return ("FAIL", f"counts differ in {bad}") if bad else ("PASS", f"extract = clean = database ({detail})")


def check_weighted_totals(engine, extracted):
    fact = q(engine, "select year, sum(weight) as w from fact_ed_visit group by year").set_index("year")["w"]
    ext = extracted.groupby("year")["PATWT"].sum()
    bad = [y for y in ext.index if abs(ext[y] - fact.get(y, 0)) >= 1]
    return ("FAIL", f"weights differ in {bad}") if bad else ("PASS", "weights in database equal the raw extract, all years")


def check_cdc_published(engine):
    fact = q(engine, "select year, sum(weight) / 1e6 as m from fact_ed_visit group by year").set_index("year")["m"]
    parts, bad = [], []
    for y, published in CDC_PUBLISHED_M.items():
        ours = fact.get(y)
        parts.append(f"{y}: {ours:.1f} vs {published:g}")
        if ours is None or abs(ours - published) > CDC_TOLERANCE_M:
            bad.append(y)
    status = "FAIL" if bad else "PASS"
    return status, ("off by more than 0.5M in " + str(bad) + "; " if bad else "") + "millions, ours vs CDC: " + "; ".join(parts)


def check_unique_ids(engine):
    dupes = scalar(engine, "select count(*) - count(distinct visit_id) from fact_ed_visit")
    return ("FAIL", f"{dupes} duplicate visit_id values") if dupes else ("PASS", "every visit_id is unique")


def check_foreign_keys(engine):
    n = scalar(engine, """
        select count(*) from information_schema.table_constraints
        where table_name = 'fact_ed_visit' and constraint_type = 'FOREIGN KEY'""")
    return ("PASS", f"{n} foreign keys enforce every dimension link") if n == FACT_KEYS \
        else ("FAIL", f"expected {FACT_KEYS} foreign keys, found {n}")


# The label each report visual shows, per dimension (dim_year.note is optional, so it isn't listed)
LABEL_COLUMNS = {
    "dim_year": "year_label", "dim_triage": "triage_group", "dim_outcome": "outcome",
    "dim_age_group": "age_group", "dim_sex": "sex", "dim_payer": "payer_group",
    "dim_region": "region", "dim_metro": "metro_status", "dim_weekday": "weekday",
    "dim_arrival_mode": "arrival_mode", "dim_hour": "hour_label", "dim_reason": "reason",
}


def check_dimension_labels(engine):
    bad = []
    for table, col in LABEL_COLUMNS.items():
        n = scalar(engine, f"select count(*) from {table} where {col} is null or trim({col}) = ''")
        if n:
            bad.append(f"{table}.{col} ({n})")
    return ("FAIL", "empty labels: " + ", ".join(bad)) if bad \
        else ("PASS", f"no empty labels in {len(LABEL_COLUMNS)} dimension tables")


def check_weights_positive(engine):
    n = scalar(engine, "select count(*) from fact_ed_visit where weight is null or weight <= 0")
    return ("FAIL", f"{n} visits with a zero, negative or empty weight") if n else ("PASS", "all weights are positive")


def check_minute_ranges(engine):
    r = q(engine, """
        select
          count(*) filter (where waittime_min < 0 or waittime_min > 1440) as wait_out,
          count(*) filter (where lov_min < 0)                              as lov_out,
          count(*) filter (where boarded_min < 0)                          as boarded_out,
          count(*) filter (where waittime_min > lov_min)                   as wait_over_visit,
          max(waittime_min) as max_wait, max(lov_min) as max_lov
        from fact_ed_visit""").iloc[0]
    problems = int(r.wait_out + r.lov_out + r.boarded_out + r.wait_over_visit)
    detail = (f"wait 0-1440 min, visit and boarding not negative, wait never longer than the visit "
              f"(longest wait {int(r.max_wait)} min, longest visit {int(r.max_lov)} min)")
    return ("FAIL", f"{problems} out-of-range values") if problems else ("PASS", detail)


def check_missing_reasons(engine):
    bad = []
    for m in MEASURES:
        n = scalar(engine, f"""
            select count(*) from fact_ed_visit
            where ({m}_min is null) <> ({m}_missing is not null)""")
        if n:
            bad.append(f"{m} ({n})")
    return ("FAIL", "value and missing reason disagree: " + ", ".join(bad)) if bad \
        else ("PASS", "every empty value has a reason, and no recorded value has one")


def check_missing_shares(engine):
    r = q(engine, """
        select f.year,
          100 * sum(f.weight) filter (where f.waittime_min is null) / sum(f.weight)   as wait_missing,
          100 * sum(f.weight) filter (where t.triage_group = 'Unknown') / sum(f.weight) as triage_unknown
        from fact_ed_visit f join dim_triage t using (triage_code)
        group by f.year order by f.year""")
    out = r[~r.wait_missing.between(*WAIT_MISSING_RANGE) | ~r.triage_unknown.between(*TRIAGE_UNKNOWN_RANGE)]
    detail = (f"wait missing {r.wait_missing.min():.1f}-{r.wait_missing.max():.1f}%, "
              f"triage unknown {r.triage_unknown.min():.1f}-{r.triage_unknown.max():.1f}% (weighted, by year)")
    return ("WARN", f"outside expected range in {list(out.year)}: {detail}") if len(out) else ("PASS", detail)


def check_outcome_logic(engine):
    r = q(engine, """
        select
          count(*) filter (where o.outcome = 'Left without being seen' and f.waittime_min is not null) as lwbs_with_wait,
          count(*) filter (where o.outcome <> 'Admitted' and f.boarded_min is not null)              as boarded_not_admitted
        from fact_ed_visit f join dim_outcome o using (outcome_key)""").iloc[0]
    n1, n2 = int(r.lwbs_with_wait), int(r.boarded_not_admitted)
    if n1 or n2:
        return "WARN", (f"{n1} 'left without being seen' visits have a wait time; "
                        f"{n2} non-admitted visits have boarding time. Kept as recorded by CDC.")
    return "PASS", "outcomes and times are consistent"


def check_sql_matches_python(engine, clean):
    sql = q(engine, "select year, median_wait_min, median_visit_min from vw_year_summary").set_index("year")
    bad, parts = [], []
    for y, g in clean.groupby("year"):
        py_wait = weighted_median(g["waittime_min"], g["weight"])
        py_lov = weighted_median(g["lov_min"], g["weight"])
        s = sql.loc[y]
        if py_wait != s.median_wait_min or py_lov != s.median_visit_min:
            bad.append(y)
        parts.append(f"{y}: {py_wait:g}/{py_lov:g}")
    return ("FAIL", f"SQL and Python medians differ in {bad}") if bad \
        else ("PASS", "SQL view and Python agree on weighted median wait/visit: " + "; ".join(parts))


# --- runner -----------------------------------------------------------------------

def main():
    engine = connect()
    extracted = pd.read_csv(PROCESSED / "visits_extracted.csv", usecols=["year", "PATWT"])
    clean = pd.read_csv(PROCESSED / "visits_clean.csv",
                        usecols=["year", "weight", "waittime_min", "lov_min"])

    checks = [
        ("Row counts match across extract, clean and database", lambda: check_row_counts(engine, extracted, clean)),
        ("Weighted totals match the raw extract", lambda: check_weighted_totals(engine, extracted)),
        ("Weighted totals match CDC's published estimates", lambda: check_cdc_published(engine)),
        ("visit_id is unique", lambda: check_unique_ids(engine)),
        ("Foreign keys exist for all 12 dimensions", lambda: check_foreign_keys(engine)),
        ("Dimension labels are filled", lambda: check_dimension_labels(engine)),
        ("Weights are positive", lambda: check_weights_positive(engine)),
        ("Minutes are in a valid range", lambda: check_minute_ranges(engine)),
        ("Missing values always have a reason", lambda: check_missing_reasons(engine)),
        ("Missing-data shares are in the expected range", lambda: check_missing_shares(engine)),
        ("Outcomes and times are consistent", lambda: check_outcome_logic(engine)),
        ("SQL views match Python's weighted medians", lambda: check_sql_matches_python(engine, clean)),
    ]

    results = []
    for i, (name, run) in enumerate(checks, 1):
        status, detail = run()
        results.append((i, name, status, detail))
        print(f"{i:>2}. [{status}] {name}\n      {detail}")
    engine.dispose()

    counts = {s: sum(r[2] == s for r in results) for s in ("PASS", "WARN", "FAIL")}
    summary = f"{counts['PASS']} passed, {counts['WARN']} warnings, {counts['FAIL']} failed"
    print(f"\n{summary}")

    REPORT.parent.mkdir(exist_ok=True)
    lines = [
        "# Data quality report",
        "",
        f"Generated by `src/checks.py` on {date.today().isoformat()}: **{summary}**.",
        "",
        "PASS = as expected. WARN = worth knowing, kept as recorded. FAIL = pipeline stopped.",
        "",
        "| # | Check | Result | Detail |",
        "| --- | --- | --- | --- |",
        *[f"| {i} | {name} | {status} | {detail.replace('|', '/')} |" for i, name, status, detail in results],
        "",
        "CDC published totals: 2018 and 2019 NHAMCS ED summary tables; NCHS Data Briefs 452 (2020), 478 (2021), 503 (2022).",
        "",
    ]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Report written to docs/{REPORT.name}")
    sys.exit(1 if counts["FAIL"] else 0)


if __name__ == "__main__":
    main()
