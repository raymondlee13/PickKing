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

import os

try:
    import openpyxl
    OPENPYXL_AVAILABLE = True
except ImportError:
    OPENPYXL_AVAILABLE = False

TIER_ORDER = ["BELOW BAR", "TIER C", "TIER B", "TIER A", "TIER S"]


def _read_graded_rows(leg_log):
    rows = []
    r = 2
    while leg_log.cell(row=r, column=5).value not in (None, ""):  # column E = Player
        result = leg_log.cell(row=r, column=21).value  # column U = Result
        if result in ("W", "L"):  # exclude blank/pending and PUSH -- neither is a real outcome
            rows.append({
                "true_pct": leg_log.cell(row=r, column=15).value,  # column O
                "line_type": leg_log.cell(row=r, column=11).value,  # column K
                "tier": leg_log.cell(row=r, column=19).value,  # column S
                "hit": 1 if result == "W" else 0,
            })
        r += 1
    return rows


def build_report(workbook_path):
    """Returns (success, message, data). data is None on failure, otherwise:
    {total_graded, brier_score, fixed_bar_by_tier, variable_bar_calibration}
    """
    if not OPENPYXL_AVAILABLE:
        return False, "openpyxl isn't installed. In Command Prompt run: pip install openpyxl --break-system-packages , then restart the app.", None
    if not workbook_path:
        return False, "No tracking workbook path set. Add \"tracking_workbook_path\" in config.json.", None
    if not os.path.exists(workbook_path):
        return False, f"Workbook not found at: {workbook_path}. Check the path in config.json.", None

    try:
        wb = openpyxl.load_workbook(workbook_path)
    except PermissionError:
        return False, "Couldn't open the workbook -- close it in Excel first, then try again.", None
    except Exception as e:
        return False, f"Couldn't open workbook: {type(e).__name__}: {e}", None

    if "Leg Log" not in wb.sheetnames:
        return False, "Workbook doesn't have a 'Leg Log' sheet -- wrong file?", None

    rows = _read_graded_rows(wb["Leg Log"])
    if not rows:
        return True, "No graded picks yet (Result = W/L) -- log some picks and run \"Check results\" first.", {
            "total_graded": 0, "brier_score": None, "fixed_bar_by_tier": [], "variable_bar_calibration": [],
        }

    scored = [r for r in rows if r["true_pct"] is not None]
    brier_score = round(sum((r["true_pct"] - r["hit"]) ** 2 for r in scored) / len(scored), 4) if scored else None

    fixed_bar = [r for r in rows if (r["line_type"] or "STD") == "STD"]
    variable_bar = [r for r in rows if r["line_type"] in ("GOBLIN", "DEMON")]

    by_tier = {}
    for r in fixed_bar:
        by_tier.setdefault(r["tier"], []).append(r["hit"])
    fixed_bar_by_tier = [
        {"tier": t, "n": len(hits), "hit_rate": round(sum(hits) / len(hits), 3)}
        for t, hits in by_tier.items()
    ]
    fixed_bar_by_tier.sort(key=lambda x: TIER_ORDER.index(x["tier"]) if x["tier"] in TIER_ORDER else -1)

    buckets = {}
    for r in variable_bar:
        if r["true_pct"] is None:
            continue
        bucket = min(int(r["true_pct"] * 10), 9) * 10  # 0, 10, ..., 90
        buckets.setdefault(bucket, []).append(r)
    variable_bar_calibration = []
    for bucket in sorted(buckets):
        entries = buckets[bucket]
        avg_predicted = sum(r["true_pct"] for r in entries) / len(entries)
        actual_hit_rate = sum(r["hit"] for r in entries) / len(entries)
        variable_bar_calibration.append({
            "bucket": f"{bucket}-{bucket + 10}%", "n": len(entries),
            "avg_predicted": round(avg_predicted * 100, 1),
            "actual_hit_rate": round(actual_hit_rate * 100, 1),
        })

    data = {
        "total_graded": len(rows),
        "brier_score": brier_score,
        "fixed_bar_by_tier": fixed_bar_by_tier,
        "variable_bar_calibration": variable_bar_calibration,
    }
    return True, "OK", data
