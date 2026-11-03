"""Load CIHI's 2025-2026 emergency department table (Table 1: visits and length of stay
by province) into PostgreSQL for the Alberta comparison page. Safe to re-run.

Source: CIHI, NACRS Emergency Department Visits and Lengths of Stay by Province/Territory,
2025-2026 (Q1 to Q4), released September 2026."""
import sys
import pandas as pd
from sqlalchemy import text, types
from config import RAW_CIHI, get_engine

CIHI_FILE = RAW_CIHI / "emergency-department-visits-apr-2025-mar-2026-data-tables-en.xlsx"
TABLE = "cihi_ed_los"
FISCAL_YEAR = "2025-2026"

PROVINCES = {
    "P.E.I.": "Prince Edward Island", "N.S.": "Nova Scotia", "Que.": "Quebec",
    "Ont.": "Ontario", "Man.": "Manitoba", "Sask.": "Saskatchewan", "Alta.": "Alberta",
    "B.C.": "British Columbia", "Y.T.": "Yukon", "Total": "Canada (participating)",
}

# Column positions in Table 1 (after the province column), per patient group
GROUPS = [
    # name, visits col, median col, 90th percentile col
    ("Urgent, discharged (CTAS I-III)", 2, 5, 8),
    ("Less urgent, discharged (CTAS IV-V)", 3, 6, 9),
    ("Admitted", 4, 7, 10),
]


def number(v):
    """CIHI writes 'n/a' where a province had too little data: store it as empty."""
    return None if v in (None, "n/a") else float(v)


def read_table1():
    raw = pd.read_excel(CIHI_FILE, sheet_name="Table 1", header=None)
    start = raw.index[raw[0].astype(str).str.startswith("Province/territory")][0] + 1
    end = raw.index[raw[0].astype(str).str.strip() == "Total"][0]
    rows = []
    for _, r in raw.loc[start:end].iterrows():
        label = str(r[0]).strip()
        short = label.replace("*", "").strip()
        if short not in PROVINCES:
            raise ValueError(f"Unexpected row in CIHI Table 1: {label!r}")
        common = {
            "fiscal_year": FISCAL_YEAR,
            "province_code": short,
            "province": PROVINCES[short],
            "is_alberta": short == "Alta.",
            "partial_coverage": label.endswith("**"),   # CIHI: not all EDs reported
            "total_visits": number(r[1]),
        }
        for group, v, med, p90 in GROUPS:
            rows.append({**common, "patient_group": group, "visits": number(r[v]),
                         "median_los_hours": number(r[med]), "p90_los_hours": number(r[p90])})
    return pd.DataFrame(rows)


def verify(df):
    """Provinces must add up to CIHI's own Canada total, for all visits and each group."""
    prov = df[df.province_code != "Total"]
    canada = df[df.province_code == "Total"]
    ok = True
    for col, label in [("total_visits", "all visits")]:
        p = prov.drop_duplicates("province_code")[col].sum()
        c = canada[col].iloc[0]
        ok &= p == c
        print(f"  {label}: provinces {p:,.0f} vs Canada total {c:,.0f}")
    for group, *_ in GROUPS:
        p = prov.loc[prov.patient_group == group, "visits"].sum()
        c = canada.loc[canada.patient_group == group, "visits"].iloc[0]
        ok &= p == c
        print(f"  {group}: provinces {p:,.0f} vs Canada total {c:,.0f}")
    return ok


def main():
    df = read_table1()
    print(f"Read {df.province_code.nunique()} rows from CIHI Table 1 ({len(df)} after splitting by patient group)")
    print("Check: provinces add up to the Canada total")
    ok = verify(df)

    engine = get_engine()
    df.to_sql(TABLE, engine, if_exists="replace", index=False, dtype={
        "fiscal_year": types.Text(), "province_code": types.Text(), "province": types.Text(),
        "is_alberta": types.Boolean(), "partial_coverage": types.Boolean(),
        "total_visits": types.BigInteger(), "patient_group": types.Text(), "visits": types.BigInteger(),
        "median_los_hours": types.Float(), "p90_los_hours": types.Float(),
    })
    with engine.begin() as conn:
        conn.execute(text(f"alter table {TABLE} add primary key (province_code, patient_group)"))
    print(f"\n{TABLE}: {len(df)} rows loaded")

    alberta = pd.read_sql(text(f"""
        select a.patient_group,
               a.median_los_hours as alberta_median, c.median_los_hours as canada_median,
               a.p90_los_hours    as alberta_p90,    c.p90_los_hours    as canada_p90
        from {TABLE} a join {TABLE} c using (patient_group)
        where a.province_code = 'Alta.' and c.province_code = 'Total'"""), engine)
    print("\nAlberta vs Canada, hours in the ED (2025-2026):")
    print(alberta.to_string(index=False))
    engine.dispose()

    print("\nPASS: provinces match the Canada total" if ok else "\nFAIL: provinces do not add up")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
