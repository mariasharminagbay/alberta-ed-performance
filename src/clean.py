"""Phase 3b: turn coded values into analysis-ready columns and save the cleaned visits.
Run extract.py first."""
import numpy as np
import pandas as pd
from config import PROCESSED

MINUTE_FIELDS = ["WAITTIME", "LOV", "BOARDED"]
MISSING_REASON = {-9: "blank", -8: "unknown", -7: "not applicable"}


def weighted_median(values, weights):
    """Median where each visit counts as many times as its weight (PATWT)."""
    mask = values.notna()
    v, w = values[mask].to_numpy(), weights[mask].to_numpy()
    if len(v) == 0:
        return np.nan
    order = np.argsort(v)
    v, w = v[order], w[order]
    cum = np.cumsum(w)
    return float(v[np.searchsorted(cum, cum[-1] / 2)])


def clean(df):
    out = pd.DataFrame({
        "visit_id": df["visit_id"],
        "year": df["year"],
        "weight": df["PATWT"],
        "hospital_code": df["HOSPCODE"],
    })

    # 1. Minutes: negative codes become empty; keep the reason in a separate column
    for field in MINUTE_FIELDS:
        col = field.lower()
        out[f"{col}_min"] = df[field].where(df[field] >= 0)
        out[f"{col}_missing"] = df[field].map(MISSING_REASON)   # empty when a value exists

    # 2. Triage: levels 1-5, "No triage" (0 and 7), "Unknown" (negative codes)
    out["triage_code"] = df["IMMEDR"]
    out["triage_group"] = np.select(
        [df["IMMEDR"].between(1, 5), df["IMMEDR"].isin([0, 7])],
        ["Level " + df["IMMEDR"].astype(str), "No triage"],
        default="Unknown",
    )

    # 3. Outcome: one per visit, checked in this order
    out["outcome"] = np.select(
        [df["LWBS"] == 1, df["LEFTAMA"] == 1, df["ADMITHOS"] == 1],
        ["Left without being seen", "Left against medical advice", "Admitted"],
        default="Discharged or other",
    )

    # 4. Arrival: ambulance yes/no, hour of day
    out["arrived_by_ambulance"] = df["ARREMS"].map({1: "Yes", 2: "No"}).fillna("Unknown")
    out["arrival_hour"] = (df["ARRTIME"].where(df["ARRTIME"] >= 0) // 100).astype("Int64")
    out["weekday_code"] = df["VDAYR"]

    # 5. Patient: age, CIHI-style age group, sex, payer
    out["age"] = df["AGE"]
    out["age_group"] = pd.cut(df["AGE"], bins=[-1, 19, 44, 64, 200],
                              labels=["0-19", "20-44", "45-64", "65+"]).astype(str)
    out["sex_code"] = df["SEX"]
    out["payer_code"] = df["PAYTYPER"]

    # 6. Place and reason
    out["region_code"] = df["REGION"]
    out["msa_code"] = df["MSA"]
    out["reason_code"] = df["RFV1"]
    out["diagnosis_code"] = df["DIAG1"].where(df["DIAG1"].astype(str) != "-9")

    # 7. Survey design (only for error estimates later)
    out["design_stratum"] = df["CSTRATM"]
    out["design_psu"] = df["CPSUM"]
    return out


def summary(v):
    print("\nCheck by year (weighted unless noted):")
    rows = []
    for year, g in v.groupby("year"):
        w = g["weight"]
        rows.append({
            "year": year,
            "sample visits": len(g),
            "visits (M)": round(w.sum() / 1e6, 1),
            "median wait (min)": weighted_median(g["waittime_min"], w),
            "median visit (min)": weighted_median(g["lov_min"], w),
            "wait missing %": round(100 * w[g["waittime_min"].isna()].sum() / w.sum(), 1),
            "LWBS %": round(100 * w[g["outcome"] == "Left without being seen"].sum() / w.sum(), 1),
            "admitted %": round(100 * w[g["outcome"] == "Admitted"].sum() / w.sum(), 1),
        })
    print(pd.DataFrame(rows).to_string(index=False))

    print("\nTriage bias check: weighted median wait (min), all years")
    for grp, g in v.groupby("triage_group"):
        print(f"  {grp:<10} {weighted_median(g['waittime_min'], g['weight']):>6}   share of visits {100*g['weight'].sum()/v['weight'].sum():.1f}%")


def main():
    raw = pd.read_csv(PROCESSED / "visits_extracted.csv", dtype={"DIAG1": str})
    visits = clean(raw)
    visits.to_csv(PROCESSED / "visits_clean.csv", index=False)
    print(f"{len(visits):,} visits -> data/processed/visits_clean.csv ({visits.shape[1]} columns)")
    summary(visits)


if __name__ == "__main__":
    main()
