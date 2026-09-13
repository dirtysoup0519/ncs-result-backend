-- =============================================================================
-- 文件：01_ods_create.hql
-- 项目：东软电动汽车充电桩应用管理平台 NCS（北京理工大学项目实训）
-- 课时：第一天 第3课时 —— Hive 基础介绍 + 本项目 Hive 建表实施（ODS 原始数据层）
-- 说明：
--   ODS（Operational Data Store）原始数据层：原样保存 CSV 数据，不做清洗。
--   存储格式用 TextFile（行存、可读），字段分隔符为逗号 ','。
--   注意：CSV 首行为英文列名表头，导入时需跳过（见采集脚本 TBLPROPERTIES skip.header.line.count）。
-- 执行：hive -f 01_ods_create.hql
-- =============================================================================

-- 0. 创建四层数据仓库数据库（ODS/DWD/DWS/ADS），本课时先建 ods
CREATE DATABASE IF NOT EXISTS ncs_ods COMMENT 'NCS充电桩项目-原始数据层ODS';
CREATE DATABASE IF NOT EXISTS ncs_dwd COMMENT 'NCS充电桩项目-明细数据层DWD';
CREATE DATABASE IF NOT EXISTS ncs_dws COMMENT 'NCS充电桩项目-聚合数据层DWS';
CREATE DATABASE IF NOT EXISTS ncs_ads COMMENT 'NCS充电桩项目-应用数据层ADS';

USE ncs_ods;

-- =============================================================================
-- 1. ODS 层：充电过程实时监测数据表（来源 dsv13r2.csv）
--    CSV 表头：esd,record_time,soc,pack_voltage (V),charge_current (A),
--             max_cell_voltage (V),min_cell_voltage (V),
--             max_temperature(℃),min_temperature(℃),
--             available_energy (kw),available_capacity (Ah)
--    注意：record_time 在 CSV 中为科学计数法(如 2.02E+13)，
--          ODS 层先用 STRING 原样接收，清洗(DWD)时再统一转时间格式。
-- =============================================================================
DROP TABLE IF EXISTS ncs_ods.ods_charging_process;
CREATE EXTERNAL TABLE IF NOT EXISTS ncs_ods.ods_charging_process (
    esd                 STRING  COMMENT '充电会话唯一标识ID(对应订单sessionId)',
    record_time         STRING  COMMENT '记录时间戳(CSV为科学计数法,原样保留,如2.02E+13)',
    soc                 STRING  COMMENT '电池剩余电量百分比(%)',
    pack_voltage        STRING  COMMENT '电池组总电压(V)',
    charge_current      STRING  COMMENT '充电电流(A,负值表示放电)',
    max_cell_voltage    STRING  COMMENT '最高单体电池电压(V)',
    min_cell_voltage    STRING  COMMENT '最低单体电池电压(V)',
    max_temperature     STRING  COMMENT '电池组最高温度(℃)',
    min_temperature     STRING  COMMENT '电池组最低温度(℃)',
    available_energy    STRING  COMMENT '电池可用能量(kWh)',
    available_capacity  STRING  COMMENT '电池可用容量(Ah)'
)
COMMENT '充电桩充电过程原始监测数据(ODS层)'
ROW FORMAT DELIMITED FIELDS TERMINATED BY ','
STORED AS TEXTFILE
LOCATION '/ncs/ods/ods_charging_process'
TBLPROPERTIES ('skip.header.line.count'='1');   -- 导入时跳过 CSV 首行英文表头

-- =============================================================================
-- 2. ODS 层：充电订单交易数据表（来源 nvv2t.csv）
--    CSV 表头：sessionId,kwhTotal,charging_fees,created,ended,startTime,endTime,
--             chargeTimeHrs,weekday,platform,userId,stationId,locationId,
--             managerVehicle,facilityType,Mon,Tues,Wed,Thurs,Fri,Sat,Sun
--    注意：created 时间为异常年份格式(如 0014-11-18)，ODS 层原样保留，DWD 层再修。
-- =============================================================================
DROP TABLE IF EXISTS ncs_ods.ods_charging_order;
CREATE EXTERNAL TABLE IF NOT EXISTS ncs_ods.ods_charging_order (
    sessionId       STRING  COMMENT '充电会话ID(关联充电过程数据esd)',
    kwhTotal        STRING  COMMENT '充电总量(kWh)',
    charging_fees   STRING  COMMENT '充电费用(元)',
    created         STRING  COMMENT '订单创建时间(YYYY-MM-DD HH:MM:SS,年份可能异常)',
    ended           STRING  COMMENT '订单结束时间(YYYY-MM-DD HH:MM:SS)',
    startTime       STRING  COMMENT '充电开始小时(24小时制)',
    endTime         STRING  COMMENT '充电结束小时(24小时制)',
    chargeTimeHrs   STRING  COMMENT '充电时长(小时)',
    weekday         STRING  COMMENT '星期几(Mon..Sun)',
    platform        STRING  COMMENT '用户使用平台(android/ios等)',
    userId          STRING  COMMENT '用户唯一标识ID',
    stationId       STRING  COMMENT '充电站唯一标识ID',
    locationId      STRING  COMMENT '位置区域ID',
    managerVehicle  STRING  COMMENT '管理车辆标识(0=普通用户,1=管理车辆)',
    facilityType    STRING  COMMENT '设施类型(充电桩类型编码)',
    Mon             STRING  COMMENT '是否周一(1是0否)',
    Tues            STRING  COMMENT '是否周二(1是0否)',
    Wed             STRING  COMMENT '是否周三(1是0否)',
    Thurs           STRING  COMMENT '是否周四(1是0否)',
    Fri             STRING  COMMENT '是否周五(1是0否)',
    Sat             STRING  COMMENT '是否周六(1是0否)',
    Sun             STRING  COMMENT '是否周日(1是0否)'
)
COMMENT '充电桩充电订单原始交易数据(ODS层)'
ROW FORMAT DELIMITED FIELDS TERMINATED BY ','
STORED AS TEXTFILE
LOCATION '/ncs/ods/ods_charging_order'
TBLPROPERTIES ('skip.header.line.count'='1');

-- =============================================================================
-- 3. ODS 层：充电站/充电桩元数据表（来源 nvv2t_md_end.csv）
--    CSV 表头：stationId,locationId,facilityType,station_name,address,
--             device_count,open_time,update_time
-- =============================================================================
DROP TABLE IF EXISTS ncs_ods.ods_charging_station_meta;
CREATE EXTERNAL TABLE IF NOT EXISTS ncs_ods.ods_charging_station_meta (
    stationId      STRING  COMMENT '充电站唯一标识ID',
    locationId     STRING  COMMENT '位置区域ID',
    facilityType   STRING  COMMENT '设施类型编码(1交流/2直流/3交直流一体)',
    station_name   STRING  COMMENT '充电站名称',
    address        STRING  COMMENT '充电站地址',
    device_count   STRING  COMMENT '充电桩数量',
    open_time      STRING  COMMENT '运营时间',
    update_time    STRING  COMMENT '元数据更新时间'
)
COMMENT '充电站及充电桩原始元数据(ODS层)'
ROW FORMAT DELIMITED FIELDS TERMINATED BY ','
STORED AS TEXTFILE
LOCATION '/ncs/ods/ods_charging_station_meta'
TBLPROPERTIES ('skip.header.line.count'='1');

-- =============================================================================
-- 建表后验证
-- =============================================================================
SHOW DATABASES; --显示有那些数据库
USE ncs_ods;  --切换数据库
SHOW TABLES;  --显示有那些表
DESC FORMATTED ncs_ods.ods_charging_order;
