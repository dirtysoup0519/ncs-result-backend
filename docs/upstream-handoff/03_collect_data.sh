#!/bin/bash
# =============================================================
# 03_collect_data.sh   NCS 项目 · ODS 层数据采集脚本（课件标准封装）
# 功能：建 HDFS 目录 → 上传/导入 3 份 CSV → LOAD 入 ODS → 行数校验
# 用法：
#   ./03_collect_data.sh local    # CSV 在 Linux 本地 /home/hadoop/data
#   ./03_collect_data.sh hdfs     # CSV 已上传到 HDFS /ncs/ods
# 定时：crontab -e 加入  30 1 * * * /home/hadoop/03_collect_data.sh local
# =============================================================
MODE="${1:-local}"
DATA_DIR="/home/hadoop/data"
HQL_DIR="/home/hadoop"
LOG_FILE="/home/hadoop/logs/collect_$(date +%Y%m%d).log"
HIVE="hive"

mkdir -p /home/hadoop/logs

log() { echo "[$(date +%F\ %T)] $1" | tee -a "$LOG_FILE"; }

load_hql() {
  log "执行 HQL: $1"
  $HIVE -f "$1"
  if [ $? -ne 0 ]; then log "ERROR: $1 执行失败"; exit 1; fi
  log "完成: $1"
}

# 1) 建 ODS 表目录
log "建 HDFS 目录 /ncs/ods"
hdfs dfs -mkdir -p /ncs/ods/ods_charging_process \
                     /ncs/ods/ods_charging_order \
                     /ncs/ods/ods_charging_station_meta

# 2) 数据入表
if [ "$MODE" = "hdfs" ]; then
  log "HDFS 模式：上传 CSV 到 /ncs/ods 后入表"
  hdfs dfs -put -f $DATA_DIR/*.csv /ncs/ods/
  $HIVE -e "USE ncs_ods;
LOAD DATA INPATH '/ncs/ods/dsv13r2.csv'       INTO TABLE ods_charging_process;
LOAD DATA INPATH '/ncs/ods/nvv2t.csv'         INTO TABLE ods_charging_order;
LOAD DATA INPATH '/ncs/ods/nvv2t_md_end.csv'  INTO TABLE ods_charging_station_meta;" >> "$LOG_FILE" 2>&1
else
  log "LOCAL 模式：直接从 /home/hadoop/data LOAD"
  load_hql "$HQL_DIR/03_load_ods.hql"
fi

# 3) 行数校验（与源 CSV 对比）
log "=== 行数校验 ==="
$HIVE -e "SELECT 'ods_charging_process' t, COUNT(*) c FROM ncs_ods.ods_charging_process
UNION ALL SELECT 'ods_charging_order', COUNT(*) FROM ncs_ods.ods_charging_order
UNION ALL SELECT 'ods_charging_station_meta', COUNT(*) FROM ncs_ods.ods_charging_station_meta;" | tee -a "$LOG_FILE"

log "全部采集完成，日志: $LOG_FILE"
