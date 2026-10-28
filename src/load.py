"""Phase 4: load the cleaned visits and the code lookup tables into PostgreSQL (alberta_ed).
Run extract.py and clean.py first. Safe to re-run: each table is replaced."""
import sys
import pandas as pd
from sqlalchemy import text, types
from sqlalchemy.exc import OperationalError
from config import PROCESSED, LOOKUPS, get_engine

VISITS_TABLE = "visits_clean"

# Column types in PostgreSQL (anything not listed is stored as text)
VISIT_TYPES = {
    "visit_id": types.Integer(),
    "year": types.SmallInteger(),
    "weight": types.Float(),
    "hospital_code": types.SmallInteger(),
    "waittime_min": types.Integer(),
    "lov_min": types.Integer(),
    "boarded_min": types.Integer(),
    "triage_code": types.SmallInteger(),
    "arrival_hour": types.SmallInteger(),
    "weekday_code": types.SmallInteger(),
    "age": types.SmallInteger(),
    "sex_code": types.SmallInteger(),
    "payer_code": types.SmallInteger(),
    "region_code": types.SmallInteger(),
    "msa_code": types.SmallInteger(),
    "reason_code": types.Integer(),
    "diagnosis_code": types.String(8),
    "design_stratum": types.Integer(),
    "design_psu": types.Integer(),
}

# lookup file (from extract.py) -> table name in the database
LOOKUP_TABLES = {
    "immedr": "lkp_triage",
    "region": "lkp_region",
    "msa": "lkp_metro",
    "sex": "lkp_sex",
    "paytyper": "lkp_payer",
    "vdayr": "lkp_weekday",
    "arrems": "lkp_ambulance",
    "rfv1": "lkp_reason",
}

# Whole-number columns that contain blanks: read as nullable integers, not decimals
NULLABLE_INTS = ["waittime_min", "lov_min", "boarded_min", "arrival_hour"]


def connect():
    engine = get_engine()
    try:
        with engine.connect() as conn:
            conn.execute(text("select 1"))
    except OperationalError as e:
        print("Could not connect to PostgreSQL. Check .env (password, DB_NAME=alberta_ed) "
              "and that PostgreSQL is running.\nDetails:", str(e).splitlines()[0])
        sys.exit(1)
    return engine


def load_visits(engine):
    dtypes = {"diagnosis_code": str, **{c: "Int64" for c in NULLABLE_INTS}}
    visits = pd.read_csv(PROCESSED / "visits_clean.csv", dtype=dtypes)
    visits.to_sql(VISITS_TABLE, engine, if_exists="replace", index=False,
                  dtype=VISIT_TYPES, chunksize=5000, method="multi")
    with engine.begin() as conn:
        conn.execute(text(f"alter table {VISITS_TABLE} add primary key (visit_id)"))
    print(f"{VISITS_TABLE}: {len(visits):,} rows loaded")
    return visits


def load_lookups(engine):
    for file_stem, table in LOOKUP_TABLES.items():
        lookup = pd.read_csv(LOOKUPS / f"{file_stem}.csv")
        lookup.to_sql(table, engine, if_exists="replace", index=False,
                      dtype={"code": types.Integer(), "label": types.Text()})
        with engine.begin() as conn:
            conn.execute(text(f"alter table {table} add primary key (code)"))
        print(f"{table}: {len(lookup)} codes loaded")


def verify(engine, visits):
    """Compare row counts and weighted totals in the database with the CSV."""
    in_db = pd.read_sql(
        f"select year, count(*) as visits, sum(weight) as weighted from {VISITS_TABLE} group by year order by year",
        engine)
    in_csv = (visits.groupby("year")
              .agg(visits=("visit_id", "size"), weighted=("weight", "sum")).reset_index())
    check = in_db.merge(in_csv, on="year", suffixes=("_db", "_csv"))
    ok = (check["visits_db"] == check["visits_csv"]).all() and \
         ((check["weighted_db"] - check["weighted_csv"]).abs() < 1).all()
    check["weighted_M"] = (check["weighted_db"] / 1e6).round(1)
    print("\nVerification (database vs CSV):")
    print(check[["year", "visits_db", "visits_csv", "weighted_M"]].to_string(index=False))
    print("PASS: database matches the cleaned file" if ok else "FAIL: database and CSV differ")
    return ok


def main():
    engine = connect()
    visits = load_visits(engine)
    load_lookups(engine)
    ok = verify(engine, visits)
    engine.dispose()
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
