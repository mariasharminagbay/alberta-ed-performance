"""Phase 3a: read the five NHAMCS Stata files, keep the needed fields, stack them,
and save the code labels as lookup tables."""
import pandas as pd
from config import RAW_NHAMCS, PROCESSED, LOOKUPS, NHAMCS_FILES, KEEP, LABELLED


def read_year(year, filename):
    with pd.io.stata.StataReader(RAW_NHAMCS / filename) as reader:
        df = reader.read(convert_categoricals=False)   # keep numeric codes, not text labels
        labels = reader.value_labels()                  # {label set name: {code: text}}

    missing = [c for c in KEEP if c not in df.columns]
    if missing:
        raise ValueError(f"{year}: fields not found: {missing}")

    df = df[KEEP].copy()
    df.insert(0, "year", year)
    df.insert(0, "visit_id", [year * 100000 + i + 1 for i in range(len(df))])
    year_labels = {}
    for field, label_set in LABELLED.items():
        if label_set not in labels:
            raise ValueError(f"{year}: label set {label_set} for {field} not found")
        year_labels[field] = labels[label_set]
    return df, year_labels


def build_lookups(all_labels):
    """One table per coded field: code, label. If a label changed between years,
    the latest year wins and the change is reported."""
    LOOKUPS.mkdir(parents=True, exist_ok=True)
    for field in LABELLED:
        merged = {}
        changed = 0
        for year in sorted(all_labels):
            for code, text in all_labels[year][field].items():
                if code in merged and merged[code] != text:
                    changed += 1
                merged[code] = text
        table = pd.DataFrame(sorted(merged.items()), columns=["code", "label"])
        table.to_csv(LOOKUPS / f"{field.lower()}.csv", index=False)
        note = f", {changed} labels reworded between years (latest kept)" if changed else ""
        print(f"  lookup {field.lower()}.csv: {len(table)} codes{note}")


def main():
    frames, all_labels = [], {}
    for year, filename in NHAMCS_FILES.items():
        df, labels = read_year(year, filename)
        frames.append(df)
        all_labels[year] = labels
        print(f"{year}: {len(df):,} visits read")

    visits = pd.concat(frames, ignore_index=True)
    PROCESSED.mkdir(parents=True, exist_ok=True)
    visits.to_csv(PROCESSED / "visits_extracted.csv", index=False)
    print(f"Total: {len(visits):,} visits -> data/processed/visits_extracted.csv")
    build_lookups(all_labels)


if __name__ == "__main__":
    main()
