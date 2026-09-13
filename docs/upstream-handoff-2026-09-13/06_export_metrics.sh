#!/bin/bash
# =============================================================
# 06_export_metrics.sh   NCS 项目：导出大屏指标为 CSV
# 前置：ADS/DWS 表已生成（跑完 05_build_dws_ads.hql）
# 执行：bash /home/hadoop/06_export_metrics.sh
# 输出：/home/hadoop/dashboard/data/*.csv（制表符分隔，无表头）
#       前端 JS 里按行 split('\t') 解析即可
# =============================================================
OUT=/home/hadoop/dashboard/data
mkdir -p "$OUT"

hive --silent -e "SELECT * FROM ncs_ads.ads_kpi_total;"           > "$OUT/kpi_total.csv"
hive --silent -e "SELECT * FROM ncs_ads.ads_revenue_trend ORDER BY stat_date;" > "$OUT/revenue_trend.csv"
hive --silent -e "SELECT * FROM ncs_ads.ads_revenue_monthly ORDER BY stat_month;" > "$OUT/revenue_monthly.csv"
hive --silent -e "SELECT * FROM ncs_ads.ads_station_top10;"       > "$OUT/station_top10.csv"
hive --silent -e "SELECT * FROM ncs_ads.ads_platform_stat;"       > "$OUT/platform_stat.csv"
hive --silent -e "SELECT * FROM ncs_ads.ads_hourly_stat ORDER BY stat_hour;" > "$OUT/hourly_stat.csv"
hive --silent -e "SELECT * FROM ncs_dws.dws_order_daily ORDER BY stat_date;" > "$OUT/order_daily.csv"
hive --silent -e "SELECT * FROM ncs_dws.dws_process_daily ORDER BY stat_date;" > "$OUT/process_daily.csv"

echo "=== 完成，输出目录: $OUT ==="
ls -lh "$OUT"
