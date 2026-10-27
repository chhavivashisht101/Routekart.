"""Delivery route planning for Design and Analysis of Algorithms.

Problem: a van leaves the warehouse (the depot), visits every delivery stop exactly once and
comes back. That is the Travelling Salesman Problem (TSP), which is NP-hard, so the algorithms
below trade route quality against running time:

    as_placed    baseline, deliver in the order the orders were placed (no optimisation)
    nearest      greedy, always drive to the closest unvisited stop             O(n^2)
    two_opt      nearest neighbour, then remove crossing edges until none left  O(n^2) per pass
    held_karp    exact dynamic programming over subsets                         O(n^2 * 2^n)
    brute_force  exact, tries every ordering                                    O(n!)

Distances are straight-line (haversine) multiplied by a detour factor to estimate road distance.
Every solver takes a distance matrix D where index 0 is the depot and 1..n are the stops, and
returns (order, steps): the stops in visiting order and how many candidates it examined.
"""
import itertools
import math
import os
import random
import time

EARTH_KM = 6371.0088
DETOUR = 1.3          # roads are longer than straight lines; 1.3 is a common city estimate
SPEED_KMPH = 30.0     # average city delivery speed
SERVICE_MIN = 5.0     # minutes spent at each stop handing over the parcel

DEFAULT_DEPOT = {
    "name": os.environ.get("DEPOT_NAME", "Main warehouse"),
    "lat": float(os.environ.get("DEPOT_LAT", 28.6315)),
    "lng": float(os.environ.get("DEPOT_LNG", 77.2167)),
}

AREAS = ["Model Town", "Civil Lines", "Green Park", "Rajouri Garden", "Lajpat Nagar", "Karol Bagh",
         "Vasant Vihar", "Pitampura", "Saket", "Dwarka", "Rohini", "Janakpuri", "Mayur Vihar", "Hauz Khas"]
STREETS = ["Main Road", "Gandhi Marg", "Nehru Street", "Market Road", "Park Lane", "Temple Road", "Station Road"]


# ---------- input helpers ----------
def parse_location(address, lat, lng):
    """Validate an optional delivery location. Returns (address, lat, lng); lat and lng are both
    None or both valid numbers. Raises ValueError with a readable message otherwise."""
    address = (str(address).strip() if address is not None else "") or None
    if address and len(address) > 300:
        raise ValueError("address is too long (300 characters at most)")
    blank = lambda v: v is None or (isinstance(v, str) and not v.strip())
    if blank(lat) and blank(lng):
        return address, None, None
    if blank(lat) or blank(lng):
        raise ValueError("give both lat and lng, or neither")
    try:
        lat, lng = float(lat), float(lng)
    except (TypeError, ValueError):
        raise ValueError("lat and lng must be numbers")
    if not (math.isfinite(lat) and math.isfinite(lng)) or not (-90 <= lat <= 90) or not (-180 <= lng <= 180):
        raise ValueError("lat must be between -90 and 90 and lng between -180 and 180")
    return address, round(lat, 6), round(lng, 6)


def random_point_near(rnd, lat, lng, radius_km):
    """Uniformly random point inside a circle of radius_km around (lat, lng)."""
    r = radius_km * math.sqrt(rnd.random())
    theta = rnd.random() * 2 * math.pi
    dlat = (r * math.cos(theta)) / 111.32
    dlng = (r * math.sin(theta)) / (111.32 * max(0.05, math.cos(math.radians(lat))))
    return round(lat + dlat, 6), round(lng + dlng, 6)


def random_address(rnd):
    return f"{rnd.randint(1, 450)}, {rnd.choice(STREETS)}, {rnd.choice(AREAS)}"


# ---------- distances ----------
def haversine(a, b):
    """Great-circle distance in km between two (lat, lng) points."""
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * EARTH_KM * math.asin(min(1.0, math.sqrt(h)))


def build_matrix(points, detour=DETOUR):
    n = len(points)
    D = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            D[i][j] = D[j][i] = haversine(points[i], points[j]) * detour
    return D


def tour_length(D, order):
    """Length of depot -> order -> depot."""
    if not order:
        return 0.0
    total = D[0][order[0]] + D[order[-1]][0]
    for k in range(len(order) - 1):
        total += D[order[k]][order[k + 1]]
    return total


# ---------- solvers ----------
def as_placed(D):
    return list(range(1, len(D))), 0


def nearest_neighbour(D):
    left = list(range(1, len(D)))
    cur, order, steps = 0, [], 0
    while left:
        best, best_d = left[0], math.inf
        for j in left:
            steps += 1
            if D[cur][j] < best_d:
                best, best_d = j, D[cur][j]
        order.append(best)
        left.remove(best)
        cur = best
    return order, steps


def two_opt(D, max_passes=200):
    """Start from nearest neighbour, then reverse any segment that shortens the tour."""
    order, steps = nearest_neighbour(D)
    n = len(order)
    tour = [0] + order + [0]
    improved, passes = True, 0
    while improved and passes < max_passes:
        improved = False
        passes += 1
        for i in range(1, n):
            for j in range(i + 1, n + 1):
                a, b, c, d = tour[i - 1], tour[i], tour[j], tour[j + 1]
                steps += 1
                if D[a][c] + D[b][d] < D[a][b] + D[c][d] - 1e-9:
                    tour[i:j + 1] = reversed(tour[i:j + 1])
                    improved = True
    return tour[1:-1], steps


def held_karp(D):
    """Exact dynamic programming. dp[mask][j] is the shortest path that starts at the depot,
    visits exactly the stops in mask and ends at stop j."""
    n = len(D) - 1
    size = 1 << n
    dp = [[math.inf] * n for _ in range(size)]
    parent = [[-1] * n for _ in range(size)]
    for j in range(n):
        dp[1 << j][j] = D[0][j + 1]
    steps = 0
    for mask in range(1, size):
        row = dp[mask]
        for j in range(n):
            cur = row[j]
            if not (mask >> j) & 1 or cur == math.inf:
                continue
            for k in range(n):
                if (mask >> k) & 1:
                    continue
                steps += 1
                nm = mask | (1 << k)
                val = cur + D[j + 1][k + 1]
                if val < dp[nm][k]:
                    dp[nm][k] = val
                    parent[nm][k] = j
    full = size - 1
    last = min(range(n), key=lambda j: dp[full][j] + D[j + 1][0])
    order, mask, j = [], full, last
    while j != -1:
        order.append(j + 1)
        pj = parent[mask][j]
        mask ^= 1 << j
        j = pj
    order.reverse()
    return order, steps


def brute_force(D):
    n = len(D) - 1
    best, best_len, steps = None, math.inf, 0
    for perm in itertools.permutations(range(1, n + 1)):
        steps += 1
        length = D[0][perm[0]] + D[perm[-1]][0] + sum(D[perm[k]][perm[k + 1]] for k in range(n - 1))
        if length < best_len - 1e-12:
            best, best_len = perm, length
    return list(best), steps


ALGORITHMS = {
    "two_opt": {"label": "Nearest neighbour + 2-opt", "paradigm": "Greedy start, local search", "time": "O(n²) per pass",
                "space": "O(n)", "exact": False, "max_stops": None, "fn": two_opt},
    "nearest": {"label": "Nearest neighbour", "paradigm": "Greedy", "time": "O(n²)",
                "space": "O(n)", "exact": False, "max_stops": None, "fn": nearest_neighbour},
    "held_karp": {"label": "Held-Karp (exact)", "paradigm": "Dynamic programming", "time": "O(n² · 2ⁿ)",
                  "space": "O(n · 2ⁿ)", "exact": True, "max_stops": 12, "fn": held_karp},
    "brute_force": {"label": "Brute force (exact)", "paradigm": "Exhaustive search", "time": "O(n!)",
                    "space": "O(n)", "exact": True, "max_stops": 8, "fn": brute_force},
    "as_placed": {"label": "As placed (no optimisation)", "paradigm": "Baseline", "time": "O(n)",
                  "space": "O(1)", "exact": False, "max_stops": None, "fn": as_placed},
}


def info():
    return [{"key": k, **{f: v[f] for f in ("label", "paradigm", "time", "space", "exact", "max_stops")}}
            for k, v in ALGORITHMS.items()]


def too_many(key, n):
    cap = ALGORITHMS[key]["max_stops"]
    if cap and n > cap:
        return f"{ALGORITHMS[key]['label']} needs {cap} or fewer stops (you have {n}). Use 2-opt or nearest neighbour for more."
    return None


def solve(D, key):
    """Run one algorithm on matrix D. Returns (order, steps, time_ms)."""
    if len(D) <= 1:
        return [], 0, 0.0
    t0 = time.perf_counter()
    order, steps = ALGORITHMS[key]["fn"](D)
    return order, steps, (time.perf_counter() - t0) * 1000


# ---------- planning ----------
def _matrix_for(depot, orders, detour):
    return build_matrix([(depot["lat"], depot["lng"])] + [(o["lat"], o["lng"]) for o in orders], detour)


def plan(depot, orders, algorithm, detour=DETOUR, speed_kmph=SPEED_KMPH, service_min=SERVICE_MIN):
    """Plan one route. `orders` are dicts with id, customer_name, address, lat, lng, total."""
    msg = too_many(algorithm, len(orders))
    if msg:
        raise ValueError(msg)
    D = _matrix_for(depot, orders, detour)
    order, steps, ms = solve(D, algorithm)
    stops, prev, cum = [], 0, 0.0
    for seq, idx in enumerate(order, 1):
        leg = D[prev][idx]
        cum += leg
        o = orders[idx - 1]
        stops.append({"seq": seq, "order_id": o["id"], "customer_name": o["customer_name"], "address": o.get("address"),
                      "lat": o["lat"], "lng": o["lng"], "total": o.get("total"), "leg_km": round(leg, 2),
                      "cum_km": round(cum, 2),
                      "eta_min": round(cum / speed_kmph * 60 + service_min * (seq - 1))})
        prev = idx
    return_km = D[prev][0] if order else 0.0
    total_km = cum + return_km
    travel_min = total_km / speed_kmph * 60
    return {"algorithm": algorithm, "label": ALGORITHMS[algorithm]["label"], "depot": depot, "n_stops": len(order),
            "stops": stops, "return_km": round(return_km, 2), "total_km": round(total_km, 2),
            "travel_min": round(travel_min), "service_min": round(service_min * len(order)),
            "total_min": round(travel_min + service_min * len(order)),
            "stats": {"steps": steps, "time_ms": round(ms, 4)}}


def compare(depot, orders, detour=DETOUR):
    """Run every algorithm on the same stops so their results can be compared."""
    D = _matrix_for(depot, orders, detour)
    rows, base = [], None
    for key, a in ALGORITHMS.items():
        msg = too_many(key, len(orders))
        row = {"algorithm": key, "label": a["label"], "paradigm": a["paradigm"], "time": a["time"], "exact": a["exact"]}
        if msg:
            row["skipped"] = f"needs {a['max_stops']} or fewer stops"
        else:
            order, steps, ms = solve(D, key)
            row.update(total_km=round(tour_length(D, order), 2), steps=steps, time_ms=round(ms, 4),
                       sequence=[orders[i - 1]["id"] for i in order])
            if key == "as_placed":
                base = row["total_km"]
        rows.append(row)
    for row in rows:
        if "total_km" in row and base:
            row["saving_pct"] = round((1 - row["total_km"] / base) * 100, 1)
    done = [r for r in rows if "total_km" in r]
    best = min(done, key=lambda r: r["total_km"])["algorithm"] if done else None
    return {"n_stops": len(orders), "baseline_km": base, "best": best, "rows": rows}
