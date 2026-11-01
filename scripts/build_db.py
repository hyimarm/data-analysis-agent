"""生成业务演示库：客户 / 商品 / 订单 / 订单明细。

设计时刻意留了三个陷阱，用来考察 SQL 是否严谨：
1. 订单有 4 种状态，只有 paid 才算真实成交（GMV 要排除 refunded / cancelled）
2. 订单金额 = 明细合计 - 优惠 + 运费，不能只看某一列
3. 明细里的单价是"下单时价格"，可能和商品当前价格不同（历史价格）
"""

from __future__ import annotations

import random
import sqlite3
from datetime import date, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "business.db"

SEED = 42
START_DATE = date(2025, 11, 1)
END_DATE = date(2026, 10, 31)

CITIES = {
    "华东": ["上海", "杭州", "南京", "苏州"],
    "华北": ["北京", "天津", "石家庄"],
    "华南": ["广州", "深圳", "厦门"],
    "西南": ["成都", "重庆", "昆明"],
}
SURNAMES = "赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许"
GIVEN = "伟芳娜秀英敏静丽强磊军洋勇艳杰娟涛明超霞平刚"
CATEGORIES = ["手机", "笔记本", "耳机", "配件", "智能家居"]
LEVELS = [("普通", 0.55), ("白银", 0.25), ("黄金", 0.15), ("钻石", 0.05)]
CHANNELS = [("app", 0.50), ("web", 0.30), ("mini", 0.20)]
STATUSES = [("paid", 0.88), ("refunded", 0.07), ("cancelled", 0.03), ("pending", 0.02)]


def pick_weighted(pairs: list[tuple[str, float]]) -> str:
    """按权重随机取一个值。用累积概率，避免手写一堆 if。"""
    r = random.random()
    acc = 0.0
    for name, weight in pairs:
        acc += weight
        if r <= acc:
            return name
    return pairs[-1][0]


def random_date() -> str:
    days = (END_DATE - START_DATE).days
    return (START_DATE + timedelta(days=random.randint(0, days))).isoformat()


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        DROP TABLE IF EXISTS order_items;
        DROP TABLE IF EXISTS orders;
        DROP TABLE IF EXISTS products;
        DROP TABLE IF EXISTS customers;

        CREATE TABLE customers (
            id           INTEGER PRIMARY KEY,
            name         TEXT    NOT NULL,
            city         TEXT    NOT NULL,
            region       TEXT    NOT NULL,
            level        TEXT    NOT NULL,
            register_date TEXT   NOT NULL
        );

        CREATE TABLE products (
            id          INTEGER PRIMARY KEY,
            name        TEXT    NOT NULL,
            category    TEXT    NOT NULL,
            list_price  REAL    NOT NULL,
            launch_date TEXT    NOT NULL
        );

        CREATE TABLE orders (
            id          INTEGER PRIMARY KEY,
            customer_id INTEGER NOT NULL,
            order_date  TEXT    NOT NULL,
            status      TEXT    NOT NULL,
            channel     TEXT    NOT NULL,
            discount    REAL    NOT NULL,
            freight     REAL    NOT NULL
        );

        CREATE TABLE order_items (
            id         INTEGER PRIMARY KEY,
            order_id   INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            quantity   INTEGER NOT NULL,
            unit_price REAL    NOT NULL
        );
    """)


def main() -> None:
    random.seed(SEED)
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if DB_PATH.exists():
        DB_PATH.unlink()

    conn = sqlite3.connect(DB_PATH)
    create_schema(conn)

    # 客户 5000
    customers = []
    for cid in range(1, 5001):
        region = random.choice(list(CITIES))
        city = random.choice(CITIES[region])
        name = random.choice(SURNAMES) + "".join(
            random.choice(GIVEN) for _ in range(random.randint(1, 2))
        )
        customers.append(
            (cid, name, city, region, pick_weighted(LEVELS), random_date())
        )
    conn.executemany("INSERT INTO customers VALUES (?,?,?,?,?,?)", customers)

    # 商品 600
    products = []
    for pid in range(1, 601):
        category = random.choice(CATEGORIES)
        base = {"手机": 3000, "笔记本": 6000, "耳机": 500, "配件": 80, "智能家居": 800}[category]
        products.append(
            (
                pid,
                f"{category}-{pid:03d}",
                category,
                round(base * random.uniform(0.6, 1.6), 2),
                random_date(),
            )
        )
    conn.executemany("INSERT INTO products VALUES (?,?,?,?,?)", products)

    # 订单 60000 + 明细
    price_by_product = {p[0]: p[3] for p in products}
    orders, items = [], []
    item_id = 1
    for oid in range(1, 60001):
        status = pick_weighted(STATUSES)
        orders.append(
            (
                oid,
                random.randint(1, 5000),
                random_date(),
                status,
                pick_weighted(CHANNELS),
                round(random.choice([0, 0, 0, 10, 20, 50]) * random.random(), 2),
                round(random.choice([0, 0, 8, 12, 15]), 2),
            )
        )
        for _ in range(random.randint(1, 4)):
            pid = random.randint(1, 600)
            items.append(
                (
                    item_id,
                    oid,
                    pid,
                    random.randint(1, 3),
                    round(price_by_product[pid] * random.uniform(0.85, 1.0), 2),
                )
            )
            item_id += 1

    conn.executemany("INSERT INTO orders VALUES (?,?,?,?,?,?,?)", orders)
    conn.executemany(
        "INSERT INTO order_items VALUES (?,?,?,?,?)", items
    )
    conn.commit()

    for table in ("customers", "products", "orders", "order_items"):
        n = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"{table:12s} {n:>8,d} 行")
    conn.close()
    print(f"\n数据库: {DB_PATH}")


if __name__ == "__main__":
    main()