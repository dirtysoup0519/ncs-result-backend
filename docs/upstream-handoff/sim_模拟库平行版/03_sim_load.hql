-- =============================================================
-- 模拟库平行版（ncs_sim_*）：正式库 ncs_* 不受影响
-- 数据源：gen_sim_data.py 生成的模拟 CSV（放 /home/hadoop/simdata/）
-- 由正式版脚本自动替换生成，勿手工编辑
-- =============================================================
-- =============================================================
-- 03_load_ods.hql   NCS 项目：导入 CSV 数据到 ODS 层
-- 前置：三个 CSV 已上传到 node100 的 /home/hadoop/simdata/
-- 执行：hive -f /home/hadoop/03_load_ods.hql
-- 注意：LOAD DATA LOCAL INPATH 会把文件"移动"（非复制）到 HDFS
--       /home/hadoop/simdata/ 下的源文件将被移走
-- =============================================================
USE ncs_sim_ods;

LOAD DATA LOCAL INPATH '/home/hadoop/simdata/dsv13r2.csv' OVERWRITE INTO TABLE ods_charging_process;
LOAD DATA LOCAL INPATH '/home/hadoop/simdata/nvv2t.csv' OVERWRITE INTO TABLE ods_charging_order;
LOAD DATA LOCAL INPATH '/home/hadoop/simdata/nvv2t_md_end.csv' OVERWRITE INTO TABLE ods_charging_station_meta;

-- 验证行数
SELECT 'ods_charging_process' AS tbl, COUNT(*) AS cnt FROM ods_charging_process
UNION ALL
SELECT 'ods_charging_order', COUNT(*) FROM ods_charging_order
UNION ALL
SELECT 'ods_charging_station_meta', COUNT(*) FROM ods_charging_station_meta;
