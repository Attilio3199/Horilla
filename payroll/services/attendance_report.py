"""Readable daily summaries of attendance discrepancies."""

from collections import defaultdict
from decimal import Decimal


def format_hours(value):
    rounded = Decimal(str(value)).quantize(Decimal("0.01"))
    if rounded == 0:
        return "0"
    return f"{rounded:.2f}".rstrip("0").rstrip(".").replace(".", ",")


def daily_summaries(discrepancies):
    days = {}
    for discrepancy in discrepancies:
        day = days.setdefault(discrepancy["giorno"], {
            "app": defaultdict(lambda: Decimal(0)),
            "cedolino": defaultdict(lambda: Decimal(0)),
        })
        for side, key in (("app", "dettaglio_app"), ("cedolino", "dettaglio_cedolino")):
            for item in discrepancy[key]:
                day[side][item["causale"]] += Decimal(str(item["ore"]))
    summaries = []
    for day, values in sorted(days.items()):
        app_total = sum(values["app"].values(), Decimal(0))
        ced_total = sum(values["cedolino"].values(), Decimal(0))

        def describe(side):
            return "; ".join(
                f"{name}: {format_hours(hours)} h"
                for name, hours in sorted(values[side].items()) if hours
            ) or "nessuna ora nelle causali confrontate"

        if abs(ced_total - app_total) <= Decimal("0.05"):
            outcome = (
                f"Totale delle causali confrontate uguale ({format_hours(app_total)} h), "
                "ma causali non equivalenti secondo il dizionario."
            )
        else:
            outcome = (
                f"Totali delle causali confrontate: app {format_hours(app_total)} h, "
                f"cedolino {format_hours(ced_total)} h. "
                f"Differenza: {format_hours(ced_total - app_total)} h (cedolino meno app)."
            )
        summaries.append({
            "giorno": day, "app": describe("app"),
            "cedolino": describe("cedolino"), "esito": outcome,
        })
    return summaries
