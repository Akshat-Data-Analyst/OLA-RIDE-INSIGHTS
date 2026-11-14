"""
Ola Ride Insights - Streamlit app

Pages
  1. Dashboard     : interactive charts in 5 views (Overall, Vehicle Type, Revenue,
                     Cancellation, Ratings) + KPIs and sidebar filters
  2. SQL Insights  : the 10 project SQL questions, run live on the data
  3. Data Explorer : filter / search / download the raw bookings
  4. Power BI      : embed your published Power BI report

Run locally :  streamlit run app.py
"""
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(page_title="Ola Ride Insights", page_icon="🚖", layout="wide")

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
YELLOW, BLACK = "#C6D600", "#111111"
PALETTE = px.colors.qualitative.Safe

# --------------------------------------------------------------------------
# SQL queries (project questions)
# --------------------------------------------------------------------------
QUERIES = {
    'Q1. Retrieve all successful bookings': """SELECT *
FROM ola_rides
WHERE Booking_Status = 'Success'""",
    'Q2. Average ride distance for each vehicle type': """SELECT Vehicle_Type,
       ROUND(AVG(Ride_Distance), 2) AS Avg_Ride_Distance
FROM ola_rides
WHERE Booking_Status = 'Success'          -- cancelled rides have 0 km
GROUP BY Vehicle_Type
ORDER BY Avg_Ride_Distance DESC""",
    'Q3. Total number of cancelled rides by customers': """SELECT COUNT(*) AS Cancelled_By_Customers
FROM ola_rides
WHERE Booking_Status = 'Canceled by Customer'""",
    'Q4. Top 5 customers who booked the highest number of rides': """SELECT Customer_ID,
       COUNT(Booking_ID) AS Total_Rides
FROM ola_rides
GROUP BY Customer_ID
ORDER BY Total_Rides DESC, Customer_ID
LIMIT 5""",
    'Q5. Rides cancelled by drivers due to personal & car related issues': """SELECT COUNT(*) AS Driver_Cancels_Personal_Car_Issue
FROM ola_rides
WHERE Canceled_Rides_by_Driver = 'Personal & Car related issue'""",
    'Q6. Max and min driver ratings for Prime Sedan bookings': """SELECT MAX(Driver_Ratings) AS Max_Driver_Rating,
       MIN(Driver_Ratings) AS Min_Driver_Rating
FROM ola_rides
WHERE Vehicle_Type = 'Prime Sedan'
  AND Driver_Ratings IS NOT NULL""",
    'Q7. All rides where payment was made using UPI': """SELECT *
FROM ola_rides
WHERE Payment_Method = 'UPI'""",
    'Q8. Average customer rating per vehicle type': """SELECT Vehicle_Type,
       ROUND(AVG(Customer_Rating), 2) AS Avg_Customer_Rating
FROM ola_rides
WHERE Customer_Rating IS NOT NULL
GROUP BY Vehicle_Type
ORDER BY Avg_Customer_Rating DESC""",
    'Q9. Total booking value of rides completed successfully': """SELECT SUM(Booking_Value) AS Total_Booking_Value
FROM ola_rides
WHERE Booking_Status = 'Success'""",
    'Q10. All incomplete rides along with the reason': """SELECT Booking_ID, Customer_ID, Vehicle_Type, Pickup_Location, Drop_Location,
       Incomplete_Rides, Incomplete_Rides_Reason
FROM ola_rides
WHERE Incomplete_Rides = 'Yes'""",
}


# --------------------------------------------------------------------------
# Cleaning
# --------------------------------------------------------------------------
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



# --------------------------------------------------------------------------
# Data layer
# --------------------------------------------------------------------------
@st.cache_data(show_spinner="Loading data (first run can take ~1 minute) ...")
def load_data() -> pd.DataFrame:
    """Use a cleaned CSV if present anywhere in the repo, else clean OLA_DataSet.xlsx."""
    for p in sorted(BASE_DIR.rglob("ola_cleaned.csv*")):
        if p.is_file():
            return pd.read_csv(p, parse_dates=["Date"])
    for p in sorted(BASE_DIR.rglob("OLA_DataSet.xlsx")):
        if p.is_file():
            return clean(pd.read_excel(p, sheet_name="July"))
    st.error(
        "Data file not found. Upload `OLA_DataSet.xlsx` to your GitHub repo "
        f"(next to app.py). Files in repo root: {sorted(x.name for x in BASE_DIR.iterdir())}"
    )
    st.stop()


@st.cache_resource(show_spinner="Building SQL database ...")
def get_connection() -> sqlite3.Connection:
    """In-memory SQLite DB so the app deploys without an external database."""
    df = load_data().copy()
    df["Date"] = df["Date"].dt.strftime("%Y-%m-%d")
    con = sqlite3.connect(":memory:", check_same_thread=False)
    df.to_sql("ola_rides", con, index=False)
    return con


def parse_sql_file() -> dict:
    return QUERIES


df_all = load_data()


# --------------------------------------------------------------------------
# Sidebar: navigation + global filters
# --------------------------------------------------------------------------
st.sidebar.title("🚖 Ola Ride Insights")
page = st.sidebar.radio(
    "Go to", ["Dashboard", "SQL Insights", "Data Explorer", "Power BI"]
)

st.sidebar.markdown("---")
st.sidebar.subheader("Filters (Dashboard)")
min_d, max_d = df_all["Date"].min().date(), df_all["Date"].max().date()
date_range = st.sidebar.date_input(
    "Date range", (min_d, max_d), min_value=min_d, max_value=max_d
)
vehicles = st.sidebar.multiselect(
    "Vehicle type", sorted(df_all["Vehicle_Type"].unique()),
    default=sorted(df_all["Vehicle_Type"].unique()),
)
statuses = st.sidebar.multiselect(
    "Booking status", sorted(df_all["Booking_Status"].unique()),
    default=sorted(df_all["Booking_Status"].unique()),
)

if isinstance(date_range, tuple) and len(date_range) == 2:
    start, end = date_range
else:                                   # user has picked only one date so far
    start = end = date_range[0] if isinstance(date_range, tuple) else date_range

df = df_all[
    df_all["Date"].between(pd.Timestamp(start), pd.Timestamp(end))
    & df_all["Vehicle_Type"].isin(vehicles)
    & df_all["Booking_Status"].isin(statuses)
]
success = df[df["Booking_Status"] == "Success"]


def style(fig, height=380):
    fig.update_layout(height=height, margin=dict(l=10, r=10, t=50, b=10))
    return fig


# --------------------------------------------------------------------------
# Page 1: Dashboard
# --------------------------------------------------------------------------
def page_dashboard():
    st.title("🚖 Ola Ride Insights Dashboard")
    st.caption(f"July 2024 | {len(df):,} bookings after filters")

    if df.empty:
        st.warning("No data for the selected filters.")
        return

    # KPIs
    total = len(df)
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Total Bookings", f"{total:,}")
    k2.metric("Success Rate", f"{len(success) / total:.1%}")
    k3.metric("Revenue (Success)", f"₹{success['Booking_Value'].sum():,.0f}")
    k4.metric("Avg Distance (km)", f"{success['Ride_Distance'].mean():.1f}" if len(success) else "-")
    k5.metric("Cancellation Rate", f"{df['Is_Cancelled'].mean():.1%}")

    tabs = st.tabs(["Overall", "Vehicle Type", "Revenue", "Cancellation", "Ratings"])

    # ---- Overall ---------------------------------------------------------
    with tabs[0]:
        c1, c2 = st.columns(2)
        daily = df.groupby("Date").size().reset_index(name="Rides")
        c1.plotly_chart(
            style(px.line(daily, x="Date", y="Rides", markers=True,
                          title="Ride Volume Over Time (bookings per day)",
                          color_discrete_sequence=[BLACK])),
        )
        status = df["Booking_Status"].value_counts().reset_index()
        status.columns = ["Booking_Status", "Count"]
        c2.plotly_chart(
            style(px.pie(status, names="Booking_Status", values="Count", hole=0.45,
                         title="Booking Status Breakdown",
                         color_discrete_sequence=PALETTE)),
        )
        hourly = df.groupby("Hour").size().reset_index(name="Rides")
        st.plotly_chart(
            style(px.bar(hourly, x="Hour", y="Rides",
                         title="Peak Demand Hours (use for driver allocation)",
                         color_discrete_sequence=[YELLOW]), 320),
        )

    # ---- Vehicle type ------------------------------------------------------
    with tabs[1]:
        c1, c2 = st.columns(2)
        dist = (success.groupby("Vehicle_Type")["Ride_Distance"].sum()
                .nlargest(5).reset_index())
        c1.plotly_chart(
            style(px.bar(dist, x="Vehicle_Type", y="Ride_Distance", text_auto=".3s",
                         title="Top 5 Vehicle Types by Total Ride Distance (km)",
                         color="Vehicle_Type", color_discrete_sequence=PALETTE)),
        )
        avg_d = (success.groupby("Vehicle_Type")["Ride_Distance"].mean()
                 .round(2).reset_index())
        c2.plotly_chart(
            style(px.bar(avg_d, x="Vehicle_Type", y="Ride_Distance", text_auto=True,
                         title="Average Ride Distance by Vehicle Type (km)",
                         color="Vehicle_Type", color_discrete_sequence=PALETTE)),
        )

    # ---- Revenue ----------------------------------------------------------
    with tabs[2]:
        c1, c2 = st.columns(2)
        pay = (success.groupby("Payment_Method")["Booking_Value"].sum()
               .reset_index().sort_values("Booking_Value", ascending=False))
        c1.plotly_chart(
            style(px.bar(pay, x="Payment_Method", y="Booking_Value", text_auto=".3s",
                         title="Revenue by Payment Method (₹)",
                         color="Payment_Method", color_discrete_sequence=PALETTE)),
        )
        top_c = (success.groupby("Customer_ID")["Booking_Value"].sum()
                 .nlargest(5).reset_index())
        c2.plotly_chart(
            style(px.bar(top_c, x="Booking_Value", y="Customer_ID", orientation="h",
                         text_auto=True, title="Top 5 Customers by Total Booking Value (₹)",
                         color_discrete_sequence=[BLACK])
                  .update_yaxes(categoryorder="total ascending")),
        )
        per_day = success.groupby("Date")["Ride_Distance"].sum().reset_index()
        st.plotly_chart(
            style(px.bar(per_day, x="Date", y="Ride_Distance",
                         title="Ride Distance Distribution Per Day (total km)",
                         color_discrete_sequence=[YELLOW]), 320),
        )

    # ---- Cancellation ------------------------------------------------------
    with tabs[3]:
        c1, c2 = st.columns(2)
        cust = df[df["Canceled_Rides_by_Customer"] != "Not Applicable"]
        cust = cust["Canceled_Rides_by_Customer"].value_counts().reset_index()
        cust.columns = ["Reason", "Count"]
        c1.plotly_chart(
            style(px.bar(cust, x="Count", y="Reason", orientation="h", text_auto=True,
                         title="Cancelled Rides - Customer Reasons",
                         color_discrete_sequence=[BLACK])
                  .update_yaxes(categoryorder="total ascending")),
        )
        drv = df[df["Canceled_Rides_by_Driver"] != "Not Applicable"]
        drv = drv["Canceled_Rides_by_Driver"].value_counts().reset_index()
        drv.columns = ["Reason", "Count"]
        c2.plotly_chart(
            style(px.bar(drv, x="Count", y="Reason", orientation="h", text_auto=True,
                         title="Cancelled Rides - Driver Reasons",
                         color_discrete_sequence=[YELLOW])
                  .update_yaxes(categoryorder="total ascending")),
        )
        inc = df[df["Incomplete_Rides"] == "Yes"]["Incomplete_Rides_Reason"].value_counts()
        if not inc.empty:
            inc = inc.reset_index()
            inc.columns = ["Reason", "Count"]
            st.plotly_chart(
                style(px.pie(inc, names="Reason", values="Count", hole=0.4,
                             title="Incomplete Rides - Reasons",
                             color_discrete_sequence=PALETTE), 320),
            )

    # ---- Ratings -----------------------------------------------------------
    with tabs[4]:
        rated = success.dropna(subset=["Driver_Ratings", "Customer_Rating"])
        c1, c2 = st.columns(2)
        c1.plotly_chart(
            style(px.histogram(rated, x="Driver_Ratings", nbins=20,
                               title="Driver Ratings Distribution",
                               color_discrete_sequence=[BLACK])),
        )
        c2.plotly_chart(
            style(px.histogram(rated, x="Customer_Rating", nbins=20,
                               title="Customer Ratings Distribution",
                               color_discrete_sequence=[YELLOW])),
        )
        c3, c4 = st.columns(2)
        avg_r = (rated.groupby("Vehicle_Type")[["Customer_Rating", "Driver_Ratings"]]
                 .mean().round(2).reset_index())
        c3.plotly_chart(
            style(px.bar(avg_r, x="Vehicle_Type", y="Customer_Rating", text_auto=True,
                         title="Average Customer Rating by Vehicle Type",
                         color="Vehicle_Type", color_discrete_sequence=PALETTE)
                  .update_yaxes(range=[0, 5])),
        )
        c4.plotly_chart(
            style(px.density_heatmap(rated, x="Customer_Rating", y="Driver_Ratings",
                                     nbinsx=20, nbinsy=20, color_continuous_scale="YlGnBu",
                                     title="Customer vs. Driver Ratings")),
        )


# --------------------------------------------------------------------------
# Page 2: SQL Insights
# --------------------------------------------------------------------------
def page_sql():
    st.title("🧮 SQL Insights")
    st.caption("Queries run live against the cleaned data (table `ola_rides`).")
    queries = parse_sql_file()
    choice = st.selectbox("Choose a question", list(queries))
    query = queries[choice]
    st.code(query, language="sql")

    result = pd.read_sql_query(query, get_connection())
    st.write(f"**{len(result):,} row(s)**")
    st.dataframe(result, height=min(450, 38 * (len(result) + 1)))
    st.download_button("Download result as CSV", result.to_csv(index=False),
                       file_name="query_result.csv", mime="text/csv")

    with st.expander("Run your own SQL"):
        custom = st.text_area("SELECT ... FROM ola_rides ...",
                              "SELECT Vehicle_Type, COUNT(*) AS rides\nFROM ola_rides\nGROUP BY Vehicle_Type")
        if st.button("Run query"):
            if not custom.strip().lower().startswith("select"):
                st.error("Only SELECT statements are allowed.")
            else:
                try:
                    st.dataframe(pd.read_sql_query(custom, get_connection()))
                except Exception as exc:          # show SQL errors to the user
                    st.error(f"Query failed: {exc}")


# --------------------------------------------------------------------------
# Page 3: Data Explorer
# --------------------------------------------------------------------------
def page_explorer():
    st.title("🔎 Data Explorer")
    search = st.text_input("Search Booking ID / Customer ID / Pickup / Drop location")
    view = df
    if search:
        mask = False
        for col in ["Booking_ID", "Customer_ID", "Pickup_Location", "Drop_Location"]:
            mask = mask | view[col].astype(str).str.contains(search, case=False, na=False)
        view = view[mask]
    cols = [c for c in view.columns if c != "Vehicle_Images"]
    st.write(f"**{len(view):,} rows** (sidebar filters also apply)")
    st.dataframe(view[cols].head(2000), height=500)
    st.download_button("Download filtered data", view[cols].to_csv(index=False),
                       file_name="ola_filtered.csv", mime="text/csv")
    st.caption("Showing the first 2,000 rows; the download contains all matches.")


# --------------------------------------------------------------------------
# Page 4: Power BI embed
# --------------------------------------------------------------------------
def page_powerbi():
    st.title("📊 Power BI Report")
    st.write(
        "In Power BI Service: **File → Embed report → Publish to web (public)**, "
        "copy the link and paste it below."
    )
    url = st.text_input("Power BI embed URL (https://app.powerbi.com/view?r=...)")
    if url.startswith("https://app.powerbi.com/"):
        components.html(
            f'<iframe title="Ola Ride Insights" width="100%" height="700" src="{url}" '
            'frameborder="0" allowfullscreen="true"></iframe>',
            height=720,
        )
    elif url:
        st.error("Please paste a valid https://app.powerbi.com/ link.")
    else:
        st.info("No report linked yet. The Dashboard page already contains all required visuals.")


{"Dashboard": page_dashboard, "SQL Insights": page_sql,
 "Data Explorer": page_explorer, "Power BI": page_powerbi}[page]()
