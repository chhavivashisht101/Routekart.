"""Online Order System backend: products, orders, stock handling, sorting, filtering and delivery routes."""
import os
import sqlite3
from datetime import datetime, timezone
from flask import Flask, jsonify, request, g, render_template

import routing

DB_PATH = os.environ.get("DB_PATH", "orders.db")
app = Flask(__name__)
app.config["DB_PATH"] = DB_PATH

ORDER_STATUSES = ("pending", "confirmed", "shipped", "delivered", "cancelled")
# Allowed sort columns map to real SQL columns (prevents SQL injection via sort_by)
ORDER_SORT = {"created_at": "o.created_at", "total": "o.total", "status": "o.status",
              "customer": "o.customer_name", "id": "o.id"}
PRODUCT_SORT = {"name": "name", "price": "price", "stock": "stock", "id": "id"}


def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_):
    d = g.pop("db", None)
    if d:
        d.close()


def init_db():
    con = sqlite3.connect(DB_PATH)
    con.executescript("""
    CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        price REAL NOT NULL CHECK(price >= 0),
        stock INTEGER NOT NULL DEFAULT 0 CHECK(stock >= 0)
    );
    CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_name TEXT NOT NULL,
        customer_email TEXT,
        status TEXT NOT NULL DEFAULT 'pending',
        total REAL NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS order_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
        product_id INTEGER NOT NULL REFERENCES products(id),
        quantity INTEGER NOT NULL CHECK(quantity > 0),
        unit_price REAL NOT NULL
    );
    """)
    # Delivery columns. Added with ALTER TABLE so an existing orders.db keeps all its data.
    have = {r[1] for r in con.execute("PRAGMA table_info(orders)")}
    for col, kind in (("address", "TEXT"), ("lat", "REAL"), ("lng", "REAL")):
        if col not in have:
            con.execute(f"ALTER TABLE orders ADD COLUMN {col} {kind}")
    con.commit()
    con.close()


def err(msg, code=400):
    return jsonify(error=msg), code


@app.get("/")
def home():
    return render_template("lab.html")


@app.get("/health")
def health():
    return {"status": "ok"}


# ---------- Products ----------
@app.get("/products")
def list_products():
    col = PRODUCT_SORT.get(request.args.get("sort_by", "id"))
    if not col:
        return err(f"sort_by must be one of {list(PRODUCT_SORT)}")
    direction = "DESC" if request.args.get("order", "asc").lower() == "desc" else "ASC"
    q = "SELECT * FROM products"
    params = []
    if request.args.get("search"):
        q += " WHERE name LIKE ?"
        params.append(f"%{request.args['search']}%")
    rows = db().execute(f"{q} ORDER BY {col} {direction}", params).fetchall()
    return jsonify([dict(r) for r in rows])


@app.post("/products")
def create_product():
    b = request.get_json(force=True)
    if not b.get("name") or b.get("price") is None:
        return err("name and price are required")
    cur = db().execute("INSERT INTO products(name, price, stock) VALUES (?,?,?)",
                       (b["name"], float(b["price"]), int(b.get("stock", 0))))
    db().commit()
    return jsonify(id=cur.lastrowid), 201


@app.patch("/products/<int:pid>")
def update_product(pid):
    b = request.get_json(force=True)
    fields = {k: b[k] for k in ("name", "price", "stock") if k in b}
    if not fields:
        return err("nothing to update")
    sets = ", ".join(f"{k}=?" for k in fields)
    cur = db().execute(f"UPDATE products SET {sets} WHERE id=?", (*fields.values(), pid))
    db().commit()
    return ("", 204) if cur.rowcount else err("product not found", 404)


# ---------- Orders ----------
@app.post("/orders")
def create_order():
    b = request.get_json(force=True)
    items = b.get("items") or []
    if not b.get("customer_name") or not items:
        return err("customer_name and at least one item are required")
    try:
        address, lat, lng = routing.parse_location(b.get("address"), b.get("lat"), b.get("lng"))
    except ValueError as e:
        return err(str(e))
    con = db()
    try:
        con.execute("BEGIN IMMEDIATE")
        total, lines = 0.0, []
        for it in items:
            p = con.execute("SELECT * FROM products WHERE id=?", (it["product_id"],)).fetchone()
            qty = int(it["quantity"])
            if not p:
                raise ValueError(f"product {it['product_id']} not found")
            if qty <= 0 or p["stock"] < qty:
                raise ValueError(f"insufficient stock for '{p['name']}' (available {p['stock']})")
            total += p["price"] * qty
            lines.append((p["id"], qty, p["price"]))
        cur = con.execute(
            "INSERT INTO orders(customer_name, customer_email, total, created_at, address, lat, lng) "
            "VALUES (?,?,?,?,?,?,?)",
            (b["customer_name"], b.get("customer_email"), round(total, 2),
             datetime.now(timezone.utc).isoformat(), address, lat, lng))
        oid = cur.lastrowid
        for pid, qty, price in lines:
            con.execute("INSERT INTO order_items(order_id, product_id, quantity, unit_price) VALUES (?,?,?,?)",
                        (oid, pid, qty, price))
            con.execute("UPDATE products SET stock = stock - ? WHERE id=?", (qty, pid))
        con.commit()
    except (ValueError, KeyError, TypeError) as e:
        con.rollback()
        return err(str(e))
    return jsonify(id=oid, total=round(total, 2), status="pending"), 201


@app.get("/orders")
def list_orders():
    col = ORDER_SORT.get(request.args.get("sort_by", "created_at"))
    if not col:
        return err(f"sort_by must be one of {list(ORDER_SORT)}")
    direction = "ASC" if request.args.get("order", "desc").lower() == "asc" else "DESC"
    where, params = [], []
    if request.args.get("status"):
        where.append("o.status = ?"); params.append(request.args["status"])
    if request.args.get("customer"):
        where.append("o.customer_name LIKE ?"); params.append(f"%{request.args['customer']}%")
    if request.args.get("min_total"):
        where.append("o.total >= ?"); params.append(float(request.args["min_total"]))
    page = max(1, int(request.args.get("page", 1)))
    size = min(100, max(1, int(request.args.get("page_size", 20))))
    sql = "SELECT o.* FROM orders o"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += f" ORDER BY {col} {direction}, o.id DESC LIMIT ? OFFSET ?"
    rows = db().execute(sql, (*params, size, (page - 1) * size)).fetchall()
    return jsonify([dict(r) for r in rows])


@app.get("/orders/<int:oid>")
def get_order(oid):
    o = db().execute("SELECT * FROM orders WHERE id=?", (oid,)).fetchone()
    if not o:
        return err("order not found", 404)
    items = db().execute("""SELECT oi.product_id, p.name, oi.quantity, oi.unit_price
                            FROM order_items oi JOIN products p ON p.id = oi.product_id
                            WHERE oi.order_id=?""", (oid,)).fetchall()
    return jsonify({**dict(o), "items": [dict(i) for i in items]})


@app.patch("/orders/<int:oid>/status")
def update_status(oid):
    status = (request.get_json(force=True) or {}).get("status")
    if status not in ORDER_STATUSES:
        return err(f"status must be one of {list(ORDER_STATUSES)}")
    con = db()
    o = con.execute("SELECT status FROM orders WHERE id=?", (oid,)).fetchone()
    if not o:
        return err("order not found", 404)
    if o["status"] == "cancelled":
        return err("cancelled orders cannot change status", 409)
    if status == "cancelled":   # restock
        for it in con.execute("SELECT product_id, quantity FROM order_items WHERE order_id=?", (oid,)):
            con.execute("UPDATE products SET stock = stock + ? WHERE id=?", (it["quantity"], it["product_id"]))
    con.execute("UPDATE orders SET status=? WHERE id=?", (status, oid))
    con.commit()
    return jsonify(id=oid, status=status)


@app.patch("/orders/<int:oid>/location")
def update_location(oid):
    """Set or fix the delivery address and coordinates of an existing order."""
    b = request.get_json(force=True) or {}
    try:
        address, lat, lng = routing.parse_location(b.get("address"), b.get("lat"), b.get("lng"))
    except ValueError as e:
        return err(str(e))
    cur = db().execute("UPDATE orders SET address=?, lat=?, lng=? WHERE id=?", (address, lat, lng, oid))
    db().commit()
    if not cur.rowcount:
        return err("order not found", 404)
    return jsonify(id=oid, address=address, lat=lat, lng=lng)


from lab import lab_bp  # noqa: E402  (analysis endpoints)
from route_api import route_bp  # noqa: E402  (delivery route endpoints)
app.register_blueprint(lab_bp)
app.register_blueprint(route_bp)

init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5001)))
