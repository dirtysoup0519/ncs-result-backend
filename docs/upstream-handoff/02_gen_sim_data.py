# -*- coding: utf-8 -*-
"""
gen_sim_data.py   NCS 充电桩项目 · 模拟数据生成器（贴合真实数据特征版）

用途：
  1) 链路测试：真实数据未到位时，生成同结构 CSV 验证 ODS→DWD→DWS/ADS 全链路
  2) 容量验证：生成更大规模数据，验证 Hive 处理能力与大屏性能
  3) 交付展示：作为"数据模拟"环节的成果（数据集-第X组）

输出与老师真实数据【同结构同特征】：
  - 表头与真实 CSV 完全一致（订单22列/监测11列/站点8列）
  - stationId/locationId 为纯数字风格
  - created 异常年份(0014/0015) 默认 100%（模拟真实数据）
  - record_time 为科学计数法毫秒时间戳（如 1.56E+12）
  - 费用 0 值比例可配（真实数据约 88.8%）
  - 充电电流为负值（真实数据 -22~-74A）

用法：
  python gen_sim_data.py                     # 默认 5000 订单、2019 年、全异常年份
  python gen_sim_data.py --orders 100000     # 生成 10 万订单（容量测试）
  python gen_sim_data.py --orders 5000 --year 2026 --abnormal 0.01 --zero-fee 0.3
"""
import csv, os, random, argparse
from datetime import datetime, timedelta

def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--orders", type=int, default=5000, help="订单数量（默认5000）")
    ap.add_argument("--year", type=int, default=2019, help="数据年份（默认2019，贴合真实数据）")
    ap.add_argument("--abnormal", type=float, default=1.0, help="created异常年份比例（默认1.0=全部0014/0015）")
    ap.add_argument("--zero-fee", type=float, default=0.5, help="充电费用为0的比例（默认0.5）")
    ap.add_argument("--stations", type=int, default=105, help="站点数量（默认105，与真实一致）")
    ap.add_argument("--out", default=os.path.dirname(os.path.abspath(__file__)), help="输出目录")
    ap.add_argument("--seed", type=int, default=42)
    return ap.parse_args()

def main():
    a = parse_args()
    random.seed(a.seed)
    os.makedirs(a.out, exist_ok=True)
    YEAR = a.year

    # ---------- 1) 站点元数据（纯数字 ID，郑州风格站名） ----------
    zones = ["高新区", "二七区", "金水区", "郑东新区", "中原区", "管城回族区", "惠济区", "上街区"]
    roads = ["科学大道", "嵩山路", "东风东路", "航海路", "中原路", "文化路", "花园路", "经三路", "农业路", "陇海路"]
    stations = []
    for i in range(1, a.stations + 1):
        sid = 100000 + i
        lid = 400000 + (i % 25) * 10 + i % 10
        ft = random.choice([1, 2, 3, 4])
        zone = zones[i % len(zones)]
        road = roads[i % len(roads)]
        stations.append([
            str(sid), str(lid), str(ft),
            "%s%s·充电站%d号" % (zone, road, i),
            "河南省郑州市%s%s" % (zone, road),
            str(random.randint(1, 20)),
            random.choice(["00:00-24:00", "06:00-24:00", "06:00-22:00"]),
            "%d/%d/%d" % (YEAR, random.randint(1, 9), random.randint(1, 28)),
        ])
    meta_header = "stationId,locationId,facilityType,station_name,address,device_count,open_time,update_time"

    # ---------- 2) 订单（一笔订单一行） ----------
    WEEKDAYS = ["Mon", "Tues", "Wed", "Thurs", "Fri", "Sat", "Sun"]
    def hour_weight(h):
        if 8 <= h <= 11: return 3.0
        if 14 <= h <= 17: return 2.5
        if 19 <= h <= 22: return 3.5
        if h <= 5: return 0.8
        return 1.0
    order_header = ("sessionId,kwhTotal,charging_fees,created,ended,startTime,endTime,"
                    "chargeTimeHrs,weekday,platform,userId,stationId,locationId,"
                    "managerVehicle,facilityType,Mon,Tues,Wed,Thurs,Fri,Sat,Sun")

    orders = []
    for seq in range(1, a.orders + 1):
        st = random.choice(stations)
        ft = int(st[2])
        if ft == 1:      # 交流慢充
            hours = round(random.uniform(1.0, 8.0), 2)
            power, price = 7.0, random.uniform(0.9, 1.4)
        elif ft == 2:    # 直流快充
            hours = round(random.uniform(0.3, 3.0), 2)
            power, price = random.choice([60.0, 120.0]), random.uniform(1.4, 1.9)
        else:            # 交直流/其他
            hours = round(random.uniform(0.4, 6.0), 2)
            power, price = random.choice([7.0, 60.0]), random.uniform(1.2, 1.7)
        kwh = round(hours * power * random.uniform(0.7, 0.95), 2)
        # 费用：按参数比例置 0（模拟真实数据高比例免费订单）
        fees = 0.0 if random.random() < a.zero_fee else round(kwh * price, 2)
        h = random.choices(range(24), weights=[hour_weight(x) for x in range(24)])[0]
        mon = random.randint(1, 12)
        day = random.randint(1, 28)
        created = datetime(YEAR, mon, day, h, random.randint(0, 59), random.randint(0, 59))
        ended = created + timedelta(hours=hours * random.uniform(0.95, 1.05))
        # created 异常年份处理
        if random.random() < a.abnormal:
            y_ab = random.choice([2014, 2015])  # 源数据特征 0014/0015
            created_str = "00%02d-%02d-%02d %02d:%02d:%02d" % (
                y_ab % 100, mon, day, created.hour, created.minute, created.second)
            ended_str = created_str
        else:
            created_str = created.strftime("%Y-%m-%d %H:%M:%S")
            ended_str = ended.strftime("%Y-%m-%d %H:%M:%S")
        wk = created.weekday()
        platform = random.choices(["android", "ios", "web"], weights=[0.34, 0.66, 0.002])[0]
        orders.append([
            str(1000000 + seq), "%.2f" % kwh, "%.2f" % fees, created_str, ended_str,
            "%02d" % created.hour, "%02d" % ended.hour, "%.2f" % hours,
            WEEKDAYS[wk], platform,
            str(random.randint(100000, 999999)), st[0], st[1],
            "1" if random.random() < 0.05 else "0", st[2],
            *["1" if i == wk else "0" for i in range(7)],
        ])

    # ---------- 3) 充电过程监测（60% 订单有监测，每会话多条采样） ----------
    proc_header = ("esd,record_time,soc,pack_voltage (V),charge_current (A),"
                   "max_cell_voltage (V),min_cell_voltage (V),max_temperature (℃),"
                   "min_temperature (℃),available_energy (kw),available_capacity (Ah)")
    process = []
    for o in orders:
        if random.random() > 0.6:
            continue
        try:
            parsed = datetime.strptime(o[3], "%Y-%m-%d %H:%M:%S")
            base = parsed if parsed.year >= 2000 else datetime(YEAR, 9, 1, random.randint(8, 20), 0, 0)
        except ValueError:
            base = datetime(YEAR, 9, 1, random.randint(8, 20), 0, 0)
        kwh = float(o[1])
        n_points = random.randint(5, 20)
        soc = random.uniform(15, 45)
        energy = 0.0
        cap = random.uniform(60, 120)
        for p in range(n_points):
            ts = int((base + timedelta(minutes=5 * p)).timestamp() * 1000)
            soc = min(100.0, soc + random.uniform(2.0, 4.5))
            if p == n_points - 1:
                soc = random.uniform(92, 100)
            v = 300 + soc * 0.9 + random.uniform(-3, 3)
            i_cur = -random.uniform(22, 74)          # 负值电流（真实特征）
            mv = 3.5 + soc / 100 * 0.6 + random.uniform(-0.05, 0.05)
            mi = mv - random.uniform(0.05, 0.3)
            mt = 32 + random.uniform(-1, 3)          # 温度 32~37℃（真实特征）
            nt = mt - random.uniform(1, 4)
            energy = min(100.0, energy + kwh / n_points * random.uniform(0.8, 1.2))
            process.append([
                o[0], "%.2E" % ts, "%.1f" % soc, "%.1f" % v, "%.1f" % i_cur,
                "%.3f" % mv, "%.3f" % mi, "%.1f" % mt, "%.1f" % nt,
                "%.2f" % energy, "%.2f" % cap,
            ])

    # ---------- 输出 ----------
    files = [
        ("nvv2t.csv", order_header, orders),
        ("dsv13r2.csv", proc_header, process),
        ("nvv2t_md_end.csv", meta_header, stations),
    ]
    for fname, header, data in files:
        path = os.path.join(a.out, fname)
        with open(path, "w", newline="", encoding="utf-8-sig") as f:  # utf-8-sig 带BOM（与真实一致）
            w = csv.writer(f)
            w.writerow(header.split(","))
            w.writerows(data)
        print("已生成 %s（%d 行）-> %s" % (fname, len(data), path))
    print("完成：订单 %d / 监测 %d / 站点 %d，年份 %d，异常比例 %.0f%%" % (
        len(orders), len(process), len(stations), YEAR, a.abnormal * 100))

if __name__ == "__main__":
    main()
