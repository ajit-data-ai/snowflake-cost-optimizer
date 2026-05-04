"""
Streamlit cost dashboard for Snowflake.
Run: streamlit run dashboard/app.py
"""
import os
import streamlit as st
import pandas as pd
import plotly.express as px
import snowflake.connector
from profiler.query_profiler import QueryProfiler

st.set_page_config(page_title="Snowflake Cost Optimizer", layout="wide")
st.title("Snowflake Cost Optimizer")

@st.cache_resource
def get_conn():
    return snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        password=os.environ["SNOWFLAKE_PASSWORD"],
        warehouse=os.environ.get("SNOWFLAKE_WAREHOUSE", "COMPUTE_WH"),
        role=os.environ.get("SNOWFLAKE_ROLE", "SYSADMIN"),
    )

conn = get_conn()
profiler = QueryProfiler(conn)

tab1, tab2 = st.tabs(["Credit burn by warehouse", "Top queries"])

with tab1:
    lookback = st.slider("Lookback days", 7, 90, 30)
    df = profiler.warehouse_credit_burn(lookback_days=lookback)
    if not df.empty:
        fig = px.bar(df, x="DAY", y="CREDITS_USED", color="WAREHOUSE_NAME",
                     title="Daily credit consumption by warehouse")
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(df, use_container_width=True)

with tab2:
    top_n = st.slider("Top N queries", 10, 100, 25)
    df2 = profiler.top_credit_consumers(lookback_days=30, top_n=top_n)
    if not df2.empty:
        st.dataframe(
            df2[["QUERY_TEXT_PREVIEW", "USER_NAME", "WAREHOUSE_NAME",
                 "CREDITS_USED", "EXECUTION_TIME_SECONDS",
                 "PARTITION_SCAN_PCT", "SPILL_TO_REMOTE_STORAGE_MB", "recommendations"]],
            use_container_width=True,
        )
