-- =============================================================
-- 03_load_ods.hql   NCS 项目：导入 CSV 数据到 ODS 层
-- 前置：三个 CSV 已上传到 node100 的 /home/hadoop/data/
-- 执行：hive -f /home/hadoop/03_load_ods.hql
-- 注意：LOAD DATA LOCAL INPATH 会把文件"移动"（非复制）到 HDFS
--       /home/hadoop/data/ 下的源文件将被移走
-- =============================================================
USE ncs_ods;

LOAD DATA LOCAL INPATH '/home/hadoop/data/dsv13r2.csv' INTO TABLE ods_charging_process;
LOAD DATA LOCAL INPATH '/home/hadoop/data/nvv2t.csv' INTO TABLE ods_charging_order;
LOAD DATA LOCAL INPATH '/home/hadoop/data/nvv2t_md_end.csv' INTO TABLE ods_charging_station_meta;

-- 验证行数
SELECT 'ods_charging_process' AS tbl, COUNT(*) AS cnt FROM ods_charging_process
UNION ALL
SELECT 'ods_charging_order', COUNT(*) FROM ods_charging_order
UNION ALL
SELECT 'ods_charging_station_meta', COUNT(*) FROM ods_charging_station_meta;
