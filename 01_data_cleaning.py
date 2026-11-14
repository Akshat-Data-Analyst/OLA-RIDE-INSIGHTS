"""
Step 1 - Data Understanding, Cleaning & Preprocessing  (Ola Ride Insights)

Input : data/OLA_DataSet.xlsx  (sheet 'July')
Output: data/ola_cleaned.csv   (used by the Streamlit app and Power BI)
        data/ola.db            (SQLite database, table `ola_rides`, for SQL practice)

Run:  python 01_data_cleaning.py
"""
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

DATA_DIR = Path(__file__).parent / "data"
RAW_FILE = DATA_DIR / "OLA_DataSet.xlsx"
CLEAN_CSV = DATA_DIR / "ola_cleaned.csv"
DB_FILE = DATA_DIR / "ola.db"


def load_raw() -> pd.DataFrame:
    return pd.read_excel(RAW_FILE, sheet_name="July")


def explore(df: pd.DataFrame) -> None:
    """Initial EDA printed to the console."""
    print("Shape:", df.shape)
    print("\nDtypes:\n", df.dtypes)
    print("\nMissing values:\n", df.isna().sum())
    print("\nDuplicate Booking_IDs:", df["Booking_ID"].duplicated().sum())
    for col in ["Booking_Status", "Vehicle_Type", "Payment_Method"]:
        print(f"\n{col}:\n", df[col].value_counts(dropna=False))


def clean(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # 1. Standardise column names (the 'Vehicle Images' column has a space)
    df.columns = [c.strip().replace(" ", "_") for c in df.columns]

    # 2. Remove exact duplicate bookings (none expected, but be safe)
    df = df.drop_duplicates(subset="Booking_ID")

    # 3. Dates / times.  'Date' already carries a clock time, so split it out.
    df["Date"] = pd.to_datetime(df["Date"]).dt.normalize()
    df["Time"] = df["Time"].astype(str)                       # HH:MM:SS text
    df["Hour"] = pd.to_datetime(df["Time"], format="%H:%M:%S").dt.hour
    df["Day_Name"] = df["Date"].dt.day_name()
    df["Week"] = df["Date"].dt.isocalendar().week.astype(int)

    # 4. Trim / standardise text columns
    text_cols = df.select_dtypes(include=["object", "string"]).columns
    for c in text_cols:
        df[c] = df[c].astype("string").str.strip()

    # 5. Missing values.
    #    NaN in the cancellation / incomplete / payment / rating columns is
    #    *structural* ("not applicable" for that booking status), so we do NOT
    #    impute numbers.  We keep them as NULL so AVG()/COUNT() ignore them,
    #    and only add readable labels for the reason columns.
    df["Canceled_Rides_by_Customer"] = df["Canceled_Rides_by_Customer"].fillna("Not Applicable")
    df["Canceled_Rides_by_Driver"] = df["Canceled_Rides_by_Driver"].fillna("Not Applicable")
    df["Incomplete_Rides_Reason"] = df["Incomplete_Rides_Reason"].fillna("Not Applicable")
    df["Incomplete_Rides"] = df["Incomplete_Rides"].fillna("Not Applicable")
    df["Payment_Method"] = df["Payment_Method"].fillna("Not Applicable")

    # 6. Numeric types
    for c in ["V_TAT", "C_TAT", "Driver_Ratings", "Customer_Rating"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["Booking_Value"] = pd.to_numeric(df["Booking_Value"], errors="coerce")
    df["Ride_Distance"] = pd.to_numeric(df["Ride_Distance"], errors="coerce")

    # 7. Derived features
    df["Is_Success"] = (df["Booking_Status"] == "Success").astype(int)
    df["Is_Cancelled"] = df["Booking_Status"].str.startswith("Canceled").astype(int)
    df["Revenue"] = np.where(df["Is_Success"] == 1, df["Booking_Value"], 0)
    df["Price_per_Km"] = np.where(
        df["Ride_Distance"] > 0, df["Booking_Value"] / df["Ride_Distance"], np.nan
    ).round(2)

    # 8. Sanity checks (anomaly detection for the 'fraud / anomaly' use case)
    assert df["Booking_ID"].is_unique
    assert df["Driver_Ratings"].dropna().between(1, 5).all()
    assert df["Customer_Rating"].dropna().between(1, 5).all()
    assert (df["Booking_Value"] >= 0).all()

    return df.sort_values(["Date", "Time"]).reset_index(drop=True)


def save(df: pd.DataFrame) -> None:
    df.to_csv(CLEAN_CSV, index=False)

    out = df.copy()
    out["Date"] = out["Date"].dt.strftime("%Y-%m-%d")        # SQLite has no date type
    with sqlite3.connect(DB_FILE) as con:
        out.to_sql("ola_rides", con, if_exists="replace", index=False)
    print(f"Saved {CLEAN_CSV.name} and {DB_FILE.name}  ({len(out):,} rows)")


if __name__ == "__main__":
    raw = load_raw()
    explore(raw)
    cleaned = clean(raw)
    save(cleaned)
