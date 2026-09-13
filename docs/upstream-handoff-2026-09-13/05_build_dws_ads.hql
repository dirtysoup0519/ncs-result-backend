-- =============================================================
-- 05_build_dws_ads.hql   NCS 项目：DWD -> DWS/ADS 聚合层（真实数据版）
-- 前置：DWD 三表已生成（行数 3395 / 1594 / 105）
-- 执行：hive -f /home/hadoop/05_build_dws_ads.hql
-- DWS（明细汇总层）：按日/站点/小时聚合
-- ADS（指标应用层）：大屏指标表
-- 说明：真实数据异常年份已在 DWD 修复为 2019，时间全部有效，
--       聚合统计全量数据（不排除）
-- =============================================================

-- ================= DWS 层 =================
USE ncs_dws;

-- 1) 按日聚合：营收趋势
CREATE TABLE IF NOT EXISTS dws_order_daily (
  stat_date STRING,
  order_cnt BIGINT,
  total_kwh DOUBLE,
  total_fees DOUBLE,
  total_charge_hours DOUBLE,
  user_cnt BIGINT
) STORED AS PARQUET TBLPROPERTIES ('parquet.compression'='SNAPPY');

INSERT OVERWRITE TABLE dws_order_daily
SELECT created_date,
       COUNT(*),
       ROUND(SUM(kwh_total),2),
       ROUND(SUM(charging_fees),2),
       ROUND(SUM(charge_hours),2),
       COUNT(DISTINCT user_id)
FROM ncs_dwd.dwd_charging_order
GROUP BY created_date;

-- 2) 按日+站点聚合：站点分析
CREATE TABLE IF NOT EXISTS dws_order_station_daily (
  stat_date STRING,
  station_id STRING,
  order_cnt BIGINT,
  total_kwh DOUBLE,
  total_fees DOUBLE
) STORED AS PARQUET TBLPROPERTIES ('parquet.compression'='SNAPPY');

INSERT OVERWRITE TABLE dws_order_station_daily
SELECT created_date, station_id, COUNT(*), ROUND(SUM(kwh_total),2), ROUND(SUM(charging_fees),2)
FROM ncs_dwd.dwd_charging_order
GROUP BY created_date, station_id;

-- 3) 按小时聚合：24h 时段分布
CREATE TABLE IF NOT EXISTS dws_order_hourly (
  stat_hour INT,
  order_cnt BIGINT,
  total_kwh DOUBLE,
  total_fees DOUBLE
) STORED AS PARQUET TBLPROPERTIES ('parquet.compression'='SNAPPY');

INSERT OVERWRITE TABLE dws_order_hourly
SELECT created_hour, COUNT(*), ROUND(SUM(kwh_total),2), ROUND(SUM(charging_fees),2)
FROM ncs_dwd.dwd_charging_order
GROUP BY created_hour;

-- 4) 充电过程按日聚合：监测指标
CREATE TABLE IF NOT EXISTS dws_process_daily (
  stat_date STRING,
  record_cnt BIGINT,
  session_cnt BIGINT,
  avg_soc DOUBLE,
  max_soc DOUBLE,
  min_soc DOUBLE,
  avg_current DOUBLE,
  avg_pack_voltage DOUBLE,
  avg_max_temp DOUBLE
) STORED AS PARQUET TBLPROPERTIES ('parquet.compression'='SNAPPY');

INSERT OVERWRITE TABLE dws_process_daily
SELECT record_date,
       COUNT(*),
       COUNT(DISTINCT esd),
       ROUND(AVG(soc),2),
       ROUND(MAX(soc),2),
       ROUND(MIN(soc),2),
       ROUND(AVG(charge_current),2),
       ROUND(AVG(pack_voltage),2),
       ROUND(AVG(max_temperature),2)
FROM ncs_dwd.dwd_charging_process
GROUP BY record_date;

-- ================= ADS 层 =================
USE ncs_ads;

-- 1) 总 KPI 指标卡
CREATE TABLE IF NOT EXISTS ads_kpi_total (
  total_order_cnt BIGINT,
  total_fees DOUBLE,
  total_kwh DOUBLE,
  total_user_cnt BIGINT,
  total_station_cnt BIGINT,
  avg_fee_per_order DOUBLE,
  avg_kwh_per_order DOUBLE
) STORED AS PARQUET TBLPROPERTIES ('parquet.compression'='SNAPPY');

INSERT OVERWRITE TABLE ads_kpi_total
SELECT COUNT(*),
       ROUND(SUM(charging_fees),2),
       ROUND(SUM(kwh_total),2),
       COUNT(DISTINCT user_id),
       COUNT(DISTINCT station_id),
       ROUND(SUM(charging_fees)/COUNT(*),2),
       ROUND(SUM(kwh_total)/COUNT(*),2)
FROM ncs_dwd.dwd_charging_order;

-- 2) 营收趋势（全部日期，前端可自行截取近7/30日）
CREATE TABLE IF NOT EXISTS ads_revenue_trend (
  stat_date STRING,
  order_cnt BIGINT,
  total_fees DOUBLE,
  total_kwh DOUBLE
) STORED AS PARQUET TBLPROPERTIES ('parquet.compression'='SNAPPY');

INSERT OVERWRITE TABLE ads_revenue_trend
SELECT stat_date, order_cnt, total_fees, total_kwh
FROM ncs_dws.dws_order_daily;

-- 3) 站点 TOP10（按营收）
CREATE TABLE IF NOT EXISTS ads_station_top10 (
  station_id STRING,
  station_name STRING,
  location_id STRING,
  order_cnt BIGINT,
  total_fees DOUBLE,
  total_kwh DOUBLE
) STORED AS PARQUET TBLPROPERTIES ('parquet.compression'='SNAPPY');

INSERT OVERWRITE TABLE ads_station_top10
SELECT a.station_id, b.station_name, b.location_id,
       a.order_cnt, a.total_fees, a.total_kwh
FROM (
  SELECT station_id, COUNT(*) order_cnt, ROUND(SUM(charging_fees),2) total_fees, ROUND(SUM(kwh_total),2) total_kwh
  FROM ncs_dwd.dwd_charging_order
  GROUP BY station_id
  ORDER BY SUM(charging_fees) DESC
  LIMIT 10
) a
LEFT JOIN ncs_dwd.dwd_charging_station_meta b ON a.station_id = b.station_id;

-- 4) 平台占比
CREATE TABLE IF NOT EXISTS ads_platform_stat (
  platform STRING,
  order_cnt BIGINT,
  total_fees DOUBLE,
  fee_ratio DOUBLE
) STORED AS PARQUET TBLPROPERTIES ('parquet.compression'='SNAPPY');

INSERT OVERWRITE TABLE ads_platform_stat
SELECT p.platform, p.order_cnt, p.total_fees,
       ROUND(p.total_fees / t.total_fees * 100, 2)
FROM (
  SELECT platform, COUNT(*) order_cnt, ROUND(SUM(charging_fees),2) total_fees
  FROM ncs_dwd.dwd_charging_order
  GROUP BY platform
) p
CROSS JOIN (SELECT SUM(charging_fees) total_fees FROM ncs_dwd.dwd_charging_order) t;

-- 5) 24h 时段分布
CREATE TABLE IF NOT EXISTS ads_hourly_stat (
  stat_hour INT,
  order_cnt BIGINT,
  total_kwh DOUBLE,
  total_fees DOUBLE
) STORED AS PARQUET TBLPROPERTIES ('parquet.compression'='SNAPPY');

INSERT OVERWRITE TABLE ads_hourly_stat
SELECT stat_hour, order_cnt, total_kwh, total_fees
FROM ncs_dws.dws_order_hourly;

-- 6) 月度营收聚合（大屏月趋势）
CREATE TABLE IF NOT EXISTS ads_revenue_monthly (
  stat_month STRING,
  order_cnt BIGINT,
  total_fees DOUBLE,
  total_kwh DOUBLE
) STORED AS PARQUET TBLPROPERTIES ('parquet.compression'='SNAPPY');

INSERT OVERWRITE TABLE ads_revenue_monthly
SELECT substr(stat_date,1,7),
       SUM(order_cnt),
       ROUND(SUM(total_fees),2),
       ROUND(SUM(total_kwh),2)
FROM ncs_dws.dws_order_daily
GROUP BY substr(stat_date,1,7);

-- ================= 验证 =================
SELECT 'ads_kpi_total' t, COUNT(*) c FROM ads_kpi_total
UNION ALL SELECT 'ads_revenue_trend', COUNT(*) FROM ads_revenue_trend
UNION ALL SELECT 'ads_revenue_monthly', COUNT(*) FROM ads_revenue_monthly
UNION ALL SELECT 'ads_station_top10', COUNT(*) FROM ads_station_top10
UNION ALL SELECT 'ads_platform_stat', COUNT(*) FROM ads_platform_stat
UNION ALL SELECT 'ads_hourly_stat', COUNT(*) FROM ads_hourly_stat;
