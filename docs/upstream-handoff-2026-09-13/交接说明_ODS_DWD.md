# NCS 电动汽车充电桩应用管理平台 · 数据侧交接文档（完整版）

> 交接人：数据模拟 + ODS + DWD 负责人
> 交接对象：DWS/ADS 聚合 → MySQL → Flask 后端 → Vue+ECharts 前端 负责人
> 盘点日期：2026-09-12（node100 实测）
> 状态：**数据侧全链路（ODS→DWD→DWS→ADS→导出 CSV）已跑通，下游可直接取数**

---

## 1. 环境信息（node100 虚拟机）

| 项目 | 值 |
|---|---|
| 主机 | node100，CentOS 7 |
| 用户 | hadoop |
| IP | 192.168.176.100（ssh/scp 用 `hadoop@192.168.176.100`） |
| Hadoop | 3.3.0（/opt/module/hadoop-3.3.0） |
| Hive | 2.1.1（/opt/module/apache-hive-2.1.1-bin） |
| JDK | 1.8.0_144 |
| 数据库 | Hive 4 层库：ncs_ods / ncs_dwd / ncs_dws / ncs_ads（MySQL 5.7.35 存 Hive 元数据） |
| 数据文件位置 | 原始 CSV 在 `/home/hadoop/data/`；导出指标在 `/home/hadoop/dashboard/data/` |

---

## 2. 数据资产总览（2026-09-12 盘点实测）

### 2.1 Hive 四层 16 张表

| 层 | 表名 | 行数 | 存储 | 说明 |
|---|---|---|---|---|
| ODS | ods_charging_order | 3,395 | TEXTFILE 外部表 | 订单原始数据 |
| ODS | ods_charging_process | 1,594 | TEXTFILE 外部表 | 充电过程原始数据 |
| ODS | ods_charging_station_meta | 105 | TEXTFILE 外部表 | 站点元数据 |
| DWD | dwd_charging_order | 3,395 | PARQUET | 订单明细（清洗后） |
| DWD | dwd_charging_process | 1,594 | PARQUET | 充电过程（清洗后） |
| DWD | dwd_charging_station_meta | 105 | PARQUET | 站点维度 |
| DWS | dws_order_daily | 238 | PARQUET+SNAPPY | 按日聚合（营收趋势） |
| DWS | dws_order_station_daily | 2,800 | PARQUET+SNAPPY | 按日+站点聚合 |
| DWS | dws_order_hourly | 23 | PARQUET+SNAPPY | 按小时聚合（24h 分布） |
| DWS | dws_process_daily | 219 | PARQUET+SNAPPY | 充电过程按日指标 |
| ADS | ads_kpi_total | 1 | PARQUET+SNAPPY | 总 KPI 指标卡 |
| ADS | ads_revenue_trend | 238 | PARQUET+SNAPPY | 营收日趋势 |
| ADS | ads_revenue_monthly | 12 | PARQUET+SNAPPY | 营收月趋势 |
| ADS | ads_station_top10 | 10 | PARQUET+SNAPPY | 站点营收 TOP10 |
| ADS | ads_platform_stat | 3 | PARQUET+SNAPPY | 平台占比 |
| ADS | ads_hourly_stat | 23 | PARQUET+SNAPPY | 24h 时段分布 |

### 2.2 导出指标 CSV（/home/hadoop/dashboard/data/，制表符分隔、无表头）

| 文件 | 大小 | 对应大屏图表 | 来源表 |
|---|---|---|---|
| kpi_total.csv | 242B | 总指标卡（订单/营收/电量/用户/站点/均价） | ads_kpi_total |
| revenue_trend.csv | 5.7K | 营收趋势折线图（日） | ads_revenue_trend |
| revenue_monthly.csv | 410B | 营收月度趋势 | ads_revenue_monthly |
| station_top10.csv | 912B | 站点营收 TOP10 排行 | ads_station_top10 |
| platform_stat.csv | 172B | 平台占比饼图/环形图 | ads_platform_stat |
| hourly_stat.csv | 504B | 24 小时订单/电量分布 | ads_hourly_stat |
| order_daily.csv | 7.7K | 每日订单量柱状图 | dws_order_daily |
| process_daily.csv | 11K | 充电过程监测指标趋势 | dws_process_daily |

---

## 3. 数据来源与特征

### 3.1 真实数据（老师课堂派发放，正式分析使用）

| 文件 | 行数 | 列数 | 内容 |
|---|---|---|---|
| nvv2t.csv | 3,395 | 22 | 充电订单交易 |
| dsv13r2.csv | 1,594 | 11 | 充电过程实时监测 |
| nvv2t_md_end.csv | 105 | 8 | 充电站/桩元数据（郑州 105 站） |

**原始数据特征（清洗依据）**：
- 表头带 UTF-8 BOM，ODS 列名不含单位和括号（如 `pack_voltage` 而非 `pack_voltage (V)`）
- created/ended 年份**全部异常**（0014/0015，月日时分秒有效，9 月订单最多）
- record_time 为科学计数法（2.02E+13），毫秒精度丢失，无法直接解析
- 充电费用 88.8% 为 0；电流为负值 -22~-74A；温度 32~37℃
- stationId/locationId 纯数字；站点表 105 行与订单 105 个站点 100% 关联
- 平台仅 android / ios / web；站点 update_time = 2019/7/26

**数据年份判定：2019**（依据站点 update_time=2019/7/26，异常年份 0014/0015 实际为 2014/2015 的截断写法）

### 3.2 模拟数据（分布一致版，链路测试与容量验证用）

`02_gen_aug_sim_data.py` + `real_dist.json`：**分布一致版模拟生成器 v2**——从真实数据学习分布模型（real_dist.json），按分位数采样生成，模拟数据的分布规律与真实数据一致或相似（而非纯随机）：

- 表头与真实数据完全一致（22/11/8 列、UTF-8 BOM）
- 小时分布（10-12点/16-17点双高峰）、星期分布（工作日多、周末极少）、月份分布（1~9月递增、10月起骤降）均对齐真实
- 平台占比（ios 66%/android 34%）、设施类型、站点热度（真实 105 站长尾）对齐真实
- kwh = 时长 × 隐含功率（保持字段相关性）；费用 88.8% 为 0；电流集中 -22.5A、温度 32~37℃；监测每会话 1 条采样（真实特征）
- 异常年份 0014/0015（99.3% 为 0015）、科学计数法时间戳、esd 100% 关联订单

```cmd
:: 分布采样生成（默认）
python 02_gen_aug_sim_data.py --orders 5000 --out 输出目录 --seed 42
:: 数据增强模式（对真实数据做时间偏移+数值扰动+站点重组）
python 02_gen_aug_sim_data.py --augment --real-dir 真实CSV目录 --offset-days 90 --noise 0.05 --out 输出目录
```

常用参数：--orders 订单数 / --seed 随机种子 / --out 输出目录；增强模式：--augment / --real-dir / --offset-days / --noise

> 预生成好的模拟 CSV（5000 订单，已在本机验证分布一致）在交付包 `simdata/` 目录，可直接上传使用。

---

## 4. 已完成工作（本负责人分工：数据模拟 + ODS + DWD）

### 4.1 ODS 原始层
- `01_ods_create.hql`：建 4 库 + 3 张 ODS 外部表（TEXTFILE、LOCATION /ncs/ods/表名、skip.header.line.count=1、全 STRING）
- `03_load_ods.hql` / `03_collect_data.sh`：LOAD 3 份 CSV 入 ODS，并做行数校验
- **校验结果：1594 / 3395 / 105 全部一致 ✅**

### 4.2 DWD 清洗层（`04_build_dwd.hql`，PARQUET）
| 清洗项 | 处理方式 |
|---|---|
| 异常年份 0014/0015 | 依据站点 update_time=2019/7/26 修复为 2019，并标记 is_abnormal=1 |
| record_time 精度丢失 | 通过 esd = 订单 sessionId 关联，取订单修复后的 created 时间 |
| 类型转换 | DOUBLE / INT / TIMESTAMP 明确转换（from_unixtime 参数须为 BIGINT，毫秒转秒用 DIV 1000） |
| 字段裁剪 | 按分析需要选取字段，去除括号列名差异 |

- **DWD 结果：dwd_charging_order 3,395 / dwd_charging_process 1,594 / dwd_charging_station_meta 105 ✅**

---

## 5. 已协助跑通（DWS/ADS/导出，供下游直接使用）

> 说明：DWS/ADS 聚合与导出属下游职责，本人为验证链路完整性已协助跑通（05/06 脚本），下游接手即可直接用，无需重跑。

### 5.1 DWS 表口径
| 表 | 粒度 | 关键字段 |
|---|---|---|
| dws_order_daily | 日 | stat_date, order_cnt, total_kwh, total_fees, total_charge_hours, user_cnt |
| dws_order_station_daily | 日+站点 | stat_date, station_id, order_cnt, total_kwh, total_fees |
| dws_order_hourly | 小时 | stat_hour, order_cnt, total_kwh, total_fees |
| dws_process_daily | 日 | stat_date, record_cnt, session_cnt, avg_soc, max_soc, min_soc, avg_current, avg_pack_voltage, avg_max_temp |

### 5.2 ADS 表口径
| 表 | 内容 | 关键字段 |
|---|---|---|
| ads_kpi_total | 总 KPI（1 行） | total_order_cnt, total_fees, total_kwh, total_user_cnt, total_station_cnt, avg_fee_per_order, avg_kwh_per_order |
| ads_revenue_trend | 营收日趋势（238 行） | stat_date, order_cnt, total_fees, total_kwh |
| ads_revenue_monthly | 营收月趋势（12 行） | stat_month, order_cnt, total_fees, total_kwh |
| ads_station_top10 | 站点 TOP10（10 行） | station_id, station_name, location_id, order_cnt, total_fees, total_kwh |
| ads_platform_stat | 平台占比（3 行） | platform, order_cnt, total_fees, fee_ratio |
| ads_hourly_stat | 24h 分布（23 行） | stat_hour, order_cnt, total_kwh, total_fees |

### 5.3 导出脚本（06_export_metrics.sh）
`hive --silent -e "SELECT ..."` 导出 8 个 CSV 到 `/home/hadoop/dashboard/data/`，制表符分隔无表头，前端 JS 按 `split('\t')` 解析即可。

---

## 6. 给下一个成员（后端/前端）的接续指引

### 6.1 推荐链路（课件标准）
```
Hive(ADS) → MySQL(建议 sqoop 或脚本导入) → Flask RESTful API → Vue + ECharts 大屏
```

### 6.2 取数路径建议（CSV 已就绪，最快方案）
直接读 `/home/hadoop/dashboard/data/*.csv`（Flask 按文件读取返回 JSON），或先导入 MySQL 再走接口。

### 6.3 命名规范（对齐课件）
ODS 库 `_ods` / DWD 库 `_dwd` / DWS 库 `_dws` / ADS 库 `_ads`；表名如 `ods_charging_order`、`dwd_charging_order`、`dws_order_daily`、`ads_kpi_total`。

### 6.4 注意事项
- 数据年份为 **2019**，大屏标题/筛选勿写错年份
- 时间字段（created/ended/stat_date）均为标准格式，直接按日期/小时 GROUP BY 即可
- 站点维度表 `dwd_charging_station_meta` 与订单 `station_id` 可直接 JOIN
- 费用有大量 0 值订单（真实数据特征），如做均价类指标建议注明口径
- 前端若需近 7/30 日趋势，从 ads_revenue_trend 自行截取

---

## 7. 脚本清单（本交付包）

| 文件 | 作用 |
|---|---|
| 01_ods_create.hql | 建库 + ODS 三表 DDL |
| 03_load_ods.hql | 导入 3 份 CSV 入 ODS（含行数校验） |
| 03_collect_data.sh | 采集封装脚本（local/hdfs 双模式、日志、可配 crontab） |
| 04_build_dwd.hql | ODS→DWD 清洗（PARQUET，修复年份/时间戳/类型） |
| 05_build_dws_ads.hql | DWD→DWS/ADS 聚合（PARQUET+SNAPPY） |
| 06_export_metrics.sh | 导出 8 个指标 CSV 到 /home/hadoop/dashboard/data/ |
| 02_gen_aug_sim_data.py | 模拟数据生成器 v2（分布一致版，读 real_dist.json 采样） |
| real_dist.json | 真实数据分布模型（生成器学习依据） |

### 在 node100 上重跑顺序
```bash
hive -f /home/hadoop/01_ods_create.hql          # 建表（表已存在则跳过）
bash /home/hadoop/03_collect_data.sh            # 或 hive -f 03_load_ods.hql 导入
hive -f /home/hadoop/04_build_dwd.hql           # ODS→DWD
hive -f /home/hadoop/05_build_dws_ads.hql       # DWD→DWS/ADS
bash /home/hadoop/06_export_metrics.sh          # 导出 CSV
```

---