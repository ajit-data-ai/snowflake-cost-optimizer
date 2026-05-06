# Snowflake Cost Optimizer

Toolkit for identifying and reducing Snowflake credit spend. Includes a query profiler that surfaces the top credit consumers with optimization recommendations, a clustering key advisor, auto-suspend SQL scripts, and a Streamlit dashboard.

## Tools

| Tool | What it does |
|---|---|
| `profiler/query_profiler.py` | Reads `QUERY_HISTORY` — top N queries by credit spend with per-query recommendations |
| `advisor/clustering_advisor.py` | Identifies tables needing clustering keys from predicate analysis |
| `scripts/auto_suspend.sql` | Sets auto-suspend + resource monitor policies on all warehouses |
| `dashboard/app.py` | Streamlit app: credit burn over time + query drilldown |

## Quick Start

```bash
pip install snowflake-connector-python pandas plotly streamlit

export SNOWFLAKE_ACCOUNT="myorg-myaccount"
export SNOWFLAKE_USER="analyst"
export SNOWFLAKE_PASSWORD="..."

# Run the Streamlit dashboard
streamlit run dashboard/app.py

# Or run the profiler from the CLI
python -c "
import snowflake.connector, os
from profiler.query_profiler import QueryProfiler
conn = snowflake.connector.connect(account=os.environ['SNOWFLAKE_ACCOUNT'], user=os.environ['SNOWFLAKE_USER'], password=os.environ['SNOWFLAKE_PASSWORD'])
df = QueryProfiler(conn).top_credit_consumers(lookback_days=7)
print(df[['QUERY_TEXT_PREVIEW','CREDITS_USED','recommendations']].to_string())
"
```

## Common findings

**High partition scan %** — adding a cluster key on the most-filtered column typically reduces scan by 60–80% and cuts credit spend proportionally.

**Spill to remote storage** — queries spilling to S3 are 10–100× slower and burn credits on data transfer. Fix by increasing warehouse size for that query, reducing `LIMIT`-less subqueries, or splitting joins.

**Warehouse idle time** — `AUTO_SUSPEND = 60` on all warehouses is the single cheapest win. A warehouse suspended for 23 hours instead of running idle saves ~96% of its compute cost.
