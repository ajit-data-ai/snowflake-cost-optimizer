"""
Query profiler: surfaces top credit consumers from QUERY_HISTORY.

Snowflake charges per-second of warehouse compute. This profiler identifies
the queries responsible for the most credit consumption so teams can
prioritize optimization effort.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date, timedelta
from typing import List
import pandas as pd
import snowflake.connector


@dataclass
class QueryInsight:
    query_id: str
    query_text_preview: str
    user_name: str
    warehouse_name: str
    database_name: str
    execution_time_seconds: float
    credits_used: float
    rows_produced: int
    bytes_scanned: int
    partitions_scanned: int
    partitions_total: int
    partition_scan_pct: float
    spill_to_remote_storage_mb: float
    recommendations: List[str]


class QueryProfiler:
    def __init__(self, conn: snowflake.connector.SnowflakeConnection) -> None:
        self._conn = conn

    def top_credit_consumers(self, lookback_days: int = 7, top_n: int = 50) -> pd.DataFrame:
        start = (date.today() - timedelta(days=lookback_days)).isoformat()
        query = f"""
            SELECT
                query_id,
                LEFT(query_text, 200)                   AS query_text_preview,
                user_name,
                warehouse_name,
                database_name,
                schema_name,
                execution_status,
                ROUND(execution_time / 1000, 2)         AS execution_time_seconds,
                ROUND(credits_used_cloud_services, 6)   AS credits_used,
                rows_produced,
                bytes_scanned,
                partitions_scanned,
                partitions_total,
                ROUND(
                    partitions_scanned * 100.0 / NULLIF(partitions_total, 0), 2
                )                                       AS partition_scan_pct,
                ROUND(bytes_spilled_to_remote_storage / 1048576, 2) AS spill_to_remote_storage_mb
            FROM snowflake.account_usage.query_history
            WHERE start_time >= '{start}'
              AND execution_status = 'SUCCESS'
              AND query_type IN ('SELECT', 'INSERT', 'UPDATE', 'DELETE', 'MERGE', 'CREATE_TABLE_AS_SELECT')
            ORDER BY credits_used DESC
            LIMIT {top_n}
        """
        df = pd.read_sql(query, self._conn)
        df["recommendations"] = df.apply(self._recommend, axis=1)
        return df

    def _recommend(self, row: pd.Series) -> List[str]:
        recs = []
        if row["partition_scan_pct"] > 80:
            recs.append("High partition scan — consider adding a cluster key on the filter column")
        if row["spill_to_remote_storage_mb"] > 100:
            recs.append(f"Spilled {row['spill_to_remote_storage_mb']:.0f}MB to remote storage — increase warehouse size or reduce join cardinality")
        if row["execution_time_seconds"] > 300:
            recs.append("Query >5 min — check for Cartesian joins or missing filters")
        if not recs:
            recs.append("No immediate recommendation")
        return recs

    def warehouse_credit_burn(self, lookback_days: int = 30) -> pd.DataFrame:
        start = (date.today() - timedelta(days=lookback_days)).isoformat()
        query = f"""
            SELECT
                warehouse_name,
                DATE_TRUNC('day', start_time)   AS day,
                SUM(credits_used)               AS credits_used,
                COUNT(*)                        AS query_count,
                ROUND(AVG(execution_time/1000), 2) AS avg_exec_seconds
            FROM snowflake.account_usage.query_history
            WHERE start_time >= '{start}'
              AND execution_status = 'SUCCESS'
            GROUP BY 1, 2
            ORDER BY 1, 2
        """
        return pd.read_sql(query, self._conn)
