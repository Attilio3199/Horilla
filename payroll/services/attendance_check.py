"""Daily matching of app hours to compatible payslip hours, without reuse."""

from collections import defaultdict, deque
from decimal import Decimal


TOLERANCE = Decimal("0.05")


def reconcile_hours(app_hours, payslip_hours, allowed):
    """Return incompatible daily groups; allowed maps voice -> app types.

    A maximum flow allocates each hour once, including when the allowed
    lists overlap. Comparing only group totals would miss incompatible
    distributions with the same total.
    """
    neighbours = defaultdict(set)
    for voice, types in allowed.items():
        for kind in types:
            neighbours[("voice", voice)].add(("app", kind))
            neighbours[("app", kind)].add(("voice", voice))

    remaining = set(neighbours)
    discrepancies = []
    while remaining:
        start = min(remaining, key=str)
        component = {start}
        queue = deque([start])
        while queue:
            for neighbour in neighbours[queue.popleft()]:
                if neighbour not in component:
                    component.add(neighbour)
                    queue.append(neighbour)
        remaining -= component
        types = sorted(n[1] for n in component if n[0] == "app")
        voices = sorted(n[1] for n in component if n[0] == "voice")
        demand = {t: Decimal(str(app_hours.get(t) or 0)) for t in types}
        supply = {v: Decimal(str(payslip_hours.get(v) or 0)) for v in voices}
        total_app = sum(demand.values(), Decimal(0))
        total_ced = sum(supply.values(), Decimal(0))
        if all(abs(v) <= TOLERANCE for v in [*demand.values(), *supply.values()]):
            continue

        residual = defaultdict(dict)

        def edge(a, b, capacity):
            residual[a][b] = capacity
            residual[b].setdefault(a, Decimal(0))

        source, sink = ("source",), ("sink",)
        for kind, hours in demand.items():
            edge(source, ("app", kind), max(hours, Decimal(0)))
        for voice, hours in supply.items():
            edge(("voice", voice), sink, max(hours, Decimal(0)))
            for kind in sorted(allowed[voice]):
                edge(("app", kind), ("voice", voice),
                     max(total_app, total_ced, Decimal(0)))

        matched = Decimal(0)
        while True:
            parents = {source: None}
            queue = deque([source])
            while queue and sink not in parents:
                node = queue.popleft()
                for nxt, capacity in residual[node].items():
                    if capacity > 0 and nxt not in parents:
                        parents[nxt] = node
                        queue.append(nxt)
            if sink not in parents:
                break
            amount = None
            node = sink
            while parents[node] is not None:
                prev = parents[node]
                capacity = residual[prev][node]
                amount = capacity if amount is None else min(amount, capacity)
                node = prev
            node = sink
            while parents[node] is not None:
                prev = parents[node]
                residual[prev][node] -= amount
                residual[node][prev] += amount
                node = prev
            matched += amount

        # Signed/negative imported values must not silently cancel anomalies.
        missing = sum((max(h, Decimal(0)) for h in demand.values()), Decimal(0)) - matched
        extra = sum((max(h, Decimal(0)) for h in supply.values()), Decimal(0)) - matched
        negative = any(h < -TOLERANCE for h in [*demand.values(), *supply.values()])
        if missing > TOLERANCE or extra > TOLERANCE or negative:
            discrepancies.append({
                "types": types, "voices": voices,
                "app": total_app, "payslip": total_ced,
                "missing": missing, "extra": extra,
            })
    return discrepancies
