-- Auto-suspend policy for warehouses.
-- Run once per warehouse to set the idle timeout.
-- Replace COMPUTE_WH with your actual warehouse name.

-- Standard warehouses: suspend after 1 minute of inactivity
ALTER WAREHOUSE COMPUTE_WH SET AUTO_SUSPEND = 60;
ALTER WAREHOUSE COMPUTE_WH SET AUTO_RESUME = TRUE;

-- Batch/ETL warehouses: slightly longer window to avoid thrash
ALTER WAREHOUSE ETL_WH SET AUTO_SUSPEND = 120;
ALTER WAREHOUSE ETL_WH SET AUTO_RESUME = TRUE;

-- BI/dashboard warehouses: very short — queries are bursty
ALTER WAREHOUSE BI_WH SET AUTO_SUSPEND = 60;
ALTER WAREHOUSE BI_WH SET AUTO_RESUME = TRUE;

-- Resource monitors: alert at 80%, suspend at 100% of monthly budget
CREATE OR REPLACE RESOURCE MONITOR monthly_budget
    WITH CREDIT_QUOTA = 500          -- adjust to your monthly budget
    FREQUENCY = MONTHLY
    START_TIMESTAMP = IMMEDIATELY
    TRIGGERS
        ON 80 PERCENT DO NOTIFY
        ON 95 PERCENT DO NOTIFY
        ON 100 PERCENT DO SUSPEND;

ALTER WAREHOUSE COMPUTE_WH SET RESOURCE_MONITOR = monthly_budget;
ALTER WAREHOUSE ETL_WH SET RESOURCE_MONITOR = monthly_budget;
ALTER WAREHOUSE BI_WH SET RESOURCE_MONITOR = monthly_budget;
