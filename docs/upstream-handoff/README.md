# NCS 电动汽车充电桩应用管理平台 · 数据侧交接包

> 交接人：数据模拟 + ODS + DWD 负责人（DWS/ADS/导出协助跑通）
> 交接对象：DWS/ADS → MySQL → Flask → Vue+ECharts 大屏负责人
> 更新日期：2026-09-13

---

## 一、交接包结构（平铺，按文件名序号 = 执行顺序）

```
交接包\
├── README.md                         ← 总览（先看这个）
├── 交接说明_ODS_DWD.md               数据现状总览、16 张表行数、清洗口径
├── 下游接续指南-后端与前端.md         下游同学操作手册（Flask/Vue/大屏/答辩清单）
├── 01_ods_create.hql               建 ncs_ods/dwd/dws/ads 四库 + 3 张 ODS 外部表
├── 02_gen_sim_data.py              模拟数据生成器（贴合真实特征，参数化）
├── 03_collect_data.sh              采集封装脚本（local/hdfs 双模式、日志）
├── 03_load_ods.hql                 LOAD 导入 3 份 CSV 入 ODS
├── 04_build_dwd.hql                ODS→DWD 清洗（PARQUET）
├── 05_build_dws_ads.hql            DWD→DWS/ADS 聚合（PARQUET+SNAPPY）
├── 06_export_metrics.sh            导出 8 个指标 CSV 到 dashboard/data/
└── sim_模拟库平行版\                 模拟数据专用（正式库零影响）
    ├── README_sim.md                平行库使用说明
    ├── 01_sim_create.hql            建 ncs_sim_* 四库
    ├── 03_sim_load.hql              导入模拟 CSV（OVERWRITE 可重跑）
    ├── 04_sim_dwd.hql               模拟 DWD 清洗
    ├── 05_sim_dws_ads.hql           模拟 DWS/ADS 聚合
    └── 06_sim_export.sh             导出到 dashboard/sim_data/
```

## 二、正式链路执行顺序（node100，真实数据）

```bash
cd /home/hadoop
hive -f 01_ods_create.hql        # 1 建库建表
bash 03_collect_data.sh          # 2 采集/导入（或 hive -f 03_load_ods.hql）
hive -f 04_build_dwd.hql         # 3 ODS→DWD 清洗
hive -f 05_build_dws_ads.hql     # 4 DWD→DWS/ADS 聚合
bash 06_export_metrics.sh        # 5 导出指标 CSV → /home/hadoop/dashboard/data/
```

## 三、平行库链路（模拟数据，大屏测试用）

```bash
cd /home/hadoop
hive -f 01_sim_create.hql        # 建 ncs_sim_* 四库
hive -f 03_sim_load.hql          # 导入模拟 CSV（先 scp 到 /home/hadoop/simdata/）
hive -f 04_sim_dwd.hql
hive -f 05_sim_dws_ads.hql
bash 06_sim_export.sh            # 导出 → /home/hadoop/dashboard/sim_data/
```

## 四、关键提示

1. **数据年份 = 2019**（真实数据），大屏标题别写错
2. **`.sh` 脚本从 Windows 上传后**先执行 `sed -i 's/\r$//' 文件名`（转 Linux 换行），`.hql` 不用
3. 正式库行数：ODS/DWD 均 3395 订单 / 1594 监测 / 105 站点；模拟库 5000 / 37212 / 105
4. 大屏后端读正式数据用 `dashboard/data/`，读模拟数据切 `dashboard/sim_data/`
5. 清洗亮点（答辩用）：异常年份 0014/0015→2019（依据站点 update_time=2019/7/26）；record_time 精度丢失→esd 关联订单修复
