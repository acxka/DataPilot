# -*- coding: utf-8 -*-
"""DataPilot 示例数据集生成器（纯标准库，随机种子固定，可完全复现）。

业务背景：一家区域连锁家电零售企业「云启电器」，2024-2025 两年经营数据。
数据里刻意埋了 3 个可被 Agent 挖出来的业务"坑"：
  1) 2025-10 华东区销售额同比大跌（主因：小家电供应链缺货 + 去年同期华东专场大促抬高基数）
  2) 线上渠道退货率显著高于线下（数码品类尤甚）
  3) 部分门店库存周转天数异常（滞销 + 缺货并存）
运行：python data/build_db.py
"""
import os
import random
import sqlite3
from datetime import date, timedelta

SEED = 42
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "retail.db")
START = date(2024, 1, 1)
END = date(2025, 12, 31)

REGIONS = ["华东", "华南", "华北", "西南", "东北"]
CITIES = {
    "华东": [("上海", "上海"), ("杭州", "浙江"), ("南京", "江苏"), ("苏州", "江苏")],
    "华南": [("广州", "广东"), ("深圳", "广东")],
    "华北": [("北京", "北京"), ("天津", "天津")],
    "西南": [("成都", "四川"), ("重庆", "重庆")],
    "东北": [("沈阳", "辽宁"), ("哈尔滨", "黑龙江")],
}
CATEGORIES = {
    "大家电": [("冰箱", 2600, 4200), ("洗衣机", 1800, 3200), ("空调", 2200, 4800)],
    "小家电": [("吸尘器", 400, 1200), ("电饭煲", 200, 600), ("空气炸锅", 180, 500)],
    "数码": [("手机", 1800, 6500), ("耳机", 150, 1200), ("平板", 1500, 4200)],
    "配件": [("数据线", 15, 60), ("充电头", 30, 150), ("保护壳", 20, 90)],
}
# 品类月度季节性系数（1-12 月）
SEASON = {
    "大家电": [0.85, 0.8, 1.0, 0.95, 1.05, 1.3, 1.45, 1.4, 1.15, 1.1, 1.25, 1.1],
    "小家电": [0.9, 0.85, 0.95, 0.9, 0.95, 1.25, 1.2, 1.15, 1.1, 1.15, 1.5, 1.2],
    "数码": [0.95, 0.9, 0.95, 0.9, 1.0, 1.15, 1.1, 1.15, 1.2, 1.0, 1.45, 1.3],
    "配件": [1.0, 0.95, 1.0, 0.95, 1.0, 1.1, 1.1, 1.1, 1.05, 1.05, 1.3, 1.2],
}
LEVELS = ["普通", "银卡", "金卡", "钻石"]
CHANNELS = ["线下", "线上"]


def month_days(y, m):
    return [d for d in (START + timedelta(days=i) for i in range((END - START).days + 1))
            if d.year == y and d.month == m]


def build():
    rnd = random.Random(SEED)
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.executescript("""
        CREATE TABLE regions (region_id INTEGER PRIMARY KEY, region_name TEXT, manager TEXT);
        CREATE TABLE stores (store_id INTEGER PRIMARY KEY, store_name TEXT, region_id INTEGER,
                             city TEXT, province TEXT, channel_scope TEXT, open_date TEXT,
                             area_sqm REAL, FOREIGN KEY(region_id) REFERENCES regions(region_id));
        CREATE TABLE products (product_id INTEGER PRIMARY KEY, product_name TEXT, category TEXT,
                               subcategory TEXT, unit_price REAL, cost REAL, launch_date TEXT, brand TEXT);
        CREATE TABLE customers (customer_id INTEGER PRIMARY KEY, name TEXT, level TEXT,
                                region_id INTEGER, join_date TEXT, phone_mask TEXT);
        CREATE TABLE promotions (promo_id INTEGER PRIMARY KEY, promo_name TEXT, promo_type TEXT,
                                 start_date TEXT, end_date TEXT, discount_rate REAL, scope TEXT, region_id INTEGER);
        CREATE TABLE orders (order_id TEXT PRIMARY KEY, order_date TEXT, store_id INTEGER,
                             customer_id INTEGER, channel TEXT, status TEXT, promo_id INTEGER,
                             total_amount REAL);
        CREATE TABLE order_items (order_id TEXT, product_id INTEGER, quantity INTEGER,
                                  unit_price REAL, discount REAL, amount REAL);
        CREATE TABLE inventory_daily (snapshot_date TEXT, store_id INTEGER, product_id INTEGER,
                                      stock_qty INTEGER, stockout_flag INTEGER, replenish_qty INTEGER);
        CREATE TABLE returns (return_id TEXT PRIMARY KEY, order_id TEXT, product_id INTEGER,
                              return_date TEXT, quantity INTEGER, reason TEXT, refund_amount REAL);
        CREATE INDEX idx_orders_date ON orders(order_date);
        CREATE INDEX idx_orders_store ON orders(store_id);
        CREATE INDEX idx_items_order ON order_items(order_id);
        CREATE INDEX idx_inv_date_store ON inventory_daily(snapshot_date, store_id);
    """)

    # 区域 / 门店
    regions = [(i + 1, r, rnd.choice(["王磊", "李娜", "张伟", "陈静", "刘洋"])) for i, r in enumerate(REGIONS)]
    cur.executemany("INSERT INTO regions VALUES (?,?,?)", regions)
    stores = []
    sid = 0
    for rid, rname in enumerate(REGIONS, start=1):
        for city, prov in CITIES[rname]:
            sid += 1
            stores.append((sid, "%s%s店" % (city, rnd.choice(["旗舰", "中心", "万象", "印象"])),
                           rid, city, prov, rnd.choice(["全渠道", "全渠道", "线下"]),
                           str(date(rnd.randint(2015, 2022), rnd.randint(1, 12), rnd.randint(1, 28))),
                           round(rnd.uniform(800, 2600), 1)))
    cur.executemany("INSERT INTO stores VALUES (?,?,?,?,?,?,?,?)", stores)

    # 商品
    products = []
    pid = 0
    brands = ["自营", "美的", "海尔", "小米", "苏泊尔", "九阳", "戴森", "联想"]
    for cat, subs in CATEGORIES.items():
        for sub, lo, hi in subs:
            for k in range(5):
                pid += 1
                base = rnd.uniform(lo, hi)
                models = ["S", "Pro", "Max", "Air", "青春版"]
                products.append((pid, "%s%s%d" % (sub, models[k], rnd.randint(1, 99)), cat, sub,
                                 round(base, 0), round(base * rnd.uniform(0.62, 0.78), 0),
                                 str(date(rnd.randint(2022, 2024), rnd.randint(1, 12), rnd.randint(1, 28))),
                                 rnd.choice(brands)))
    cur.executemany("INSERT INTO products VALUES (?,?,?,?,?,?,?,?)", products)
    prod_cat = {p[0]: p[2] for p in products}
    prod_price = {p[0]: p[4] for p in products}
    prod_sub = {p[0]: p[3] for p in products}

    # 客户
    customers = []
    for cid in range(1, 3001):
        rid = rnd.randint(1, 5)
        customers.append((cid, "会员%05d" % cid, rnd.choices(LEVELS, [0.55, 0.25, 0.15, 0.05])[0],
                          rid, str(date(rnd.randint(2020, 2025), rnd.randint(1, 12), rnd.randint(1, 28))),
                          "1%02d****%02d" % (rnd.randint(0, 99), rnd.randint(0, 99))))
    cur.executemany("INSERT INTO customers VALUES (?,?,?,?,?,?)", customers)
    cust_region = {c[0]: c[3] for c in customers}

    # 促销活动
    promos = []
    promo_defs = [
        ("618 年中大促", "满减", 2024, 6, 1, 2024, 6, 20, 0.10, "全网", None),
        ("双11 全球狂欢", "满减", 2024, 11, 1, 2024, 11, 12, 0.18, "全网", None),
        ("年货节", "满减", 2025, 1, 10, 2025, 2, 5, 0.12, "全网", None),
        ("618 年中大促", "满减", 2025, 6, 1, 2025, 6, 20, 0.12, "全网", None),
        ("华东金秋家电节", "专场", 2024, 10, 1, 2024, 10, 31, 0.22, "区域", 1),
        ("双11 全球狂欢", "满减", 2025, 11, 1, 2025, 11, 12, 0.20, "全网", None),
        ("年末清仓", "清仓", 2025, 12, 10, 2025, 12, 31, 0.25, "全网", None),
    ]
    for i, p in enumerate(promo_defs, start=1):
        promos.append((i, p[0], p[1], "%04d-%02d-%02d" % (p[2], p[3], p[4]),
                       "%04d-%02d-%02d" % (p[5], p[6], p[7]), p[8], p[9], p[10]))
    cur.executemany("INSERT INTO promotions VALUES (?,?,?,?,?,?,?,?)", promos)

    def promo_for(d, rid):
        for p in promos:
            s = date(*map(int, p[3].split("-")))
            e = date(*map(int, p[4].split("-")))
            if s <= d <= e and (p[6] == "全网" or (p[6] == "区域" and p[7] == rid)):
                return p[0], p[5]
        return None, 0.0

    # 订单 + 明细
    orders, items = [], []
    oid = 0
    for day_i in range((END - START).days + 1):
        d = START + timedelta(days=day_i)
        season_idx = d.month - 1
        weekday_factor = [0.85, 0.85, 0.9, 0.95, 1.05, 1.3, 1.25][d.weekday()]
        for st in stores:
            sid_, rname, rid, city, prov = st[0], REGIONS[st[2] - 1], st[2], st[3], st[4]
            weight = 1.0 + (0.35 if city in ("上海", "北京", "深圳", "广州") else 0.0)
            # 2025-10 华东区供应链事故：小家电缺货，订单量下滑
            shock = 1.0
            if d.year == 2025 and d.month == 10 and rid == 1:
                shock = 0.68
            n = max(0, int(rnd.gauss(5.2 * weight * weekday_factor * shock, 1.6)))
            promo_id, disc = promo_for(d, rid)
            for _ in range(n):
                oid += 1
                ch = "线上" if rnd.random() < 0.58 else "线下"
                cust = rnd.randint(1, 3000)
                order_id = "O%05d%05d" % (d.year % 100 * 1000 + d.month * 40 + d.day, oid)
                n_items = rnd.choices([1, 2, 3, 4], [0.55, 0.28, 0.13, 0.04])[0]
                total = 0.0
                used = set()
                for _k in range(n_items):
                    pid_ = rnd.randint(1, len(products))
                    if pid_ in used:
                        continue
                    used.add(pid_)
                    cat = prod_cat[pid_]
                    qty = rnd.choices([1, 2, 3], [0.86, 0.11, 0.03])[0]
                    price = prod_price[pid_]
                    # 品类季节性影响购买概率（简化：以折扣体现）
                    dmul = SEASON[cat][season_idx] / 1.15
                    if d.year == 2025 and d.month == 10 and rid == 1 and cat == "小家电":
                        dmul *= 0.35
                    if rnd.random() > min(1.0, 0.55 + 0.35 * dmul):
                        continue
                    d_pct = disc + (0.03 if ch == "线上" else 0.0)
                    if rnd.random() < 0.12:
                        d_pct += rnd.choice([0.03, 0.05, 0.08])
                    d_pct = min(d_pct, 0.4)
                    amount = round(price * qty * (1 - d_pct), 2)
                    items.append((order_id, pid_, qty, round(price, 2), round(d_pct, 2), amount))
                    total += amount
                if total <= 0:
                    continue
                status = rnd.choices(["已完成", "已签收", "已取消", "退款中"], [0.78, 0.14, 0.05, 0.03])[0]
                orders.append((order_id, d.isoformat(), sid_, cust, ch, status,
                               promo_id, round(total, 2)))
    cur.executemany("INSERT INTO orders VALUES (?,?,?,?,?,?,?,?)", orders)
    cur.executemany("INSERT INTO order_items VALUES (?,?,?,?,?,?)", items)

    # 退货（线上退货率约为线下 2.3 倍，数码品类更高）
    returns = []
    rid_ = 0
    order_map = {o[0]: o for o in orders}
    for it in items:
        o = order_map[it[0]]
        cat = prod_cat[it[1]]
        base_rate = 0.021 if o[4] == "线下" else 0.048
        if cat == "数码":
            base_rate *= 1.9
        if rnd.random() < base_rate:
            rid_ += 1
            rdate = date.fromisoformat(o[1]) + timedelta(days=rnd.randint(1, 20))
            reason = rnd.choices(["七天无理由", "质量问题", "尺寸/型号不符", "物流破损", "不想要了"],
                                 [0.42, 0.24, 0.16, 0.1, 0.08])[0]
            returns.append(("R%06d" % rid_, it[0], it[1], rdate.isoformat(), it[2], reason, it[5]))
    cur.executemany("INSERT INTO returns VALUES (?,?,?,?,?,?,?)", returns)

    # 每日库存快照（每周一快照，关键 2025-10 按天快照以支撑缺货归因）
    inv = []
    stock_base = {p[0]: max(5, int(rnd.gauss(60, 25))) for p in products}
    snap_dates = [d for d in (START + timedelta(days=i) for i in range((END - START).days + 1))
                  if d.weekday() == 0 or (d.year == 2025 and d.month in (9, 10, 11))]
    for d in snap_dates:
        for st in stores:
            rid = st[2]
            for p in products:
                pid_ = p[0]
                cat = p[2]
                q = max(0, int(rnd.gauss(stock_base[pid_] * rnd.uniform(0.7, 1.2), 8)))
                # 2025-10 华东小家电持续缺货
                if d.year == 2025 and d.month == 10 and rid == 1 and cat == "小家电":
                    q = int(q * rnd.uniform(0.05, 0.25))
                so = 1 if q <= 3 else 0
                replen = int(rnd.gauss(40, 15)) if q < 15 else 0
                inv.append((d.isoformat(), st[0], pid_, q, so, max(0, replen)))
    cur.executemany("INSERT INTO inventory_daily VALUES (?,?,?,?,?,?)", inv)

    conn.commit()
    cur.execute("VACUUM")
    conn.commit()
    stats = {}
    for t in ["regions", "stores", "products", "customers", "promotions", "orders",
              "order_items", "returns", "inventory_daily"]:
        stats[t] = cur.execute("SELECT COUNT(*) FROM " + t).fetchone()[0]
    print("DB:", DB_PATH, "size=%.1f MB" % (os.path.getsize(DB_PATH) / 1024 / 1024))
    for k, v in stats.items():
        print("  %-16s %8d" % (k, v))
    print("\n-- 校验：2025-10 华东 vs 2024-10 华东销售额 --")
    q = """SELECT substr(order_date,1,7) AS ym, ROUND(SUM(total_amount),2) AS amt, COUNT(*) AS cnt
           FROM orders WHERE store_id IN (SELECT store_id FROM stores WHERE region_id=1)
             AND substr(order_date,1,7) IN ('2024-10','2025-10') GROUP BY ym ORDER BY ym"""
    for row in cur.execute(q):
        print("  ", row)
    print("-- 校验：小家电线上/线下退货率 --")
    q = """SELECT o.channel, ROUND(1.0*COUNT(r.return_id)/COUNT(i.order_id),4) AS return_rate
           FROM order_items i JOIN orders o ON o.order_id=i.order_id
           LEFT JOIN returns r ON r.order_id=i.order_id AND r.product_id=i.product_id
           JOIN products p ON p.product_id=i.product_id WHERE p.category='小家电'
           GROUP BY o.channel"""
    for row in cur.execute(q):
        print("  ", row)
    conn.close()


if __name__ == "__main__":
    build()
