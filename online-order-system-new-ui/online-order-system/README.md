# OrderLab: online order management with delivery route planning and sorting analysis (DAA project)

Flask + SQLite backend, a browser dashboard, a delivery route planner, and eight sorting algorithms written from scratch.
Every sorting algorithm counts its comparisons and moves, and every route algorithm counts its steps, so you can compare the measured numbers with the theory.

## Run
    pip install -r requirements.txt
    python app.py                 # open http://localhost:5001
    python -m unittest -q         # 26 tests

Charts use Chart.js from a CDN, so the first load needs internet.

## Pages
| Page | What it shows |
|---|---|
| Overview | KPIs, orders per day, orders by status, order value distribution, top products, top customers. "Add sample orders" loads up to 50,000 orders. |
| Orders | Sort live orders with any algorithm (or the database ORDER BY as a baseline). Shows comparisons, moves and time for that run. Filter, search, paginate, change status. |
| Catalog and new order | Products CRUD, cart, stock check, cancel returns stock. A new order can carry a delivery address with latitude and longitude. |
| Delivery route | Picks the orders to deliver, finds the shortest round trip from the warehouse with the algorithm you choose, draws it on a map, and lists every stop with leg distance and arrival time. Compares all route algorithms on the same stops. "Dispatch this route" marks its orders as shipped. |
| Sorting lab | Benchmark chart (time, comparisons or moves against n), measured growth exponent per algorithm, step-by-step visualiser, complexity table. |

## Algorithms (`sorting.py`)
| Algorithm | Technique | Best | Average | Worst | Space | Stable |
|---|---|---|---|---|---|---|
| Bubble | Brute force | O(n) | O(n²) | O(n²) | O(1) | Yes |
| Selection | Brute force | O(n²) | O(n²) | O(n²) | O(1) | No |
| Insertion | Decrease and conquer | O(n) | O(n²) | O(n²) | O(1) | Yes |
| Shell (Knuth gaps) | Diminishing increment | O(n log n) | about O(n^1.3) | O(n^1.5) | O(1) | No |
| Merge (bottom-up) | Divide and conquer | O(n log n) | O(n log n) | O(n log n) | O(n) | Yes |
| Quick (Hoare, median of three) | Divide and conquer | O(n log n) | O(n log n) | O(n²) | O(log n) | No |
| Heap | Transform and conquer | O(n log n) | O(n log n) | O(n log n) | O(1) | No |
| Timsort | Python built-in, used as a reference line | | | | | |

## Delivery routes (`routing.py`)
A van leaves the warehouse, visits every stop once and returns. This is the travelling salesman problem (NP-hard), so the algorithms trade route quality against running time.

| Algorithm | Technique | Time | Space | Exact |
|---|---|---|---|---|
| As placed | Baseline, no optimisation | O(n) | O(1) | No |
| Nearest neighbour | Greedy | O(n²) | O(n) | No |
| Nearest neighbour + 2-opt | Greedy start, then local search | O(n²) per pass | O(n) | No |
| Held-Karp | Dynamic programming over subsets | O(n² · 2ⁿ) | O(n · 2ⁿ) | Yes, up to 12 stops |
| Brute force | Exhaustive search | O(n!) | O(n) | Yes, up to 8 stops |

- Distance between two points is the haversine (great-circle) distance times 1.3 to allow for roads. Drive time uses 30 km/h and 5 minutes at each stop. These are constants at the top of `routing.py`.
- The warehouse location comes from the environment: `DEPOT_NAME`, `DEPOT_LAT`, `DEPOT_LNG` (default is central Delhi). It can also be changed on the page.
- Orders without a latitude and longitude are skipped when planning. "Fill demo locations" gives random points near the warehouse to any order that has none, which is handy for a demo.
- The comparison table shows how close the 2-opt heuristic gets to the exact answer, and how the step counts diverge as stops grow.
- An existing `orders.db` is upgraded automatically: the app adds the `address`, `lat` and `lng` columns on start and keeps all data.

## How the analysis works
- The benchmark gives every algorithm the same data at each size, takes the best of several runs for small sizes, and checks each result is sorted.
- Input orders: random, already sorted, reverse sorted, nearly sorted. Try them to see best and worst cases (bubble and insertion drop to O(n) on sorted input).
- Measured exponent = slope of the least-squares line through log(n) and log(measure). Quadratic algorithms land near 2, n log n algorithms a little above 1.
- Quadratic algorithms are skipped above 3,000 items in the benchmark and above 5,000 live orders.

## API
| Method | Path | Notes |
|---|---|---|
| GET | /api/sort-orders | `algorithm=merge\|quick\|heap\|shell\|insertion\|selection\|bubble\|timsort\|sql`, `sort_by=created_at\|total\|customer\|status\|id`, `order`, `status`, `customer`, `page`, `page_size` |
| POST | /api/benchmark | `{sizes:[...], algorithms:[...], case:"random\|sorted\|reversed\|nearly"}` |
| POST | /api/visualize | `{algorithm, n, case}` returns every step |
| GET | /api/algorithms | complexity table data |
| GET | /api/analytics | dashboard data |
| GET | /api/route/config | warehouse, algorithm list and constants |
| GET | /api/route/plan | `algorithm=two_opt\|nearest\|held_karp\|brute_force\|as_placed`, `status=pending,confirmed`, `limit`, `depot_lat`, `depot_lng`, `speed`, `service_min`, `detour`. Returns the stops in order with leg km, running km and arrival minutes |
| GET | /api/route/compare | same filters, runs every algorithm on the same stops |
| POST | /api/route/dispatch | `{order_ids:[...]}` marks pending or confirmed orders as shipped |
| POST | /api/route/demo-locations | gives orders without a location a random point near the warehouse |
| POST | /api/seed, /api/reset | add sample orders, delete all orders |
| GET, POST, PATCH | /products, /orders, /orders/<id>/status | core order system. `POST /orders` also accepts `address`, `lat`, `lng` |
| PATCH | /orders/<id>/location | set or fix `address`, `lat`, `lng` of an order |

## Deploy
- Render: push to GitHub, New > Blueprint (reads `render.yaml`, includes a disk for the SQLite file).
- Docker: `docker build -t orderlab . && docker run -p 8000:8000 -v orders:/data orderlab`
- Heroku or Railway use the `Procfile`; their disks are temporary, so use Postgres there.

## Files
`app.py` core API, `routing.py` route algorithms, `route_api.py` route API, `lab.py` analysis API, `sorting.py` sorting algorithms, `templates/lab.html` UI, `test_*.py` tests.
