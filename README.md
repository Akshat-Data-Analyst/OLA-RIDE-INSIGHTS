# OLA Ride Insights

 **Live Streamlit App:** [Click Here to View](https://ola-ride-insights-m7eg452tgwnfmggzdi7yx2.streamlit.app/)


# Ola Ride Insights

## Files
| File | Purpose |
|---|---|
| `01_data_cleaning.py` | EDA + cleaning; needs `data/OLA_DataSet.xlsx`; writes `data/ola_cleaned.csv` (+ `data/ola.db`) |
| `02_sql_queries.sql` | The 10 SQL questions (SQLite / MySQL compatible) |
| `app.py` | Streamlit app (Dashboard, SQL Insights, Data Explorer, Power BI embed) |
| `data/ola_cleaned.csv` | Cleaned data - this is what the app and Power BI read |

## Run locally
```
pip install -r requirements.txt
python 01_data_cleaning.py      # only if you change the raw Excel
streamlit run app.py
```

## Deploy on Streamlit Community Cloud
1. Push this folder to a GitHub repo (keep `data/ola_cleaned.csv`, 26 MB, under GitHub's 100 MB limit).
2. Go to share.streamlit.io -> New app -> pick the repo, branch, main file `app.py`.
3. Deploy. The app builds its SQL database in memory from the CSV, so no external DB is needed.

## Power BI
Import `data/ola_cleaned.csv` (or connect MySQL), build the 5 views listed in the project brief
(Overall, Vehicle Type, Revenue, Cancellation, Ratings), publish, then paste the
"Publish to web" link into the app's Power BI page.
