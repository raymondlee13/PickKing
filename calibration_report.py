"""Reads the tracking workbook's 'Leg Log' sheet and checks whether the
grading system's calibration actually holds up against real graded results.

Tier isn't a probability -- it's edge relative to THAT leg's own bar, and for
goblin/demon legs the bar comes from a calibrated multiplier that varies a
lot by market/deviation (see scoring.py's calibrated_bar_for_leg). That means
a 20%-true-probability goblin graded against a 5% bar and a 70%-true-
probability standard leg graded against the flat 55% bar can land in the
SAME tier despite wildly different real hit rates -- so averaging "hit rate
by tier" across both leg types blindly produces a meaningless number (see
chat -- caught by the user, not something this module used to account for).

Standard/discount legs always grade against the flat bar (DEFAULT_BAR in
scoring.py -- LINE_TYPE_MAP has no "discount" entry, so those rows are
written with Line Type "STD" right alongside real standard legs), so for
THEM tier ordering is mathematically guaranteed to track hit-rate ordering --
safe to report directly. Goblin/demon legs get a different check instead: a
calibration curve bucketed by the model's predicted True %, which is immune
to the bar varying per leg -- a well-calibrated model's actual hit rate in
each bucket should roughly match the predicted probability for that bucket.

Reads raw stored values (True %, Bar, Line Type, Tier, Result) rather than
the sheet's own formula columns (Margin/Hit/Squared Error), since openpyxl
never evaluates formulas -- it only returns Excel's last cached value if
Excel itself saved the file after these rows were added, which isn't
guaranteed. Recomputing from raw inputs sidesteps that entirely.
"""

import math

from excel_logging import COL, entry_outcomes, leg_key, open_workbook

TIER_ORDER = ["BELOW BAR", "TIER C", "TIER B", "TIER A", "TIER S"]
# Tier as the report shows it, from the code the workbook stores ("S" -> "TIER S").
_TIER_FROM_CODE = {t.split()[-1]: t for t in TIER_ORDER if t.startswith("TIER")}


def wilson_interval(hits, n, z=1.96):
    """95% range the true hit rate plausibly sits in, given hits out of n.
    Unlike the textbook p +/- 1.96*sqrt(p(1-p)/n), stays sensible for small n
    and rates near 0/100% -- exactly the small-tier and goblin/demon cases here."""
    if n == 0:
        return None
    p = hits / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, center - half), min(1.0, center + half)  # clamp float noise at 0/n and n/n


def _ci_pct(hits, n):
    low, high = wilson_interval(hits, n)
    return round(low * 100, 1), round(high * 100, 1)


def _read_rows(leg_log):
    """Every logged leg with a W/L result or a CLV verdict -- CLV is filled at
    kickoff, so it's often known well before (or without) a W/L. A pick logged
    more than once (tracking-only, then inside a real entry) counts once."""
    rows = {}
    r = 2
    while leg_log.cell(row=r, column=COL["Player"]).value not in (None, ""):
        result = leg_log.cell(row=r, column=COL["Result"]).value
        clv = leg_log.cell(row=r, column=COL["CLV Favorable?"]).value
        if result in ("W", "L") or clv in ("YES", "NO"):  # PUSH isn't a real outcome
            tier = leg_log.cell(row=r, column=COL["Tier"]).value
            row = {
                "true_pct": leg_log.cell(row=r, column=COL["Predicted True %"]).value,
                "line_type": leg_log.cell(row=r, column=COL["Line Type"]).value,
                "tier": _TIER_FROM_CODE.get(tier, tier),
                "hit": {"W": 1, "L": 0}.get(result),  # None = not graded yet
                "clv": {"YES": 1, "NO": 0}.get(clv),
            }
            first = rows.setdefault(leg_key(leg_log, r), row)
            for field in ("hit", "clv"):  # the first copy may not be graded yet
                if first[field] is None:
                    first[field] = row[field]
        r += 1
    return list(rows.values())


def _tier_sort_key(x):
    return TIER_ORDER.index(x["tier"]) if x["tier"] in TIER_ORDER else -1


def build_report(workbook_path):
    """Returns (success, message, data). data is None on failure, otherwise:
    {total_graded, brier_score, fixed_bar_by_tier, variable_bar_calibration, clv_by_tier, entries}
    Every hit_rate/clv_rate comes with a 95% Wilson interval (ci_low/ci_high, in %).
    """
    wb, error = open_workbook(workbook_path)
    if error:
        return False, error, None

    all_rows = _read_rows(wb["Leg Log"])
    rows = [r for r in all_rows if r["hit"] is not None]

    clv_groups = {}
    for r in all_rows:
        if r["clv"] is not None:
            clv_groups.setdefault(r["tier"], []).append(r["clv"])
    clv_by_tier = [
        {"tier": t, "n": len(v), "clv_rate": round(sum(v) / len(v) * 100, 1), "ci": _ci_pct(sum(v), len(v))}
        for t, v in clv_groups.items()
    ]
    clv_by_tier.sort(key=_tier_sort_key)
    entry_summary = _entry_summary(wb) if "Entry Log" in wb.sheetnames else None

    if not rows:
        return True, "No graded picks yet (Result = W/L) -- log some picks and run \"Check results\" first.", {
            "total_graded": 0, "brier_score": None, "fixed_bar_by_tier": [], "variable_bar_calibration": [],
            "clv_by_tier": clv_by_tier, "entries": entry_summary,
        }

    scored = [r for r in rows if r["true_pct"] is not None]
    brier_score = round(sum((r["true_pct"] - r["hit"]) ** 2 for r in scored) / len(scored), 4) if scored else None

    fixed_bar = [r for r in rows if (r["line_type"] or "STD") == "STD"]
    variable_bar = [r for r in rows if r["line_type"] in ("GOBLIN", "DEMON")]

    by_tier = {}
    for r in fixed_bar:
        by_tier.setdefault(r["tier"], []).append(r["hit"])
    fixed_bar_by_tier = [
        {"tier": t, "n": len(hits), "hit_rate": round(sum(hits) / len(hits), 3), "ci": _ci_pct(sum(hits), len(hits))}
        for t, hits in by_tier.items()
    ]
    fixed_bar_by_tier.sort(key=_tier_sort_key)

    buckets = {}
    for r in variable_bar:
        if r["true_pct"] is None:
            continue
        bucket = min(int(r["true_pct"] * 10), 9) * 10  # 0, 10, ..., 90
        buckets.setdefault(bucket, []).append(r)
    variable_bar_calibration = []
    for bucket in sorted(buckets):
        entries = buckets[bucket]
        hits = sum(r["hit"] for r in entries)
        avg_predicted = round(sum(r["true_pct"] for r in entries) / len(entries) * 100, 1)
        ci = _ci_pct(hits, len(entries))
        variable_bar_calibration.append({
            "bucket": f"{bucket}-{bucket + 10}%", "n": len(entries),
            "avg_predicted": avg_predicted,
            "actual_hit_rate": round(hits / len(entries) * 100, 1),
            "ci": ci,
            # Predicted % outside the range = miscalibrated, not just unlucky.
            "consistent": ci[0] <= avg_predicted <= ci[1],
        })

    data = {
        "total_graded": len(rows),
        "brier_score": brier_score,
        "fixed_bar_by_tier": fixed_bar_by_tier,
        "variable_bar_calibration": variable_bar_calibration,
        "clv_by_tier": clv_by_tier,
        "entries": entry_summary,
    }
    return True, "OK", data


def _entry_summary(wb):
    """Real placed entries: what they actually paid vs. what the model said
    they'd pay (Modelled EV), both per 1 unit staked. The honest bottom line --
    tiers and calibration only matter if this ends up above 1.0."""
    outcomes = entry_outcomes(wb)
    settled = [o for o in outcomes if o["status"] == "settled"]
    staked = [o for o in settled if o["stake"] is not None]
    modelled = [o["modelled_ev"] for o in settled if isinstance(o["modelled_ev"], (int, float))]
    return {
        "settled": len(settled),
        "pending": sum(1 for o in outcomes if o["status"] == "pending"),
        "manual": sum(1 for o in outcomes if o["status"] == "manual"),
        "cashed": sum(1 for o in settled if o["payout"] > 0),
        "avg_modelled_ev": round(sum(modelled) / len(modelled), 3) if modelled else None,
        "avg_actual_return": round(sum(o["payout"] for o in settled) / len(settled), 3) if settled else None,
        "total_staked": round(sum(o["stake"] for o in staked), 2),
        "total_net": round(sum(o["stake"] * (o["payout"] - 1) for o in staked), 2),
    }
