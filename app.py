import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta

st.set_page_config(page_title="LCDS Impact Tracker", page_icon="🌍", layout="wide")

# --- LOAD DATA ---
@st.cache_data
def load_data():
    try:
        df = pd.read_csv("data/lcds_publications.csv")
        df['Date Available Online'] = pd.to_datetime(df['Date Available Online'])
        return df
    except FileNotFoundError:
        return pd.DataFrame()

df = load_data()

# --- SIDEBAR FILTERS ---
st.sidebar.header("🔍 Filters")
if df.empty:
    st.error("Data not found. Please run the scraper.")
    st.stop()

# Time Filter
time_period = st.sidebar.radio(
    "Select Period", 
    ["All Time (2019+)", "Last 5 Years", "Last Year", "Last Month", "Last Week"]
)
now = datetime.now()
if time_period == "Last Year": start = now - timedelta(days=365)
elif time_period == "Last Month": start = now - timedelta(days=30)
elif time_period == "Last Week": start = now - timedelta(days=7)
elif time_period == "Last 5 Years": start = now - timedelta(days=5*365)
else: start = pd.to_datetime("2019-01-01")

df_filtered = df[df['Date Available Online'] >= start].copy()

# --- DASHBOARD ---
st.title("🌍 LCDS Publications Tracker")
st.markdown(f"**Period:** {time_period} | **Records:** {len(df_filtered)}")

# METRICS
c1, c2, c3, c4 = st.columns(4)
c1.metric("Total Papers", len(df_filtered))
c2.metric("Total Citations", int(df_filtered['Citation Count'].sum()))
c3.metric("Top Field", df_filtered['Journal Area'].mode()[0] if not df_filtered.empty else "N/A")
c4.metric("Active Authors", df_filtered['LCDS Author'].nunique())

st.divider()

# --- VISUALS ---
col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("📊 Citation Impact by Journal Area")
    # Groups by Area and sums citations
    df_area = df_filtered.groupby('Journal Area')['Citation Count'].sum().reset_index()
    # Donut Chart for Impact
    fig = px.pie(df_area, values='Citation Count', names='Journal Area', hole=0.4, 
                 title="Total Citations per Field (Impact)",
                 color_discrete_sequence=px.colors.qualitative.Prism)
    fig.update_traces(textposition='inside', textinfo='percent+label')
    st.plotly_chart(fig, use_container_width=True)

with col2:
    st.subheader("🏆 Top Journals")
    st.dataframe(df_filtered['Journal Name'].value_counts().head(10), use_container_width=True)

# --- DATA TABLE ---
st.subheader("📄 Publication List")
st.dataframe(
    df_filtered,
    column_config={
        "DOI": st.column_config.LinkColumn("Link"),
        "Date Available Online": st.column_config.DateColumn("Date")
    },
    hide_index=True,
    use_container_width=True
)

# CSV Download
csv = df_filtered.to_csv(index=False).encode('utf-8')
st.download_button("📥 Download CSV", csv, "lcds_data.csv", "text/csv")
