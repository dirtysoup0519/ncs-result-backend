# NCS 平行库（ncs_sim_*）使用说明

模拟数据与真实数据**完全隔离**：模拟数据跑 `ncs_sim_ods/dwd/dws/ads` 四套库，
正式库 `ncs_ods/dwd/dws/ads`（真实数据）一根汗毛不动。

## 一、生成模拟 CSV（Windows 上，可选——交付包 simdata/ 已预生成）

```cmd
:: 新生成器为分布一致版（v2），依赖同目录 real_dist.json
cd /d D:\Lin\交接包
python 02_gen_aug_sim_data.py --orders 5000 --out D:\simdata
:: 或直接使用预生成好的：D:\Lin\交接包\simdata\（5000订单，分布与真实一致）
```

## 二、上传到 node100

```cmd
scp D:\Lin\交接包\simdata\nvv2t.csv hadoop@192.168.176.100:/home/hadoop/simdata/
scp D:\Lin\交接包\simdata\dsv13r2.csv hadoop@192.168.176.100:/home/hadoop/simdata/
scp D:\Lin\交接包\simdata\nvv2t_md_end.csv hadoop@192.168.176.100:/home/hadoop/simdata/
scp D:\Lin\交接包\sim_模拟库平行版\*.hql hadoop@192.168.176.100:/home/hadoop/
scp D:\Lin\交接包\sim_模拟库平行版\06_sim_export.sh hadoop@192.168.176.100:/home/hadoop/
```

## 三、跑通模拟链路（node100，按序执行）

```bash
cd /home/hadoop
hive -f 01_sim_create.hql      # 建 ncs_sim_* 四库 + 3 张模拟 ODS 表
hive -f 03_sim_load.hql        # 导入模拟 CSV 入 ncs_sim_ods（OVERWRITE，可反复重跑）
hive -f 04_sim_dwd.hql         # 清洗 -> ncs_sim_dwd
hive -f 05_sim_dws_ads.hql     # 聚合 -> ncs_sim_dws / ncs_sim_ads
bash 06_sim_export.sh          # 导出指标到 /home/hadoop/dashboard/sim_data/
```

## 四、验证

```bash
hive -e "SELECT COUNT(*) FROM ncs_sim_dwd.dwd_charging_order;
SELECT COUNT(*) FROM ncs_sim_ads.ads_revenue_trend;"
ls -lh /home/hadoop/dashboard/sim_data/
```

## 五、大屏测试切换

- 后端读**正式数据**：`/home/hadoop/dashboard/data/`（真实，默认）
- 后端读**模拟数据**：把 app.py 的 DATA 改成 `/home/hadoop/dashboard/sim_data/`（测完改回）

## 六、清理模拟库（不影响正式库）

```bash
hive -e "DROP DATABASE ncs_sim_ods CASCADE; DROP DATABASE ncs_sim_dwd CASCADE;
DROP DATABASE ncs_sim_dws CASCADE; DROP DATABASE ncs_sim_ads CASCADE;"
hdfs dfs -rm -r /ncs/sim_ods   # 外部表 DROP 不删 HDFS 文件，需手动清
```
