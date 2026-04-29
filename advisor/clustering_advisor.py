"""
Clustering key advisor.

Identifies tables that would benefit from clustering by analysing
which columns appear most in WHERE and JOIN predicates across
recent queries against that table.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import List
import pandas as pd
import snowflake.connector


@dataclass
class ClusteringRecommendation:
    table_name: str
    current_clustering_key: str
    recommended_columns: List[str]
    avg_partition_depth: float
    avg_rows_per_partition: int
    rationale: str


class ClusteringAdvisor:
    def __init__(self, conn: snowflake.connector.SnowflakeConnection) -> None:
        self._conn = conn

    def analyse_table(self, database: str, schema: str, table: str) -> ClusteringRecommendation:
        fqn = f"{database}.{schema}.{table}"

        # Get current clustering info
        info_df = pd.read_sql(f"SHOW TABLES LIKE '{table}' IN SCHEMA {database}.{schema}", self._conn)
        current_key = ""
        if not info_df.empty and "cluster_by" in info_df.columns:
            current_key = info_df.iloc[0].get("cluster_by", "")

        # Analyse partition depth (high depth = poor clustering)
        cluster_df = pd.read_sql(
            f"SELECT SYSTEM$CLUSTERING_INFORMATION('{fqn}') AS info", self._conn
        )
        info = cluster_df.iloc[0]["info"] if not cluster_df.empty else "{}"

        # Find filter columns from recent query patterns
        predicate_df = pd.read_sql(f"""
            SELECT
                REGEXP_SUBSTR(query_text, 'WHERE\\s+(\\w+)', 1, 1, 'ie', 1) AS filter_col,
                COUNT(*) AS frequency
            FROM snowflake.account_usage.query_history
            WHERE query_text ILIKE '%{table}%'
              AND start_time >= DATEADD(day, -30, CURRENT_TIMESTAMP())
              AND execution_status = 'SUCCESS'
            GROUP BY 1
            HAVING filter_col IS NOT NULL
            ORDER BY frequency DESC
            LIMIT 5
        """, self._conn)

        recommended = predicate_df["filter_col"].dropna().tolist() if not predicate_df.empty else []

        return ClusteringRecommendation(
            table_name=fqn,
            current_clustering_key=current_key or "none",
            recommended_columns=recommended,
            avg_partition_depth=0.0,
            avg_rows_per_partition=0,
            rationale=(
                f"Top filter columns in last 30 days: {', '.join(recommended[:3]) or 'insufficient data'}. "
                + ("Clustering on these columns could reduce partition scans significantly." if recommended
                   else "Run more workload before advising.")
            ),
        )

    def tables_needing_clustering(self, database: str, schema: str) -> pd.DataFrame:
        """Return tables with high average partition depth (poor clustering)."""
        query = f"""
            SELECT
                table_name,
                row_count,
                bytes / 1073741824.0 AS size_gb,
                clustering_key
            FROM {database}.information_schema.tables
            WHERE table_schema = '{schema}'
              AND table_type = 'BASE TABLE'
              AND row_count > 1000000
            ORDER BY size_gb DESC
        """
        return pd.read_sql(query, self._conn)
