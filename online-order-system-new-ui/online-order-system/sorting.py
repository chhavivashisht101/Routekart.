"""Sorting algorithms written from scratch for Design and Analysis of Algorithms.

Every algorithm sorts a list in place and returns (comparisons, moves), where a move is a
swap or an element write. Pass a list as `trace` to record a snapshot after each move
(used by the step-by-step visualiser, only sensible for small inputs).
"""
import time


def bubble_sort(a, trace=None):
    comps = moves = 0
    end = len(a)
    while end > 1:
        last_swap = 0
        for i in range(1, end):
            comps += 1
            if a[i - 1] > a[i]:
                a[i - 1], a[i] = a[i], a[i - 1]
                moves += 1
                last_swap = i
                if trace is not None:
                    trace.append(tuple(a))
        end = last_swap
    return comps, moves


def selection_sort(a, trace=None):
    comps = moves = 0
    n = len(a)
    for i in range(n - 1):
        m = i
        for j in range(i + 1, n):
            comps += 1
            if a[j] < a[m]:
                m = j
        if m != i:
            a[i], a[m] = a[m], a[i]
            moves += 1
            if trace is not None:
                trace.append(tuple(a))
    return comps, moves


def insertion_sort(a, trace=None):
    comps = moves = 0
    for i in range(1, len(a)):
        key = a[i]
        j = i - 1
        while j >= 0:
            comps += 1
            if a[j] > key:
                a[j + 1] = a[j]
                moves += 1
                j -= 1
                if trace is not None:
                    trace.append(tuple(a))
            else:
                break
        a[j + 1] = key
        if trace is not None:
            trace.append(tuple(a))
    return comps, moves


def shell_sort(a, trace=None):
    comps = moves = 0
    n = len(a)
    gap = 1
    while gap < n // 3:          # Knuth sequence 1, 4, 13, 40, ...
        gap = gap * 3 + 1
    while gap >= 1:
        for i in range(gap, n):
            tmp = a[i]
            j = i
            while j >= gap:
                comps += 1
                if a[j - gap] > tmp:
                    a[j] = a[j - gap]
                    moves += 1
                    j -= gap
                    if trace is not None:
                        trace.append(tuple(a))
                else:
                    break
            a[j] = tmp
            if trace is not None:
                trace.append(tuple(a))
        gap //= 3
    return comps, moves


def merge_sort(a, trace=None):
    """Bottom-up merge sort (no recursion, so no depth limit)."""
    comps = moves = 0
    n = len(a)
    src, dst = a, [None] * n
    width = 1
    while width < n:
        for lo in range(0, n, 2 * width):
            mid = min(lo + width, n)
            hi = min(lo + 2 * width, n)
            i, j, k = lo, mid, lo
            while i < mid and j < hi:
                comps += 1
                if src[j] < src[i]:
                    dst[k] = src[j]
                    j += 1
                else:
                    dst[k] = src[i]
                    i += 1
                k += 1
                moves += 1
                if trace is not None:
                    trace.append(tuple(dst[:k]) + tuple(src[k:]))
            while i < mid:
                dst[k] = src[i]
                i += 1
                k += 1
                moves += 1
            while j < hi:
                dst[k] = src[j]
                j += 1
                k += 1
                moves += 1
            if trace is not None:
                trace.append(tuple(dst[:hi]) + tuple(src[hi:]))
        src, dst = dst, src
        width *= 2
    if src is not a:
        a[:] = src
    return comps, moves


def quick_sort(a, trace=None):
    """Hoare partition, median-of-three pivot, explicit stack (smaller side first)."""
    comps = moves = 0
    stack = [(0, len(a) - 1)]
    while stack:
        lo, hi = stack.pop()
        while lo < hi:
            mid = (lo + hi) // 2
            comps += 1
            if a[mid] < a[lo]:
                a[mid], a[lo] = a[lo], a[mid]; moves += 1
            comps += 1
            if a[hi] < a[lo]:
                a[hi], a[lo] = a[lo], a[hi]; moves += 1
            comps += 1
            if a[hi] < a[mid]:
                a[hi], a[mid] = a[mid], a[hi]; moves += 1
            if trace is not None:
                trace.append(tuple(a))
            pivot = a[mid]
            i, j = lo - 1, hi + 1
            while True:
                i += 1
                comps += 1
                while a[i] < pivot:
                    i += 1
                    comps += 1
                j -= 1
                comps += 1
                while a[j] > pivot:
                    j -= 1
                    comps += 1
                if i >= j:
                    break
                a[i], a[j] = a[j], a[i]
                moves += 1
                if trace is not None:
                    trace.append(tuple(a))
            if j - lo < hi - j - 1:
                stack.append((j + 1, hi))
                hi = j
            else:
                stack.append((lo, j))
                lo = j + 1
    return comps, moves


def _sift_down(a, root, end, trace):
    c = m = 0
    while True:
        child = 2 * root + 1
        if child >= end:
            break
        if child + 1 < end:
            c += 1
            if a[child] < a[child + 1]:
                child += 1
        c += 1
        if a[root] < a[child]:
            a[root], a[child] = a[child], a[root]
            m += 1
            if trace is not None:
                trace.append(tuple(a))
            root = child
        else:
            break
    return c, m


def heap_sort(a, trace=None):
    comps = moves = 0
    n = len(a)
    for start in range(n // 2 - 1, -1, -1):
        c, m = _sift_down(a, start, n, trace)
        comps += c; moves += m
    for end in range(n - 1, 0, -1):
        a[0], a[end] = a[end], a[0]
        moves += 1
        if trace is not None:
            trace.append(tuple(a))
        c, m = _sift_down(a, 0, end, trace)
        comps += c; moves += m
    return comps, moves


def timsort_baseline(a, trace=None):
    a.sort()                      # Python's built-in Timsort, shown as a reference line
    return None, None


ALGORITHMS = {
    "merge": dict(fn=merge_sort, label="Merge sort", paradigm="Divide and conquer",
                  best="O(n log n)", avg="O(n log n)", worst="O(n log n)", space="O(n)", stable=True, quadratic=False),
    "quick": dict(fn=quick_sort, label="Quick sort", paradigm="Divide and conquer",
                  best="O(n log n)", avg="O(n log n)", worst="O(n²)", space="O(log n)", stable=False, quadratic=False),
    "heap": dict(fn=heap_sort, label="Heap sort", paradigm="Transform and conquer (heap)",
                 best="O(n log n)", avg="O(n log n)", worst="O(n log n)", space="O(1)", stable=False, quadratic=False),
    "shell": dict(fn=shell_sort, label="Shell sort", paradigm="Diminishing increment",
                  best="O(n log n)", avg="about O(n^1.3)", worst="O(n^1.5)", space="O(1)", stable=False, quadratic=False),
    "insertion": dict(fn=insertion_sort, label="Insertion sort", paradigm="Decrease and conquer",
                      best="O(n)", avg="O(n²)", worst="O(n²)", space="O(1)", stable=True, quadratic=True),
    "selection": dict(fn=selection_sort, label="Selection sort", paradigm="Brute force",
                      best="O(n²)", avg="O(n²)", worst="O(n²)", space="O(1)", stable=False, quadratic=True),
    "bubble": dict(fn=bubble_sort, label="Bubble sort", paradigm="Brute force",
                   best="O(n)", avg="O(n²)", worst="O(n²)", space="O(1)", stable=True, quadratic=True),
    "timsort": dict(fn=timsort_baseline, label="Timsort (Python built-in)", paradigm="Hybrid merge and insertion",
                    best="O(n)", avg="O(n log n)", worst="O(n log n)", space="O(n)", stable=True, quadratic=False),
}


def info():
    return [{"key": k, **{f: v[f] for f in ("label", "paradigm", "best", "avg", "worst", "space", "stable", "quadratic")}}
            for k, v in ALGORITHMS.items()]


def run(name, items, repeats=1, trace=None):
    """Sort a copy of items. Returns (sorted_list, stats)."""
    algo = ALGORITHMS[name]
    best = None
    result = comps = moves = None
    for _ in range(max(1, repeats)):
        work = list(items)
        t0 = time.perf_counter()
        comps, moves = algo["fn"](work, trace)
        dt = (time.perf_counter() - t0) * 1000
        best = dt if best is None else min(best, dt)
        result = work
    return result, {"comparisons": comps, "moves": moves, "time_ms": round(best, 4)}
