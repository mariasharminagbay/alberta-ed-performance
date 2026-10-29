"""Phase 5: build the star schema in PostgreSQL by running the SQL files in sql/ in order,
then print row counts and the summary views. Run load.py first. Safe to re-run."""
import sys
import pandas as pd
from sqlalchemy import text
from config import ROOT, get_engine

SQL_DIR = ROOT / "sql"
SQL_FILES = ["01_dimensions.sql", "02_fact.sql", "03_views.sql"]

TABLES = ["dim_year", "dim_triage", "dim_outcome", "dim_age_group", "dim_sex", "dim_payer",
          "dim_region", "dim_metro", "dim_weekday", "dim_arrival_mode", "dim_hour",
          "dim_reason", "fact_ed_visit"]


def run_sql_files(engine):
    for name in SQL_FILES:
        sql = (SQL_DIR / name).read_text(encoding="utf-8")
        raw = engine.raw_connection()      # plain driver connection: runs the file as written,
        try:                               # so "%" in comments isn't read as a placeholder
            with raw.cursor() as cur:
                cur.execute(sql)
            raw.commit()                   # each file is one transaction
        except Exception as e:
            raw.rollback()
            print(f"FAILED in {name}:\n{str(e).strip()}")
            sys.exit(1)
        finally:
            raw.close()
        print(f"ran {name}")


def report(engine):
    with engine.connect() as conn:
        print("\nRow counts:")
        for table in TABLES:
            n = conn.execute(text(f"select count(*) from {table}")).scalar()
            print(f"  {table:<18} {n:>7,}")
        source = conn.execute(text("select count(*) from visits_clean")).scalar()
        fact = conn.execute(text("select count(*) from fact_ed_visit")).scalar()

    pd.set_option("display.width", 160)
    print("\nvw_year_summary (weighted):")
    print(pd.read_sql("select * from vw_year_summary", engine).to_string(index=False))
    print("\nvw_triage_wait (weighted, all years):")
    print(pd.read_sql("select * from vw_triage_wait", engine).to_string(index=False))

    ok = fact == source
    print(f"\n{'PASS' if ok else 'FAIL'}: fact_ed_visit has {fact:,} rows; visits_clean has {source:,}")
    return ok


def main():
    engine = get_engine()
    run_sql_files(engine)
    ok = report(engine)
    engine.dispose()
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
