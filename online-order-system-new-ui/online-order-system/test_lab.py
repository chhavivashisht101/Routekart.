import os
import tempfile
import unittest

os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "lab_test.db")
import app as order_app  # noqa: E402


class LabApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        order_app.init_db()
        cls.c = order_app.app.test_client()
        cls.c.post("/api/reset")
        assert cls.c.post("/api/seed", json={"count": 400}).get_json()["added"] == 400

    def test_every_algorithm_matches_database_sort(self):
        expected = [o["id"] for o in self.c.get("/api/sort-orders?algorithm=sql&sort_by=total&order=asc&page_size=100")
                    .get_json()["rows"]]
        totals = [o["total"] for o in self.c.get("/api/sort-orders?algorithm=sql&sort_by=total&order=asc&page_size=100")
                  .get_json()["rows"]]
        for algo in ("merge", "quick", "heap", "shell", "insertion", "selection", "bubble", "timsort"):
            rows = self.c.get(f"/api/sort-orders?algorithm={algo}&sort_by=total&order=asc&page_size=100").get_json()["rows"]
            self.assertEqual([o["total"] for o in rows], totals, algo)

    def test_descending_and_text_sort(self):
        rows = self.c.get("/api/sort-orders?algorithm=quick&sort_by=customer&order=desc&page_size=100").get_json()["rows"]
        names = [o["customer_name"].lower() for o in rows]
        self.assertEqual(names, sorted(names, reverse=True))

    def test_stats_and_pagination(self):
        d = self.c.get("/api/sort-orders?algorithm=merge&sort_by=id&page=2&page_size=100").get_json()
        self.assertEqual(d["total"], 400)
        self.assertEqual(d["pages"], 4)
        self.assertGreater(d["stats"]["comparisons"], 0)

    def test_quadratic_guard_and_bad_input(self):
        self.assertEqual(self.c.get("/api/sort-orders?algorithm=nope").status_code, 400)
        self.assertEqual(self.c.get("/api/sort-orders?sort_by=x;DROP").status_code, 400)

    def test_benchmark_and_visualize(self):
        r = self.c.post("/api/benchmark", json={"sizes": [50, 100, 4000], "algorithms": ["merge", "bubble"],
                                                "case": "reversed"}).get_json()
        by = {s["algorithm"]: s for s in r["series"]}
        self.assertEqual(len(by["merge"]["points"]), 3)
        self.assertEqual(len(by["bubble"]["points"]), 2)               # 4000 skipped for O(n^2)
        self.assertEqual(r["skipped"], [{"algorithm": "bubble", "n": 4000}])
        v = self.c.post("/api/visualize", json={"algorithm": "heap", "n": 20}).get_json()
        self.assertEqual(v["frames"][-1], sorted(v["frames"][0]))

    def test_analytics(self):
        a = self.c.get("/api/analytics").get_json()
        self.assertEqual(a["kpis"]["orders"], 400)
        self.assertEqual(len(a["daily"]), 30)
        self.assertEqual(sum(h["count"] for h in a["histogram"]),
                         400 - a["kpis"]["cancelled"])


if __name__ == "__main__":
    unittest.main()
