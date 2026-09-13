-- =============================================================
-- 模拟库平行版（ncs_sim_*）：正式库 ncs_* 不受影响
-- 数据源：gen_sim_data.py 生成的模拟 CSV（放 /home/hadoop/simdata/）
-- 由正式版脚本自动替换生成，勿手工编辑
-- =============================================================
-- =============================================================
-- 04_build_dwd.hql   NCS 项目：ODS -> DWD 清洗层（真实数据版）
-- 前置：ODS 三表已导入老师真实数据（行数 3395 / 1594 / 105）
-- 执行：hive -f /home/hadoop/04_build_dwd.hql
-- 清洗内容：
--   1) created/ended 异常年份(0014/0015) -> 修复为 2019
--      （依据：站点元数据 update_time=2019/7/26，数据采集年份为 2019；
--        月份日时分秒为原始有效值，保留）
--      并标记 is_abnormal=1 表示"年份已修复"，保留数据质量可追溯
--   2) record_time 原始为科学计数法(2.02E+13)且精度丢失(全表同值)，
--      无法解析为有效时间 -> 通过 esd 关联订单表(esd=sessionId)，
--      用订单修复后的 created 时间作为监测记录时间
--   3) 字符串字段 -> 数值类型(DOUBLE/INT)
-- =============================================================
USE ncs_sim_dwd;

-- 1) 订单明细 DWD
CREATE TABLE IF NOT EXISTS dwd_charging_order (
  session_id STRING,
  kwh_total DOUBLE,
  charging_fees DOUBLE,
  created_ts TIMESTAMP,
  ended_ts TIMESTAMP,
  created_date STRING,
  created_hour INT,
  start_hour INT,
  end_hour INT,
  charge_hours DOUBLE,
  weekday STRING,
  platform STRING,
  user_id STRING,
  station_id STRING,
  location_id STRING,
  manager_vehicle INT,
  facility_type INT,
  is_abnormal INT,
  mon INT, tues INT, wed INT, thurs INT, fri INT, sat INT, sun INT
) STORED AS PARQUET;

INSERT OVERWRITE TABLE dwd_charging_order
SELECT
  sessionId,
  cast(kwhTotal AS DOUBLE),
  cast(charging_fees AS DOUBLE),
  cast(from_unixtime(unix_timestamp(regexp_replace(created,'^001[45]','2019'),'yyyy-MM-dd HH:mm:ss'),'yyyy-MM-dd HH:mm:ss') AS TIMESTAMP),
  cast(from_unixtime(unix_timestamp(regexp_replace(ended,'^001[45]','2019'),'yyyy-MM-dd HH:mm:ss'),'yyyy-MM-dd HH:mm:ss') AS TIMESTAMP),
  substr(regexp_replace(created,'^001[45]','2019'),1,10),
  cast(substr(regexp_replace(created,'^001[45]','2019'),12,2) AS INT),
  cast(startTime AS INT),
  cast(endTime AS INT),
  cast(chargeTimeHrs AS DOUBLE),
  weekday,
  platform,
  userId,
  stationId,
  locationId,
  cast(managerVehicle AS INT),
  cast(facilityType AS INT),
  CASE WHEN created LIKE '001%' THEN 1 ELSE 0 END,
  cast(Mon AS INT), cast(Tues AS INT), cast(Wed AS INT),
  cast(Thurs AS INT), cast(Fri AS INT), cast(Sat AS INT), cast(Sun AS INT)
FROM ncs_sim_ods.ods_charging_order;

-- 2) 充电过程监测 DWD
--    record_time 原始精度丢失 -> 关联订单表修复时间(esd=sessionId)
CREATE TABLE IF NOT EXISTS dwd_charging_process (
  esd STRING,
  record_time_ts TIMESTAMP,
  record_date STRING,
  record_hour INT,
  soc DOUBLE,
  pack_voltage DOUBLE,
  charge_current DOUBLE,
  max_cell_voltage DOUBLE,
  min_cell_voltage DOUBLE,
  max_temperature DOUBLE,
  min_temperature DOUBLE,
  available_energy DOUBLE,
  available_capacity DOUBLE
) STORED AS PARQUET;

INSERT OVERWRITE TABLE dwd_charging_process
SELECT
  p.esd,
  o.created_ts,
  o.created_date,
  o.created_hour,
  cast(p.soc AS DOUBLE),
  cast(p.pack_voltage AS DOUBLE),
  cast(p.charge_current AS DOUBLE),
  cast(p.max_cell_voltage AS DOUBLE),
  cast(p.min_cell_voltage AS DOUBLE),
  cast(p.max_temperature AS DOUBLE),
  cast(p.min_temperature AS DOUBLE),
  cast(p.available_energy AS DOUBLE),
  cast(p.available_capacity AS DOUBLE)
FROM ncs_sim_ods.ods_charging_process p
LEFT JOIN ncs_sim_dwd.dwd_charging_order o ON p.esd = o.session_id;

-- 3) 充电站元数据 DWD
CREATE TABLE IF NOT EXISTS dwd_charging_station_meta (
  station_id STRING,
  location_id STRING,
  facility_type INT,
  station_name STRING,
  address STRING,
  device_count INT,
  open_time STRING,
  update_time STRING
) STORED AS PARQUET;

INSERT OVERWRITE TABLE dwd_charging_station_meta
SELECT
  stationId,
  locationId,
  cast(facilityType AS INT),
  station_name,
  address,
  cast(device_count AS INT),
  open_time,
  update_time
FROM ncs_sim_ods.ods_charging_station_meta;

-- 验证
SELECT 'dwd_order' t, COUNT(*) c FROM dwd_charging_order
UNION ALL SELECT 'dwd_process', COUNT(*) FROM dwd_charging_process
UNION ALL SELECT 'dwd_station', COUNT(*) FROM dwd_charging_station_meta;
