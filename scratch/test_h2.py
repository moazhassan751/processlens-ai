import pandas as pd
import io

FORMULA_PREFIXES = ("=", "+", "-", "@")

def _is_numeric(val):
    if isinstance(val, (int, float, complex)) and not isinstance(val, bool):
        return True
    try:
        float(str(val).strip())
        return True
    except (ValueError, TypeError):
        return False

def sanitize_cell_value(val, is_ts=False):
    if val is None or pd.isna(val) or is_ts:
        return val
    if isinstance(val, (int, float, complex)) and not isinstance(val, bool):
        return val
    if isinstance(val, str):
        trimmed = val.strip()
        if trimmed.startswith(FORMULA_PREFIXES):
            if _is_numeric(trimmed):
                return val
            return f"'{val}"
    return val

def sanitize_dataframe_for_csv(df: pd.DataFrame) -> pd.DataFrame:
    df_clean = df.copy()
    for col in df_clean.columns:
        col_lower = str(col).lower().strip()
        is_ts = "timestamp" in col_lower or pd.api.types.is_datetime64_any_dtype(df_clean[col])
        if pd.api.types.is_numeric_dtype(df_clean[col]):
            continue
        if is_ts:
            continue
        df_clean[col] = df_clean[col].apply(lambda v: sanitize_cell_value(v, is_ts=is_ts))
    return df_clean

if __name__ == "__main__":
    df = pd.DataFrame({
        "case_id": ['=cmd|"/C calc"!A1', "+CASE-2", "-CASE-3", "@CASE-4", "CASE-5"],
        "activity": ["Submitted", "-Special Review", "+Audit Step", "@Auto Approve", "Reviewed"],
        "timestamp": ["2026-09-01 10:00:00", "2026-09-01 11:00:00", "2026-09-01 12:00:00", "2026-09-01 13:00:00", "2026-09-01 14:00:00"],
        "resource": ["Alice", "=cmd", "-User", "+Admin", "@System"],
        "numeric_val": [-5, 10, -3.14, 0, 42],
    })

    cleaned = sanitize_dataframe_for_csv(df)
    buf = io.StringIO()
    cleaned.to_csv(buf, index=False)
    csv_text = buf.getvalue()
    print("CSV Text Output:")
    print(csv_text)

    # Check raw lines
    for line in csv_text.splitlines():
        if "calc" in line:
            print("Malicious line in CSV:", line)
            assert line.startswith("'=cmd") or ',"\'=cmd' in line or '\'=cmd' in line
            assert not line.startswith("=cmd")

    print("\nCSV SERIALIZATION VERIFIED!")
