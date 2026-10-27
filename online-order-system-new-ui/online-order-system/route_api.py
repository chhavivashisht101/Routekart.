"""Delivery route endpoints: pick the orders to deliver, find the shortest tour, compare algorithms,
dispatch the route (marks its orders as shipped) and fill demo locations."""
import random
import sqlite3

from flask import Blueprint, current_app, jsonify, request

import routing

route_bp = Blueprint("route", __name__)

STATUSES = ("pending", "confirmed", "shipped", "delivered", "cancelled")
DISPATCHABLE = ("pending", "confirmed")
MAX_STOPS = 150


def conn():
    c = sqlite3.connect(current_app.config["DB_PATH"])
    c.row_factory = sqlite3.Row
    return c


def bad(msg, code=400):
    return jsonify(error=msg), code


def _number(args, key, default, lo, hi):
    raw = args.get(key)
    if raw in (None, ""):
        return default
    try:
        v = float(raw)
    except ValueError:
        raise ValueError(f"{key} must be a number")
    if not lo <= v <= hi:
        raise ValueError(f"{key} must be between {lo} and {hi}")
    return v


def read_params(args):
    """Depot, statuses, stop limit and travel settings from a query string. Raises ValueError."""
    d = routing.DEFAULT_DEPOT
    lat, lng = _number(args, "depot_lat", d["lat"], -90, 90), _number(args, "depot_lng", d["lng"], -180, 180)
    statuses = [s.strip() for s in (args.get("status") or "confirmed").split(",") if s.strip()]
    if not statuses or any(s not in STATUSES for s in statuses):
        raise ValueError(f"status must be one or more of {list(STATUSES)}, separated by commas")
    return {"depot": {"name": d["name"], "lat": lat, "lng": lng},
            "statuses": statuses,
            "limit": int(_number(args, "limit", 12, 1, MAX_STOPS)),
            "speed": _number(args, "speed", routing.SPEED_KMPH, 5, 120),
            "service": _number(args, "service_min", routing.SERVICE_MIN, 0, 60),
            "detour": _number(args, "detour", routing.DETOUR, 1, 3)}


def candidates(c, statuses, limit):
    """Oldest orders (in the chosen statuses) that have a location, plus counts for the UI."""
    marks = ",".join("?" * len(statuses))
    base = f"FROM orders WHERE status IN ({marks})"
    matching = c.execute(f"SELECT COUNT(*) {base}", statuses).fetchone()[0]
    missing = c.execute(f"SELECT COUNT(*) {base} AND (lat IS NULL OR lng IS NULL)", statuses).fetchone()[0]
    rows = [dict(r) for r in c.execute(
        f"SELECT id, customer_name, address, lat, lng, total, status, created_at {base} "
        f"AND lat IS NOT NULL AND lng IS NOT NULL ORDER BY created_at ASC, id ASC LIMIT ?", (*statuses, limit))]
    located = matching - missing
    return rows, {"matching": matching, "with_location": located, "without_location": missing,
                  "planned": len(rows), "truncated": located > len(rows)}


@route_bp.get("/api/route/config")
def config():
    return jsonify(depot=routing.DEFAULT_DEPOT, algorithms=routing.info(), max_stops=MAX_STOPS,
                   speed_kmph=routing.SPEED_KMPH, service_min=routing.SERVICE_MIN, detour=routing.DETOUR)


@route_bp.get("/api/route/plan")
def plan():
    try:
        p = read_params(request.args)
    except ValueError as e:
        return bad(str(e))
    algo = request.args.get("algorithm", "two_opt")
    if algo not in routing.ALGORITHMS:
        return bad(f"algorithm must be one of {list(routing.ALGORITHMS)}")
    c = conn()
    try:
        orders, meta = candidates(c, p["statuses"], p["limit"])
    finally:
        c.close()
    try:
        result = routing.plan(p["depot"], orders, algo, p["detour"], p["speed"], p["service"])
    except ValueError as e:
        return bad(str(e))
    return jsonify(**result, **meta)


@route_bp.get("/api/route/compare")
def compare():
    try:
        p = read_params(request.args)
    except ValueError as e:
        return bad(str(e))
    c = conn()
    try:
        orders, meta = candidates(c, p["statuses"], p["limit"])
    finally:
        c.close()
    return jsonify(**routing.compare(p["depot"], orders, p["detour"]), **meta)


@route_bp.post("/api/route/dispatch")
def dispatch():
    """Mark the orders of a planned route as shipped. Only pending or confirmed orders move."""
    ids = (request.get_json(silent=True) or {}).get("order_ids")
    if not isinstance(ids, list) or not ids or len(ids) > 500 or not all(isinstance(i, int) for i in ids):
        return bad("order_ids must be a list of 1 to 500 order numbers")
    c = conn()
    try:
        marks = ",".join("?" * len(ids))
        cur = c.execute(f"UPDATE orders SET status='shipped' WHERE id IN ({marks}) "
                        f"AND status IN ({','.join('?' * len(DISPATCHABLE))})", (*ids, *DISPATCHABLE))
        c.commit()
        shipped = cur.rowcount
    finally:
        c.close()
    return jsonify(shipped=shipped, skipped=len(ids) - shipped)


@route_bp.post("/api/route/demo-locations")
def demo_locations():
    """Give every order that has no location a random delivery point around the depot (for demos)."""
    b = request.get_json(silent=True) or {}
    try:
        radius = _number({"r": b.get("radius_km")}, "r", 12, 1, 100)
        lat = _number({"a": b.get("depot_lat")}, "a", routing.DEFAULT_DEPOT["lat"], -90, 90)
        lng = _number({"a": b.get("depot_lng")}, "a", routing.DEFAULT_DEPOT["lng"], -180, 180)
    except ValueError as e:
        return bad(str(e))
    rnd = random.Random()
    c = conn()
    try:
        ids = [r[0] for r in c.execute("SELECT id FROM orders WHERE lat IS NULL OR lng IS NULL")]
        rows = []
        for oid in ids:
            la, lo = routing.random_point_near(rnd, lat, lng, radius)
            rows.append((routing.random_address(rnd), la, lo, oid))
        c.executemany("UPDATE orders SET address=COALESCE(address, ?), lat=?, lng=? WHERE id=?", rows)
        c.commit()
    finally:
        c.close()
    return jsonify(updated=len(ids))
