# -*- coding: utf-8 -*-
"""
gen_aug_sim_data.py   NCS 模拟数据生成器 v2 —— 分布一致版（数据增强）
====================================================================
与真实数据"分布规律一致"的模拟生成器：
  从 real_dist.json（真实数据学习到的分布模型）采样生成，
  订单/监测/站点的分布特征与老师真实数据一致或相似。

分布对齐项（基于真实数据统计）：
  - 小时分布（10-12点、16-17点双高峰）      - 星期分布（周一~五多、周末极少）
  - 月份分布（1~9月递增、10月起骤降）        - 年份异常 0014/0015（99.3% 为 0015）
  - 平台占比（ios 65.8% / android 34% / web 0.2%）
  - 站点热度（真实 105 站长尾分布）          - 设施类型占比（3型54%/2型25%/1型17%/4型3%）
  - 电量/时长/隐含功率分位（kwh=时长x功率，保持相关性）
  - 费用 88.8% 为 0，非0费用 70% 为 0.5 元
  - 监测数据每会话 1 条采样（真实特征）、电流集中在 -22.5A、温度 32~37℃

两种模式：
  1) 分布采样（默认）：按真实分布生成全新数据
     python gen_aug_sim_data.py --orders 5000 --out D:\simdata
  2) 数据增强 --augment：对真实数据做"时间偏移+数值扰动+站点重组"
     python gen_aug_sim_data.py --augment --real-dir 真实CSV目录 --offset-days 90 --noise 0.05 --out D:\simdata
"""

import csv, os, json, random, argparse, math
from datetime import datetime, timedelta

PS = [0, 5, 10, 20, 30, 40, 50, 60, 70, 80, 90, 95, 100]  # 分位点

def q_sample(qs, ps=None):
    """按分位数线性插值采样一个值（qs 与 ps 长度须一致）"""
    ps = ps or PS
    p = random.uniform(0, 100)
    for i in range(len(ps) - 1):
        if ps[i] <= p <= ps[i + 1]:
            t = (p - ps[i]) / (ps[i + 1] - ps[i])
            return qs[i] + t * (qs[i + 1] - qs[i])
    return qs[-1]

def w_choice(population, weights):
    return random.choices(population, weights=weights, k=1)[0]

HEADER_ORDER = ("sessionId,kwhTotal,charging_fees,created,ended,startTime,endTime,"
                "chargeTimeHrs,weekday,platform,userId,stationId,locationId,"
                "managerVehicle,facilityType,Mon,Tues,Wed,Thurs,Fri,Sat,Sun")
HEADER_PROC = ("esd,record_time,soc,pack_voltage (V),charge_current (A),"
               "max_cell_voltage (V),min_cell_voltage (V),max_temperature (℃),"
               "min_temperature (℃),available_energy (kw),available_capacity (Ah)")
HEADER_META = "stationId,locationId,facilityType,station_name,address,device_count,open_time,update_time"

def load_dist(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def gen_sampled(D, orders, seed):
    """模式1：分布采样生成"""
    random.seed(seed)
    WEEKDAYS = ["Mon", "Tues", "Wed", "Thurs", "Fri", "Sat", "Sun"]
    wd_names, wd_weights = zip(*D["weekday_dist"].items())
    mon_names, mon_weights = zip(*D["month_dist"].items())
    yr_names, yr_weights = zip(*D["year_dist"].items())
    hr_names, hr_weights = zip(*D["hour_dist"].items())
    pl_names, pl_weights = zip(*D["platform_dist"].items())
    ft_names, ft_weights = zip(*D["facility_dist"].items())
    st_ids, st_weights = D["station_ids"], D["station_weights"]
    # stationId -> locationId 映射（真实站点表）
    loc_map = {m["stationId"]: m["locationId"] for m in D["meta"]}

    rows = []
    for seq in range(1, orders + 1):
        wd = w_choice(wd_names, wd_weights)
        mon = w_choice(mon_names, mon_weights)
        yr = w_choice(yr_names, yr_weights)
        hh = int(w_choice(hr_names, hr_weights))
        dd = random.randint(1, 28)
        mi, ss = random.randint(0, 59), random.randint(0, 59)
        created = "00%s-%s-%02d %02d:%02d:%02d" % (yr, mon, dd, hh, mi, ss)

        hours = max(0.01, q_sample(D["hours_quantiles"]))
        power = q_sample(D["power_quantiles"])
        kwh = min(hours * power, D["kwh_quantiles"][-1])
        kwh = round(max(0.0, kwh), 2)

        if random.random() < D["fee_zero_ratio"]:
            fees = 0.0
        else:
            fees = min(kwh * q_sample(D["price_quantiles"], [0, 25, 50, 75, 100]), D["fee_pos_quantiles"][-1])
        fees = round(max(0.0, fees), 2)

        end_h = (hh + max(1, int(math.ceil(hours)))) % 24
        ended = "00%s-%s-%02d %02d:%02d:%02d" % (yr, mon, dd, end_h, mi, ss)

        platform = w_choice(pl_names, pl_weights)
        station = w_choice(st_ids, st_weights)
        ft = w_choice(ft_names, ft_weights)
        rows.append([
            str(1000000 + seq), "%.2f" % kwh, "%.2f" % fees, created, ended,
            "%02d" % hh, "%02d" % end_h, "%.2f" % hours,
            wd, platform, str(random.randint(100000, 999999)),
            station, loc_map.get(station, "400001"),
            "1" if random.random() < D["manager_ratio"] else "0", ft,
            *["1" if w == wd else "0" for w in WEEKDAYS],
        ])
    return rows

def gen_process_sampled(D, orders):
    """监测数据：真实特征 = 每会话 1 条采样，会话占比 = 真实 过程行数/订单数（≈47%）"""
    rows = []
    p_proc = D["proc_cnt"] / D["order_cnt"]   # 1594/3395 ≈ 0.47
    for o in orders:
        if random.random() > p_proc:
            continue
        ts = int(datetime(2019, 1, 1).timestamp() * 1000) + random.randint(0, 300 * 86400 * 1000)
        soc = q_sample(D["soc_q"])
        v = q_sample(D["volt_q"])
        cur = q_sample(D["current_q"])
        mt = q_sample(D["temp_q"])
        nt = mt - random.uniform(1, 4)
        rows.append([
            o[0], "%.2E" % ts, "%.1f" % soc, "%.1f" % v, "%.1f" % cur,
            "%.3f" % (v / 100 + random.uniform(0.03, 0.05)),
            "%.3f" % (v / 100 - random.uniform(0.02, 0.03)),
            "%.1f" % mt, "%.1f" % nt,
            "%.2f" % min(100.0, float(o[1]) * random.uniform(0.9, 1.1)),
            "%.2f" % random.uniform(60, 120),
        ])
    return rows

def gen_augment(D, real_dir, offset_days, noise, out):
    """模式2：数据增强 —— 真实数据时间偏移 + 数值扰动 + 站点重组"""
    with open(os.path.join(real_dir, "nvv2t.csv"), encoding="utf-8-sig") as f:
        ords = list(csv.DictReader(f))
    with open(os.path.join(real_dir, "dsv13r2.csv"), encoding="utf-8-sig") as f:
        procs = list(csv.DictReader(f))
    with open(os.path.join(real_dir, "nvv2t_md_end.csv"), encoding="utf-8-sig") as f:
        meta = list(csv.DictReader(f))

    def shift_time(s, days):
        y = int(s[2:4]); m = int(s[5:7]); d = int(s[8:10]); rest = s[10:]
        dt = datetime(2000 + y, m, d) + timedelta(days=days)
        return "00%02d-%02d-%02d%s" % (dt.year % 100, dt.month, dt.day, rest)

    # 站点重组映射
    old_ids = [m["stationId"] for m in meta]
    new_ids = old_ids[:]
    random.shuffle(new_ids)
    id_map = dict(zip(old_ids, new_ids))

    out_ords = []
    for o in ords:
        n = dict(o)
        n["created"] = shift_time(n["created"], offset_days)
        n["ended"] = shift_time(n["ended"], offset_days)
        n["kwhTotal"] = "%.2f" % (float(n["kwhTotal"]) * (1 + random.uniform(-noise, noise)))
        n["charging_fees"] = "%.2f" % (float(n["charging_fees"]) * (1 + random.uniform(-noise, noise)))
        n["stationId"] = id_map[n["stationId"]]
        out_ords.append(n)
    out_procs = []
    for p in procs:
        n = dict(p)
        n["esd"] = id_map.get(n["esd"], n["esd"])
        n["charge_current (A)"] = "%.1f" % (float(n["charge_current (A)"]) * (1 + random.uniform(-noise, noise)))
        out_procs.append(n)
    out_meta = []
    for m in meta:
        n = dict(m)
        n["stationId"] = id_map[n["stationId"]]
        out_meta.append(n)
    return out_ords, out_procs, out_meta

def write_csv(path, header, rows):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(header.split(","))
        w.writerows(rows)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--orders", type=int, default=5000)
    ap.add_argument("--out", default=os.path.dirname(os.path.abspath(__file__)))
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--dist", default=None, help="real_dist.json 路径（默认脚本同目录）")
    ap.add_argument("--augment", action="store_true", help="数据增强模式（对真实数据偏移/扰动/重组）")
    ap.add_argument("--real-dir", default=None, help="增强模式：真实 CSV 目录")
    ap.add_argument("--offset-days", type=int, default=90, help="增强模式：时间偏移天数")
    ap.add_argument("--noise", type=float, default=0.05, help="增强模式：数值扰动幅度")
    a = ap.parse_args()

    dist_path = a.dist or os.path.join(os.path.dirname(os.path.abspath(__file__)), "real_dist.json")
    D = load_dist(dist_path)
    os.makedirs(a.out, exist_ok=True)

    if a.augment:
        if not a.real_dir:
            print("增强模式需要 --real-dir 真实CSV目录"); return
        ords, procs, meta = gen_augment(D, a.real_dir, a.offset_days, a.noise, a.out)
        print("增强模式：偏移%d天、扰动±%.0f%%，输出 %d 订单 / %d 监测 / %d 站点"
              % (a.offset_days, a.noise * 100, len(ords), len(procs), len(meta)))
    else:
        random.seed(a.seed)
        ords = gen_sampled(D, a.orders, a.seed)
        procs = gen_process_sampled(D, ords)
        meta = [dict(m) for m in D["meta"]]
        print("分布采样模式：%d 订单 / %d 监测 / %d 站点" % (len(ords), len(procs), len(meta)))

    write_csv(os.path.join(a.out, "nvv2t.csv"), HEADER_ORDER, ords)
    write_csv(os.path.join(a.out, "dsv13r2.csv"), HEADER_PROC, procs)
    write_csv(os.path.join(a.out, "nvv2t_md_end.csv"), HEADER_META, meta)
    print("完成：nvv2t.csv / dsv13r2.csv / nvv2t_md_end.csv -> %s" % a.out)

if __name__ == "__main__":
    main()
