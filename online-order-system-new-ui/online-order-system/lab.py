"""Analysis endpoints: algorithm-based sorting, benchmark lab, visualiser, bulk data, analytics."""
import math
import os
import random
import sqlite3
import time
from datetime import datetime, timedelta, timezone

from flask import Blueprint, current_app, jsonify, request

import routing
import sorting

lab_bp = Blueprint("lab", __name__)

QUADRATIC_LIMIT_BENCH = 3000      # O(n^2) algorithms are skipped above this size in the benchmark
QUADRATIC_LIMIT_ORDERS = 5000     # ...and when sorting live orders
MAX_SIZE = 100_000

SORT_COLUMNS = {
    "created_at": ("created_at", lambda v: v),
    "total": ("total", float),
    "status": ("status", lambda v: v),
    "customer": ("customer_name", lambda v: (v or "").lower()),
    "id": ("id", int),
}

SAMPLE_PRODUCTS = [("Notebook", 120), ("Gel pen set", 80), ("Desk lamp", 899), ("USB-C cable", 349),
                   ("Backpack", 1799), ("Water bottle", 450), ("Headphones", 2999), ("Mouse pad", 299),
                   ("Keyboard", 1499), ("Monitor stand", 1199), ("Phone stand", 249), ("Planner", 399)]
FIRST = ["Aarav", "Vihaan", "Ananya", "Diya", "Rohan", "Isha", "Kabir", "Meera", "Arjun", "Saanvi", "Rahul",
         "Priya", "Karan", "Neha", "Aditya", "Simran", "Harpreet", "Gurpreet", "Manav", "Tanvi"]
LAST = ["Sharma", "Verma", "Singh", "Gill", "Kaur", "Mehta", "Gupta", "Patel", "Reddy", "Nair", "Joshi",
        "Bansal", "Chopra", "Malhotra", "Sethi", "Arora", "Bhatia", "Kapoor", "Sandhu", "Dhillon"]
STATUS_WEIGHTS = [("pending", 20), ("confirmed", 18), ("shipped", 20), ("delivered", 36), ("cancelled", 6)]


def conn():
    c = sqlite3.connect(current_app.config["DB_PATH"])
    c.row_factory = sqlite3.Row
    return c


def bad(msg, code=400):
    return jsonify(error=msg), code


def make_data(n, case, rnd):
    values = rnd.sample(range(1, n * 10 + 1), n)               # distinct values
    if case == "sorted":
        values.sort()
    elif case == "reversed":
        values.sort(reverse=True)
    elif case == "nearly":
        values.sort()
        for _ in range(max(1, n // 50)):
            i, j = rnd.randrange(n), rnd.randrange(n)
            values[i], values[j] = values[j], values[i]
    return values


@lab_bp.get("/api/algorithms")
def algorithms():
    return jsonify(sorting.info())


# ---------- Sort live orders with a chosen algorithm ----------
@lab_bp.get("/api/sort-orders")
def sort_orders():
    algo = request.args.get("algorithm", "merge")
    col, keyfn = SORT_COLUMNS.get(request.args.get("sort_by", "created_at"), (None, None))
    if col is None:
        return bad(f"sort_by must be one of {list(SORT_COLUMNS)}")
    if algo != "sql" and algo not in sorting.ALGORITHMS:
        return bad("unknown algorithm")
    desc = request.args.get("order", "desc").lower() != "asc"
    where, params = [], []
    if request.args.get("status"):
        where.append("status = ?"); params.append(request.args["status"])
    if request.args.get("customer"):
        where.append("customer_name LIKE ?"); params.append(f"%{request.args['customer']}%")
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    size = min(100, max(1, int(request.args.get("page_size", 25))))
    page = max(1, int(request.args.get("page", 1)))

    c = conn()
    try:
        if algo == "sql":
            t0 = time.perf_counter()
            rows = c.execute(f"SELECT * FROM orders{clause} ORDER BY {col} {'DESC' if desc else 'ASC'}, id DESC",
                             params).fetchall()
            stats = {"comparisons": None, "moves": None, "time_ms": round((time.perf_counter() - t0) * 1000, 4)}
            ordered = [dict(r) for r in rows]
            label = "SQLite ORDER BY"
            meta = {"avg": "O(n log n)", "worst": "O(n log n)", "space": "O(n)"}
        else:
            rows = c.execute(f"SELECT * FROM orders{clause}", params).fetchall()
            n = len(rows)
            meta_algo = sorting.ALGORITHMS[algo]
            if meta_algo["quadratic"] and n > QUADRATIC_LIMIT_ORDERS:
                return bad(f"{meta_algo['label']} is O(n²); {n:,} orders would take too long. "
                           f"Pick merge, quick, heap or shell sort, or filter to under {QUADRATIC_LIMIT_ORDERS:,} orders.")
            by_id = {r["id"]: dict(r) for r in rows}
            items = [(keyfn(r[col]), r["id"]) for r in rows]
            result, stats = sorting.run(algo, items)
            if desc:
                result.reverse()
            ordered = [by_id[i] for _, i in result]
            label = meta_algo["label"]
            meta = {k: meta_algo[k] for k in ("avg", "worst", "space")}
    finally:
        c.close()

    total = len(ordered)
    start = (page - 1) * size
    return jsonify(rows=ordered[start:start + size], total=total, page=page,
                   pages=max(1, math.ceil(total / size)),
                   stats={"algorithm": algo, "label": label, "n": total, **stats, **meta})


# ---------- Benchmark lab ----------
@lab_bp.post("/api/benchmark")
def benchmark():
    body = request.get_json(force=True)
    sizes = sorted({int(s) for s in body.get("sizes", [])})
    names = [a for a in body.get("algorithms", []) if a in sorting.ALGORITHMS]
    case = body.get("case", "random")
    if case not in ("random", "sorted", "reversed", "nearly"):
        return bad("case must be random, sorted, reversed or nearly")
    if not sizes or len(sizes) > 12 or sizes[0] < 2 or sizes[-1] > MAX_SIZE:
        return bad(f"choose 1 to 12 sizes between 2 and {MAX_SIZE:,}")
    if not names:
        return bad("choose at least one algorithm")

    series = {n: [] for n in names}
    skipped = []
    for size in sizes:
        data = make_data(size, case, random.Random(size))          # same data for every algorithm
        repeats = 5 if size <= 500 else 3 if size <= 3000 else 1
        for name in names:
            algo = sorting.ALGORITHMS[name]
            if algo["quadratic"] and size > QUADRATIC_LIMIT_BENCH:
                skipped.append({"algorithm": name, "n": size})
                continue
            out, stats = sorting.run(name, data, repeats=repeats)
            if out != sorted(data):
                return bad(f"{name} returned an unsorted result", 500)
            series[name].append({"n": size, **stats})
    return jsonify(case=case, sizes=sizes, skipped=skipped,
                   series=[{"algorithm": n, "label": sorting.ALGORITHMS[n]["label"], "points": series[n]}
                           for n in names])


# ---------- Step-by-step visualiser ----------
@lab_bp.post("/api/visualize")
def visualize():
    body = request.get_json(force=True)
    name = body.get("algorithm", "bubble")
    if name not in sorting.ALGORITHMS or name == "timsort":
        return bad("pick one of the hand-written algorithms")
    n = min(60, max(5, int(body.get("n", 30))))
    case = body.get("case", "random")
    data = make_data(n, case, random.Random())
    data = [sorted(data).index(v) + 1 for v in data]               # values 1..n for even bar heights
    trace = []
    _, stats = sorting.run(name, data, trace=trace)
    frames = [tuple(data)] + trace
    if len(frames) > 1500:                                         # thin long traces, keep the last frame
        step = math.ceil(len(frames) / 1500)
        frames = frames[::step] + [frames[-1]]
    return jsonify(frames=[list(f) for f in frames], **stats, label=sorting.ALGORITHMS[name]["label"])


# ---------- Sample data ----------
@lab_bp.post("/api/seed")
def seed():
    count = min(50_000, max(1, int((request.get_json(silent=True) or {}).get("count", 1000))))
    rnd = random.Random()
    depot = routing.DEFAULT_DEPOT          # sample orders get delivery points within 12 km of the depot
    c = conn()
    try:
        if not c.execute("SELECT 1 FROM products LIMIT 1").fetchone():
            c.executemany("INSERT INTO products(name, price, stock) VALUES (?,?,?)",
                          [(n, p, 500) for n, p in SAMPLE_PRODUCTS])
        products = c.execute("SELECT id, price FROM products").fetchall()
        customers = [f"{rnd.choice(FIRST)} {rnd.choice(LAST)}" for _ in range(300)]
        statuses = [s for s, w in STATUS_WEIGHTS for _ in range(w)]
        start_id = (c.execute("SELECT COALESCE(MAX(id),0) FROM orders").fetchone()[0]) + 1
        now = datetime.now(timezone.utc)
        orders, items = [], []
        for k in range(count):
            oid = start_id + k
            total = 0.0
            for p in rnd.sample(products, rnd.randint(1, min(4, len(products)))):
                qty = rnd.randint(1, 5)
                total += p["price"] * qty
                items.append((oid, p["id"], qty, p["price"]))
            when = now - timedelta(days=rnd.random() * 90)
            name = rnd.choice(customers)
            lat, lng = routing.random_point_near(rnd, depot["lat"], depot["lng"], 12)   # demo delivery point
            orders.append((oid, name, f"{name.split()[0].lower()}{rnd.randint(1, 99)}@example.com",
                           rnd.choice(statuses), round(total, 2), when.isoformat(),
                           routing.random_address(rnd), lat, lng))
        c.executemany("INSERT INTO orders(id, customer_name, customer_email, status, total, created_at, "
                      "address, lat, lng) VALUES (?,?,?,?,?,?,?,?,?)", orders)
        c.executemany("INSERT INTO order_items(order_id, product_id, quantity, unit_price) VALUES (?,?,?,?)", items)
        c.commit()
    finally:
        c.close()
    return jsonify(added=count)


@lab_bp.post("/api/reset")
def reset():
    c = conn()
    try:
        c.execute("DELETE FROM order_items")
        c.execute("DELETE FROM orders")
        c.commit()
    finally:
        c.close()
    return jsonify(ok=True)


# ---------- Analytics ----------
@lab_bp.get("/api/analytics")
def analytics():
    c = conn()
    try:
        k = c.execute("""SELECT COUNT(*) AS orders,
                                COALESCE(SUM(CASE WHEN status != 'cancelled' THEN total END), 0) AS revenue,
                                COALESCE(AVG(CASE WHEN status != 'cancelled' THEN total END), 0) AS avg_order,
                                COALESCE(SUM(status = 'cancelled'), 0) AS cancelled
                         FROM orders""").fetchone()
        products = c.execute("SELECT COUNT(*) AS n, COALESCE(SUM(stock < 10), 0) AS low FROM products").fetchone()
        by_status = [dict(r) for r in c.execute(
            "SELECT status, COUNT(*) AS count, COALESCE(SUM(total),0) AS revenue FROM orders GROUP BY status")]
        since = (datetime.now(timezone.utc) - timedelta(days=29)).strftime("%Y-%m-%d")
        per_day = {r["d"]: dict(r) for r in c.execute(
            "SELECT substr(created_at,1,10) AS d, COUNT(*) AS orders, SUM(total) AS revenue "
            "FROM orders WHERE substr(created_at,1,10) >= ? GROUP BY d", (since,))}
        daily = []
        for i in range(30):
            d = (datetime.now(timezone.utc) - timedelta(days=29 - i)).strftime("%Y-%m-%d")
            row = per_day.get(d, {})
            daily.append({"day": d, "orders": row.get("orders", 0), "revenue": round(row.get("revenue") or 0, 2)})
        top_products = [dict(r) for r in c.execute(
            """SELECT p.name, SUM(oi.quantity) AS units, SUM(oi.quantity * oi.unit_price) AS revenue
               FROM order_items oi JOIN products p ON p.id = oi.product_id
               JOIN orders o ON o.id = oi.order_id WHERE o.status != 'cancelled'
               GROUP BY p.id ORDER BY revenue DESC LIMIT 8""")]
        top_customers = [dict(r) for r in c.execute(
            """SELECT customer_name AS name, COUNT(*) AS orders, SUM(total) AS revenue FROM orders
               WHERE status != 'cancelled' GROUP BY customer_name ORDER BY revenue DESC LIMIT 8""")]
        totals = [r[0] for r in c.execute("SELECT total FROM orders WHERE status != 'cancelled'")]
    finally:
        c.close()

    histogram = []
    if totals:
        lo, hi = min(totals), max(totals)
        width = (hi - lo) / 10 or 1
        counts = [0] * 10
        for t in totals:
            counts[min(9, int((t - lo) / width))] += 1
        histogram = [{"from": round(lo + i * width), "to": round(lo + (i + 1) * width), "count": counts[i]}
                     for i in range(10)]
    return jsonify(kpis={"orders": k["orders"], "revenue": round(k["revenue"], 2),
                         "avg_order": round(k["avg_order"], 2), "cancelled": k["cancelled"],
                         "products": products["n"], "low_stock": products["low"]},
                   by_status=by_status, daily=daily, top_products=top_products,
                   top_customers=top_customers, histogram=histogram)
