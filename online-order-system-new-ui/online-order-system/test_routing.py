import os
import random
import tempfile
import unittest

os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "route_test.db")
import app as order_app  # noqa: E402
import routing  # noqa: E402

DEPOT = {"name": "Test depot", "lat": 28.6315, "lng": 77.2167}


def random_matrix(n, seed):
    rnd = random.Random(seed)
    pts = [(DEPOT["lat"], DEPOT["lng"])] + [routing.random_point_near(rnd, DEPOT["lat"], DEPOT["lng"], 10) for _ in range(n)]
    return routing.build_matrix(pts)


class RoutingAlgorithmTests(unittest.TestCase):
    def test_haversine_known_distance(self):
        # Delhi to Jaipur is about 235 km in a straight line
        d = routing.haversine((28.6139, 77.2090), (26.9124, 75.7873))
        self.assertAlmostEqual(d, 235, delta=8)
        self.assertEqual(routing.haversine((10, 10), (10, 10)), 0)

    def test_every_solver_visits_each_stop_once(self):
        D = random_matrix(7, 1)
        for key, a in routing.ALGORITHMS.items():
            order, _ = a["fn"](D)
            self.assertEqual(sorted(order), list(range(1, 8)), key)

    def test_exact_solvers_agree_and_are_never_beaten(self):
        for seed in range(6):
            D = random_matrix(7, seed)
            hk = routing.tour_length(D, routing.held_karp(D)[0])
            bf = routing.tour_length(D, routing.brute_force(D)[0])
            self.assertAlmostEqual(hk, bf, places=9)
            for key in ("nearest", "two_opt", "as_placed"):
                self.assertGreaterEqual(routing.tour_length(D, routing.ALGORITHMS[key]["fn"](D)[0]), hk - 1e-9, key)

    def test_two_opt_never_worse_than_nearest_neighbour(self):
        for seed in range(10):
            D = random_matrix(25, seed)
            self.assertLessEqual(routing.tour_length(D, routing.two_opt(D)[0]),
                                 routing.tour_length(D, routing.nearest_neighbour(D)[0]) + 1e-9)

    def test_step_counts_follow_theory(self):
        D = random_matrix(8, 2)
        self.assertEqual(routing.brute_force(D)[1], 40320)           # 8!
        self.assertEqual(routing.nearest_neighbour(D)[1], 8 * 9 // 2)  # n + (n-1) + ... + 1
        self.assertEqual(routing.as_placed(D)[1], 0)

    def test_tiny_inputs(self):
        for n in (0, 1, 2):
            D = random_matrix(n, 0)
            for key in routing.ALGORITHMS:
                order, _, _ = routing.solve(D, key)
                self.assertEqual(sorted(order), list(range(1, n + 1)), (key, n))

    def test_plan_totals_are_consistent(self):
        rnd = random.Random(5)
        orders = [{"id": i, "customer_name": f"C{i}", "address": None, "total": 100,
                   **dict(zip(("lat", "lng"), routing.random_point_near(rnd, DEPOT["lat"], DEPOT["lng"], 8)))} for i in range(1, 9)]
        p = routing.plan(DEPOT, orders, "two_opt")
        self.assertEqual(p["n_stops"], 8)
        self.assertAlmostEqual(p["stops"][-1]["cum_km"] + p["return_km"], p["total_km"], delta=0.05)
        etas = [s["eta_min"] for s in p["stops"]]
        self.assertEqual(etas, sorted(etas))
        with self.assertRaises(ValueError):
            routing.plan(DEPOT, orders * 2, "brute_force")      # 16 stops is too many for brute force

    def test_parse_location(self):
        self.assertEqual(routing.parse_location("  12 MG Road ", "28.6", "77.2"), ("12 MG Road", 28.6, 77.2))
        self.assertEqual(routing.parse_location(None, None, ""), (None, None, None))
        for bad in (("x", 95, 10), ("x", 10, 200), ("x", "abc", 10), ("x", 10, None), ("x", float("nan"), 10)):
            with self.assertRaises(ValueError, msg=str(bad)):
                routing.parse_location(*bad)


class RouteApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        order_app.init_db()
        cls.c = order_app.app.test_client()
        cls.pid = cls.c.post("/products", json={"name": "Parcel", "price": 100, "stock": 1000}).get_json()["id"]

    def place(self, name, lat, lng, address="addr"):
        r = self.c.post("/orders", json={"customer_name": name, "address": address, "lat": lat, "lng": lng,
                                         "items": [{"product_id": self.pid, "quantity": 1}]})
        self.assertEqual(r.status_code, 201, r.get_json())
        return r.get_json()["id"]

    def test_order_with_bad_location_is_rejected(self):
        r = self.c.post("/orders", json={"customer_name": "X", "lat": 120, "lng": 10,
                                         "items": [{"product_id": self.pid, "quantity": 1}]})
        self.assertEqual(r.status_code, 400)

    def test_plan_compare_and_dispatch(self):
        self.c.post("/api/reset")
        rnd = random.Random(9)
        ids = [self.place(f"C{i}", *routing.random_point_near(rnd, DEPOT["lat"], DEPOT["lng"], 8)) for i in range(6)]
        no_loc = self.c.post("/orders", json={"customer_name": "NoLoc", "items": [{"product_id": self.pid, "quantity": 1}]}).get_json()["id"]

        p = self.c.get("/api/route/plan?status=pending&algorithm=two_opt").get_json()
        self.assertEqual(sorted(s["order_id"] for s in p["stops"]), sorted(ids))   # unlocated order is left out
        self.assertEqual(p["without_location"], 1)
        self.assertNotIn(no_loc, [s["order_id"] for s in p["stops"]])

        cmp_ = self.c.get("/api/route/compare?status=pending").get_json()
        by = {r["algorithm"]: r for r in cmp_["rows"]}
        self.assertAlmostEqual(by["held_karp"]["total_km"], by["brute_force"]["total_km"], places=1)
        self.assertLessEqual(by["two_opt"]["total_km"], by["as_placed"]["total_km"])
        self.assertEqual(cmp_["best"] in ("held_karp", "brute_force", "two_opt"), True)

        r = self.c.post("/api/route/dispatch", json={"order_ids": ids})
        self.assertEqual(r.get_json(), {"shipped": 6, "skipped": 0})
        self.assertEqual(self.c.post("/api/route/dispatch", json={"order_ids": ids}).get_json()["shipped"], 0)  # already shipped
        self.assertEqual(self.c.get("/api/route/plan?status=pending").get_json()["n_stops"], 0)

    def test_bad_parameters(self):
        for url in ("/api/route/plan?algorithm=teleport", "/api/route/plan?status=lost", "/api/route/plan?limit=0",
                    "/api/route/plan?depot_lat=999", "/api/route/plan?speed=abc", "/api/route/compare?status=,"):
            self.assertEqual(self.c.get(url).status_code, 400, url)
        for body in ({}, {"order_ids": []}, {"order_ids": ["1"]}, {"order_ids": "1"}):
            self.assertEqual(self.c.post("/api/route/dispatch", json=body).status_code, 400, body)

    def test_demo_locations_and_location_patch(self):
        self.c.post("/api/reset")
        a = self.c.post("/orders", json={"customer_name": "A", "items": [{"product_id": self.pid, "quantity": 1}]}).get_json()["id"]
        self.assertEqual(self.c.post("/api/route/demo-locations", json={}).get_json()["updated"], 1)
        o = self.c.get(f"/orders/{a}").get_json()
        self.assertIsNotNone(o["lat"]); self.assertIsNotNone(o["address"])
        r = self.c.patch(f"/orders/{a}/location", json={"address": "Home", "lat": 12.97, "lng": 77.59})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.c.patch("/orders/99999/location", json={"lat": 1, "lng": 1}).status_code, 404)
        self.assertEqual(self.c.patch(f"/orders/{a}/location", json={"lat": 1}).status_code, 400)

    def test_too_many_stops_for_exact_algorithm_is_a_clean_error(self):
        self.c.post("/api/reset")
        rnd = random.Random(1)
        for i in range(10):
            self.place(f"C{i}", *routing.random_point_near(rnd, DEPOT["lat"], DEPOT["lng"], 5))
        r = self.c.get("/api/route/plan?status=pending&algorithm=brute_force&limit=10")
        self.assertEqual(r.status_code, 400)
        self.assertIn("8 or fewer", r.get_json()["error"])


if __name__ == "__main__":
    unittest.main()
