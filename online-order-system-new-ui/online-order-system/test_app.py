import os
import tempfile
import unittest

os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "test.db")
import app as order_app  # noqa: E402


class OrderSystemTests(unittest.TestCase):
    def setUp(self):
        order_app.init_db()
        self.client = order_app.app.test_client()

    def test_order_flow_and_sorting(self):
        c = self.client
        a = c.post("/products", json={"name": "Pen", "price": 10, "stock": 100}).get_json()["id"]
        b = c.post("/products", json={"name": "Book", "price": 250, "stock": 5}).get_json()["id"]
        c.post("/orders", json={"customer_name": "Asha", "items": [{"product_id": a, "quantity": 3}]})
        c.post("/orders", json={"customer_name": "Ravi", "items": [{"product_id": b, "quantity": 2}]})
        c.post("/orders", json={"customer_name": "Meera", "items": [{"product_id": a, "quantity": 10}]})

        totals = [o["total"] for o in c.get("/orders?sort_by=total&order=desc").get_json()]
        self.assertEqual(totals, sorted(totals, reverse=True))
        names = [o["customer_name"] for o in c.get("/orders?sort_by=customer&order=asc").get_json()]
        self.assertEqual(names, sorted(names))

        self.assertEqual(c.get("/products?sort_by=price&order=desc").get_json()[0]["name"], "Book")
        r = c.post("/orders", json={"customer_name": "X", "items": [{"product_id": b, "quantity": 99}]})
        self.assertEqual(r.status_code, 400)

        oid = c.get("/orders?customer=Ravi").get_json()[0]["id"]
        c.patch(f"/orders/{oid}/status", json={"status": "cancelled"})
        stock = {p["name"]: p["stock"] for p in c.get("/products").get_json()}
        self.assertEqual(stock["Book"], 5)   # cancelling restocks

    def test_bad_sort_rejected(self):
        self.assertEqual(self.client.get("/orders?sort_by=id;DROP TABLE orders").status_code, 400)


if __name__ == "__main__":
    unittest.main()
