import random
import unittest

import sorting


class SortingTests(unittest.TestCase):
    def check(self, data):
        for name in sorting.ALGORITHMS:
            out, stats = sorting.run(name, data)
            self.assertEqual(out, sorted(data), f"{name} failed on {data[:8]}...")
            self.assertIn("time_ms", stats)

    def test_edge_cases(self):
        for data in ([], [1], [2, 1], [1, 2], [3, 3, 3, 3], [5, 1, 5, 1, 5]):
            self.check(data)

    def test_random_sorted_reversed(self):
        rnd = random.Random(1)
        for n in (2, 3, 10, 57, 500):
            base = [rnd.randrange(0, 50) for _ in range(n)]      # lots of duplicates
            self.check(base)
            self.check(sorted(base))
            self.check(sorted(base, reverse=True))

    def test_tuples_like_orders(self):
        rnd = random.Random(2)
        data = [(round(rnd.uniform(1, 999), 2), i) for i in range(300)]
        self.check(data)

    def test_counts_match_theory(self):
        n = 200
        rev = list(range(n, 0, -1))
        _, s = sorting.run("selection", rev)
        self.assertEqual(s["comparisons"], n * (n - 1) // 2)       # always n(n-1)/2
        _, s = sorting.run("bubble", list(range(n)))
        self.assertEqual(s["comparisons"], n - 1)                  # best case O(n)
        _, s = sorting.run("insertion", rev)
        self.assertEqual(s["moves"], n * (n - 1) // 2)             # worst case shifts

    def test_trace_ends_sorted(self):
        data = [5, 2, 9, 1, 7, 3, 8, 4, 6]
        for name in ("bubble", "selection", "insertion", "shell", "merge", "quick", "heap"):
            trace = []
            sorting.run(name, data, trace=trace)
            if trace:
                self.assertEqual(list(trace[-1]), sorted(data), name)


if __name__ == "__main__":
    unittest.main()
