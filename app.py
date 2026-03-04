import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta

st.set_page_config(page_title="LCDS Impact Tracker", page_icon="🌍", layout="wide")

@st.cache_data
def load_data():
    try:
        df = pd.read_csv("data/lcds_publications.csv")
        df['Date Available Online'] = pd.to_datetime(df['Date Available Online'], errors='coerce')
        return df
    except FileNotFoundError:
        return pd.DataFrame()

df = load_data()

# --- SIDEBAR ---
st.sidebar.header("🔍 Filters")
if df.empty:
    st.error("Data not found. Please run the scraper.")
    st.stop()

# Time Filter
time_filter = st.sidebar.radio(
    "Select Period", 
    ["All Time", "Last 5 Years", "Last Year", "Last Month", "Last Week"]
)
now = datetime.now()
if time_filter == "Last Year": start = now - timedelta(days=365)
elif time_filter == "Last Month": start = now - timedelta(days=30)
elif time_filter == "Last Week": start = now - timedelta(days=7)
elif time_filter == "Last 5 Years": start = now - timedelta(days=5*365)
else: start = pd.to_datetime("2019-01-01")

# Pub Type Filter
type_filter = st.sidebar.multiselect(
    "Publication Type",
    options=df['Publication Type'].unique(),
    default=df['Publication Type'].unique()
)

# Apply Filters
df_filtered = df[
    (df['Date Available Online'] >= start) & 
    (df['Publication Type'].isin(type_filter))
].copy()

# --- DASHBOARD ---
st.title("🌍 LCDS Publications Tracker")
st.markdown(f"**Viewing:** {time_filter} | **Records:** {len(df_filtered)}")

# METRICS
c1, c2, c3, c4 = st.columns(4)
c1.metric("Total Output", len(df_filtered))
c2.metric("Preprints", len(df_filtered[df_filtered['Publication Type'] == 'Preprint']))
c3.metric("Recent Citations", int(df_filtered['Citation Count'].sum()))
c4.metric("Active Authors", df_filtered['LCDS Author'].nunique())

st.divider()

# --- CHARTS ---
col1, col2 = st.columns(2)

with col1:
    st.subheader("📊 Impact by Field")
    # Clean up "Pending" fields for the chart
    df_chart = df_filtered[df_filtered['Journal Area'] != 'Pending (Recent)']
    if not df_chart.empty:
        fig = px.pie(df_chart, values='Citation Count', names='Journal Area', hole=0.4,
                     title="Citations per Field",
                     color_discrete_sequence=px.colors.qualitative.Prism)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No citation data for this selection yet.")

with col2:
    st.subheader("📑 Type Distribution")
    fig2 = px.pie(df_filtered, names='Publication Type', hole=0.4,
                  title="Journals vs Preprints",
                  color_discrete_sequence=px.colors.qualitative.Safe)
    st.plotly_chart(fig2, use_container_width=True)

# --- DATA TABLE ---
st.subheader("📄 Latest Publications")
st.dataframe(
    df_filtered,
    column_config={
        "DOI": st.column_config.LinkColumn("Link"),
        "Date Available Online": st.column_config.DateColumn("Date", format="YYYY-MM-DD"),
        "Citation Count": st.column_config.NumberColumn("Cites"),
    },
    hide_index=True,
    use_container_width=True
)

csv = df_filtered.to_csv(index=False).encode('utf-8')
st.download_button("📥 Download CSV", csv, "lcds_data.csv", "text/csv")
