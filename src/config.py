"""Shared settings: file paths and the database connection."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW_NHAMCS = ROOT / "data" / "raw" / "nhamcs"
RAW_CIHI = ROOT / "data" / "raw" / "cihi"
PROCESSED = ROOT / "data" / "processed"
LOOKUPS = PROCESSED / "lookups"

# One Stata file per survey year (names as downloaded from CDC)
NHAMCS_FILES = {
    2018: "ED2018-stata.dta",
    2019: "ED2019-stata.dta",
    2020: "ed2020-stata.dta",
    2021: "ed2021-stata.dta",
    2022: "ed2022-stata.dta",
}

# Fields kept from the ~900 in each file (see guide, Phase 2)
KEEP = [
    "PATWT",      # visit weight: every count and median uses it
    "WAITTIME",   # minutes to first provider contact
    "LOV",        # length of visit, minutes
    "BOARDED",    # minutes boarded after admission decision
    "IMMEDR",     # triage level
    "ADMITHOS", "LWBS", "LEFTAMA",   # outcomes
    "ARREMS",     # arrived by ambulance
    "REGION", "MSA",
    "AGE", "SEX", "PAYTYPER",
    "VDAYR", "ARRTIME",
    "RFV1", "DIAG1",
    "HOSPCODE",
    "CSTRATM", "CPSUM",   # survey design variables
]

# Coded fields whose labels become lookup (dimension) tables,
# mapped to the label set each one uses inside the Stata files
LABELLED = {
    "IMMEDR": "IMMEDRF",
    "REGION": "REGIONF",
    "MSA": "MSAF",
    "SEX": "SEXF",
    "PAYTYPER": "PAYTYPERF",
    "VDAYR": "VDAYRF",
    "ARREMS": "ARREMSF",
    "RFV1": "RFVF",
}


def get_engine():
    """PostgreSQL connection, read from .env. Imported only by scripts that need the database."""
    from dotenv import load_dotenv
    from sqlalchemy import create_engine

    load_dotenv(ROOT / ".env")
    return create_engine(
        f"postgresql+psycopg2://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}"
        f"@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"
    )
