"""
Warehouse analyzer: right-sizing recommendations based on WAREHOUSE_METERING_HISTORY.

Checks for under-utilised warehouses (avg queue < 0.5), always-queuing warehouses
(avg queue > 2 → should scale up or use multi-cluster), and warehouses that should
be consolidated.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date, timedelta
from typing import List, Optional
import pandas as pd
import snowflake.connector


@dataclass
class WarehouseRecommendation:
    warehouse_name: str
    current_size: str
    avg_credits_per_hour: float
    max_queue_length: float
    avg_queue_length: float
    action: str          # "downsize" | "upsize" | "multi-cluster" | "ok" | "suspend"
    rationale: str


class WarehouseAnalyzer:
    def __init__(self, conn: snowflake.connector.SnowflakeConnection) -> None:
        self._conn = conn

    def analyse_all(self, lookback_days: int = 14) -> List[WarehouseRecommendation]:
        start = (date.today() - timedelta(days=lookback_days)).isoformat()

        # Credits and hours per warehouse
        metering_df = pd.read_sql(f"""
            SELECT
                warehouse_name,
                SUM(credits_used)           AS total_credits,
                COUNT(DISTINCT start_time)  AS metered_hours,
                ROUND(SUM(credits_used) / NULLIF(COUNT(DISTINCT start_time), 0), 4)
                                            AS avg_credits_per_hour
            FROM snowflake.account_usage.warehouse_metering_history
            WHERE start_time >= '{start}'
            GROUP BY 1
        """, self._conn)

        # Queue depth from WAREHOUSE_EVENTS_HISTORY
        queue_df = pd.read_sql(f"""
            SELECT
                warehouse_name,
                AVG(queued_load)    AS avg_queue,
                MAX(queued_load)    AS max_queue
            FROM snowflake.account_usage.warehouse_events_history
            WHERE timestamp >= '{start}'
            GROUP BY 1
        """, self._conn)

        # Current warehouse sizes
        size_df = pd.read_sql("SHOW WAREHOUSES", self._conn)
        if not size_df.empty:
            size_df = size_df[["name", "size"]].rename(columns={"name": "warehouse_name", "size": "current_size"})

        merged = metering_df.merge(queue_df, on="warehouse_name", how="left")
        merged = merged.merge(size_df, on="warehouse_name", how="left") if not size_df.empty else merged
        merged["avg_queue"] = merged.get("avg_queue", pd.Series(dtype=float)).fillna(0)
        merged["max_queue"] = merged.get("max_queue", pd.Series(dtype=float)).fillna(0)
        merged["current_size"] = merged.get("current_size", pd.Series(dtype=str)).fillna("UNKNOWN")

        return [self._recommend(row) for _, row in merged.iterrows()]

    def _recommend(self, row: pd.Series) -> WarehouseRecommendation:
        avg_q = float(row.get("avg_queue", 0) or 0)
        max_q = float(row.get("max_queue", 0) or 0)
        credits_hr = float(row.get("avg_credits_per_hour", 0) or 0)

        if credits_hr < 0.1 and avg_q < 0.1:
            action = "suspend"
            rationale = "Warehouse barely used — enable auto-suspend at 60s or consolidate"
        elif avg_q < 0.3 and credits_hr > 1:
            action = "downsize"
            rationale = f"Low queue ({avg_q:.2f} avg) with {credits_hr:.2f} credits/hr — try next size down"
        elif avg_q > 2:
            action = "multi-cluster"
            rationale = f"Persistently high queue ({avg_q:.2f} avg, {max_q:.0f} max) — enable multi-cluster (min 1, max 3)"
        elif max_q > 5:
            action = "upsize"
            rationale = f"Occasional spike queue ({max_q:.0f} max) — consider next warehouse size up or multi-cluster"
        else:
            action = "ok"
            rationale = "Warehouse appears correctly sized for current workload"

        return WarehouseRecommendation(
            warehouse_name=str(row["warehouse_name"]),
            current_size=str(row.get("current_size", "UNKNOWN")),
            avg_credits_per_hour=credits_hr,
            max_queue_length=max_q,
            avg_queue_length=avg_q,
            action=action,
            rationale=rationale,
        )
