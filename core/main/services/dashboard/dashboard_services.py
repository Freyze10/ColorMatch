import re
from collections import defaultdict
from datetime import timedelta

from django.utils import timezone

from main.models import (
    tbl_audit_trail,
    tbl_mb_extruder_formula,
    tbl_dc_extruder_formula,
    tbl_cmf_pending_completed,
    tbl_submitted_selected,
    tbl_user,
    tbl_feedback_details,
)

COMPLETED_MARKER = "Status (Pending -> Completed)"


# =====================================================================
# SHARED HELPERS
# =====================================================================

def _week_boundaries(today):
    """
    Our week runs Sunday -> Saturday (not the ISO Monday start).
    Returns (start_this_week, start_last_week, end_last_week) as dates.
    """
    days_since_sunday = (today.weekday() + 1) % 7  # Mon=0 ... Sun=6 -> Sun=0
    start_this_week = today - timedelta(days=days_since_sunday)
    start_last_week = start_this_week - timedelta(days=7)
    end_last_week = start_this_week - timedelta(days=1)
    return start_this_week, start_last_week, end_last_week


def _formula_rows(fields):
    """
    Pulls the requested columns from BOTH extruder formula tables (DC and MB)
    and returns them combined as one list of dicts. Several of the stats
    below (matches, rematches, matcher performance) need to look across
    both tables, so this avoids repeating the same two queries everywhere.
    """
    dc_rows = list(tbl_dc_extruder_formula.objects.values(*fields))
    mb_rows = list(tbl_mb_extruder_formula.objects.values(*fields))
    return dc_rows + mb_rows


def _cm_base_suffix(cm_no):
    """
    Splits a cm_no like 'A9170a' into ('A9170', 'a').
    The trailing letter marks which attempt this is (a = first attempt,
    b = first rematch, c = second rematch, ...). Returns (None, None) if
    the value doesn't end in a single letter.
    """
    if not cm_no:
        return None, None
    match = re.match(r'^(.*\d)([a-zA-Z])$', cm_no.strip())
    if not match:
        return None, None
    return match.group(1), match.group(2).lower()


# =====================================================================
# "COMPLETED SAMPLES THIS WEEK" CARD (top summary + up/down % badge)
# =====================================================================

def get_completed_samples_stats():
    """
    Counts how many CMF records were marked completed this week (Sunday
    through today) vs. last week (the full prior Sunday-Saturday), by
    scanning the audit trail for the "Status (Pending -> Completed)" entries.

    Returns (completed_this_week, percent_change, trend) where trend is
    "up" or "down" for the badge arrow/color.
    """
    today = timezone.localdate()
    start_this_week, start_last_week, end_last_week = _week_boundaries(today)

    completed_this_week = tbl_audit_trail.objects.filter(
        details__icontains=COMPLETED_MARKER,
        timestamp__date__gte=start_this_week,
        timestamp__date__lte=today,
    ).count()

    completed_last_week = tbl_audit_trail.objects.filter(
        details__icontains=COMPLETED_MARKER,
        timestamp__date__gte=start_last_week,
        timestamp__date__lte=end_last_week,
    ).count()

    if completed_last_week == 0:
        # avoid divide-by-zero; treat "went from 0 to something" as +100%
        percent_change = 100 if completed_this_week > 0 else 0
    else:
        percent_change = round(
            ((completed_this_week - completed_last_week) / completed_last_week) * 100
        )

    trend = "up" if completed_this_week >= completed_last_week else "down"

    return completed_this_week, abs(percent_change), trend


# =====================================================================
# "MONTHLY MATCHES" CHART (amCharts bar + line, matches vs rematches)
# =====================================================================

def get_monthly_chart_data():
    """
    Groups every formula row (DC + MB) by the month of its `date`, and
    within each month splits it into:
      - matches   -> cm_no ends in 'a' (or has no cm_no at all)
      - rematches -> cm_no ends in any other letter (b, c, d, ...)

    Returns a list like:
      [{"month": "Jun", "matches": 70, "rematches": 22}, ...]
    sorted chronologically, ready to hand straight to the chart's data.setAll().
    """
    monthly = defaultdict(lambda: {"matches": 0, "rematches": 0})

    formula_rows = [
        row for row in _formula_rows(["date", "cm_no_id"]) if row["date"] is not None
    ]

    for row in formula_rows:
        record_date = row["date"]
        cm_no = row["cm_no_id"]

        sort_key = record_date.strftime("%Y-%m")
        label = record_date.strftime("%b")

        bucket = monthly[(sort_key, label)]

        # No letter suffix (e.g. "3546") means it's an RS record — always
        # a normal match, never a rematch. Only 'b', 'c', ... suffixes on
        # CMF-style cm_no's (e.g. "A9170b") count as rematches.
        _, suffix = _cm_base_suffix(cm_no)
        if not suffix or suffix == "a":
            bucket["matches"] += 1
        else:
            bucket["rematches"] += 1

    return [
        {"month": label, "matches": vals["matches"], "rematches": vals["rematches"]}
        for (sort_key, label), vals in sorted(monthly.items(), key=lambda item: item[0][0])
    ]


# =====================================================================
# "PENDING" KPI CARD
# =====================================================================

def get_pending_count():
    """Simple count of CMF records still marked as not completed."""
    return tbl_cmf_pending_completed.objects.filter(is_completed=False).count()


# =====================================================================
# EMPLOYEE PERFORMANCE TABLE (Matched / Rematches / Success % per person)
# =====================================================================

def get_employee_stats():
    """
    Builds the Matched / Rematches / Success % row for every user in the
    Laboratory or Information Technology roles.

    - matched   -> raw count of every formula row (DC + MB) where this user
                   is the `matcher`, regardless of is_final.
    - rematches -> for every cm_no chain (A9170a, A9170b, A9170c, ...), only
                   the row with is_final=True "owns" that attempt. If the
                   next letter's final row exists, that means the PREVIOUS
                   letter's final match got rematched, so the rematch is
                   credited to the previous letter's final matcher
                   (not the new attempt's matcher).
    """
    # NOTE: adjust this regex if tbl_role.name doesn't literally contain
    # these words.
    eligible_users = tbl_user.objects.filter(
        role__department__iregex=r'(laboratory|information technology)'
    )

    all_rows = _formula_rows(["cm_no_id", "matcher_id"])

    # --- matched: simple per-user row count across both tables ---
    matched_counts = defaultdict(int)
    for row in all_rows:
        if row["matcher_id"]:
            matched_counts[row["matcher_id"]] += 1

    # --- build base -> {suffix: matcher_id}, no is_final filter ---
    matcher_by_suffix = defaultdict(dict)
    for row in all_rows:
        base, suffix = _cm_base_suffix(row["cm_no_id"])
        if base:
            matcher_by_suffix[base][suffix] = row["matcher_id"]

    # --- existence of suffix N implies suffix (N-1) was rematched ---
    rematch_counts = defaultdict(int)
    for base, suffix_map in matcher_by_suffix.items():
        for suffix in suffix_map:
            if suffix == 'a':
                continue
            prev_letter = chr(ord(suffix) - 1)
            prev_matcher = suffix_map.get(prev_letter)
            if prev_matcher:
                rematch_counts[prev_matcher] += 1

    employee_stats = []
    for user in eligible_users:
        matched = matched_counts.get(user.id, 0)
        rematches = rematch_counts.get(user.id, 0)
        total = matched + rematches
        success_pct = round((matched / total) * 100) if total else 0

        if success_pct >= 80:
            badge_class = "bg-success-subtle text-success border border-success"
        elif success_pct >= 60:
            badge_class = "bg-primary-subtle text-primary border border-primary"
        else:
            badge_class = "bg-warning-subtle text-warning border border-warning"

        employee_stats.append({
            "name": f"{user.first_name} {user.last_name}",
            "matched": matched,
            "rematches": rematches,
            "success_pct": success_pct,
            "badge_class": badge_class,
        })

    employee_stats.sort(key=lambda e: e["matched"], reverse=True)
    return employee_stats


# =====================================================================
# SAMPLE VS ORDER CHART (pie chart) — not wired to the DB yet, skip for now
# =====================================================================

def get_sample_vs_order_data():
    """
    Samples/Chips -> count of distinct tbl_cmf_pending_completed records
    that have a tbl_submitted_selected row pointing to the "Sample" or
    "Chips" option (Price-only submissions are excluded).

    Orders -> count of tbl_feedback_details rows whose status is
    "Ordered". Defaults to 0 if there are no matching rows for either.
    """
    samples_chips_count = tbl_submitted_selected.objects.filter(
        option_id__name__in=["Sample", "Chips"]
    ).values("completed_id").distinct().count()
    orders_count = tbl_feedback_details.objects.filter(status__iexact="Ordered").count()

    return [
        {"category": "Samples/Chips", "value": samples_chips_count},
        {"category": "Orders", "value": orders_count},
    ]


# =====================================================================
# ENTRY POINT — assembles everything the dashboard template needs
# =====================================================================

def get_dashboard_context():
    completed_this_week, percent_change, trend = get_completed_samples_stats()

    return {
        # completed samples this week card
        "completed_this_week": completed_this_week,
        "percent_change": percent_change,
        "trend": trend,

        # monthly matches chart
        "monthly_chart_data": get_monthly_chart_data(),

        # pending KPI card
        "pending_count": get_pending_count(),

        # employee performance table
        "employee_stats": get_employee_stats(),

        # sample vs order chart
        "sample_order_chart_data": get_sample_vs_order_data(),
    }