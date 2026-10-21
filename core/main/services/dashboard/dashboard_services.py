"""
Dashboard data (services layer)
===============================
Every number and chart on the dashboard page is calculated here.
The view only calls get_dashboard_context() at the bottom and passes the
result to the template.

Dashboard section            -> function that feeds it
---------------------------------------------------------------------
Completed Samples This Week  -> get_completed_samples_stats()
Monthly Matches chart        -> get_monthly_chart_data()
Employee Performance table   -> get_employee_stats()
Sample vs Order chart        -> get_sample_vs_order_data()
KPI cards (All CMF, Pending  -> get_cmf_kpis() and get_total_matches()
  CMF, Completed CMF,
  Total Matches)
"""
import re
from collections import defaultdict
from datetime import timedelta

from django.db.models import Q
from django.db.models.aggregates import Count
from django.utils import timezone

from main.models import (
    tbl_audit_trail,
    tbl_cmf,
    tbl_master_formula_encode,
    tbl_mb_extruder_formula,
    tbl_dc_extruder_formula,
    tbl_cmf_pending_completed,
    tbl_submitted_selected,
    tbl_user,
    tbl_feedback_details,
)

# Text written into the audit trail when a CMF goes from Pending to Completed.
# The "completed this week" card counts audit rows that contain this text.
COMPLETED_MARKER = "Status (Pending -> Completed)"


# =====================================================================
# SHARED HELPERS
# =====================================================================

def _week_boundaries(today):
    """
    Our week runs Sunday -> Saturday (not the ISO Monday start).
    Returns (start_this_week, start_last_week, end_last_week) as dates.
    """
    # Python's weekday(): Mon=0 ... Sun=6.  Adding 1 and taking % 7 turns
    # that into Sun=0 ... Sat=6, i.e. "days since the last Sunday".
    days_since_sunday = (today.weekday() + 1) % 7
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
    the value doesn't end in a single letter (for example an RS number
    like '3546').
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

    # Audit rows this week that say "Pending -> Completed"
    completed_this_week = tbl_audit_trail.objects.filter(
        details__icontains=COMPLETED_MARKER,
        timestamp__date__gte=start_this_week,
        timestamp__date__lte=today,
    ).count()

    # Same count for the whole previous week, used for the comparison badge
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

    # abs(): the template shows the arrow for direction, so the number itself
    # is always positive.
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
    # key = (sort_key, label), e.g. ("2026-10", "Oct"); value = the two counters
    monthly = defaultdict(lambda: {"matches": 0, "rematches": 0})

    # Skip rows with no date, because they can't be placed in a month.
    formula_rows = [
        row for row in _formula_rows(["date", "cm_no_id"]) if row["date"] is not None
    ]

    for row in formula_rows:
        record_date = row["date"]
        cm_no = row["cm_no_id"]

        # sort_key keeps months in time order; label is what the chart shows
        sort_key = record_date.strftime("%Y-%m")
        label = record_date.strftime("%b")

        bucket = monthly[(sort_key, label)]

        # No letter suffix (e.g. "3546") means it's an RS record: always
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
# KPI CARDS (right column: All CMF / Pending CMF / Completed CMF / Total Matches)
# =====================================================================

def get_cmf_kpis():
    """
    Numbers for the first three KPI cards.

    - total_cmf       -> every CMF record in tbl_cmf that has a cm_no
    - pending_count   -> rows in tbl_cmf_pending_completed with is_completed=False
    - completed_count -> rows in tbl_cmf_pending_completed with is_completed=True

    Pending and Completed come from ONE database query: Count(..., filter=...)
    counts only the rows that match the condition, so both numbers are
    calculated in a single pass over the table.
    """
    # Ignore CMF rows with an empty cm_no (same rule used by the RS entry page)
    total_cmf = (
        tbl_cmf.objects
        .exclude(cm_no__isnull=True)
        .exclude(cm_no='')
        .count()
    )

    status_counts = tbl_cmf_pending_completed.objects.aggregate(
        pending=Count('pk', filter=Q(is_completed=False)),
        completed=Count('pk', filter=Q(is_completed=True)),
    )

    return {
        "total_cmf": total_cmf,
        "pending_count": status_counts["pending"],
        "completed_count": status_counts["completed"],
    }


def get_total_matches():
    """
    Total number of formulas, for the "Total Matches" card.

    A "match" is one formula row. This counts every row in both extruder
    formula tables (DC + MB), which is the same set of rows the Monthly
    Matches chart is built from (matches + rematches together).
    """
    return (
        tbl_dc_extruder_formula.objects.count()
        + tbl_mb_extruder_formula.objects.count()
    )


# =====================================================================
# EMPLOYEE PERFORMANCE TABLE (Matched / Rematches / Success % per person)
# =====================================================================

def _get_legacy_matched_counts():
    """
    Legacy encode records (`tbl_master_formula_encode.match_by`) stored the
    matcher as a free-text field with many typos/variants (e.g. "ANNA",
    "UPDATED BY: ANNA", "UPADTED BY: ANNA" all mean the same person). This
    groups those variants the same way the manual SQL audit did, and maps
    each group to the employee's canonical full name so the historical
    count can be folded into that employee's `matched` total.
    """
    legacy_counts = defaultdict(int)
    # One row per distinct match_by text, with how many records use it
    rows = (
        tbl_master_formula_encode.objects
        .values('match_by')
        .annotate(total=Count('encode_id'))
    )

    for row in rows:
        match_by = (row['match_by'] or '').strip().lower()
        total = row['total']

        if 'ann' in match_by or 'ana' in match_by:
            canonical = 'ana solomon'
        elif 'ernie' in match_by:
            canonical = 'ernie pio'
        elif match_by == 'geelyn rellin':
            canonical = 'geelyn rellin'
        elif match_by == 'jinky':
            canonical = 'jinky villacampa'
        elif match_by == 'esa':
            canonical = 'esa'
        elif match_by == 'linzy jam bautista':
            canonical = 'linzy jam bautista'
        else:
            continue  # KAREN, INDEX BY: KAREN, W19, blanks, etc. -> not mapped, skip

        legacy_counts[canonical] += total

    return legacy_counts


def _badge_for(success_pct):
    """Bootstrap badge colour for a success %: green >= 80, blue >= 60, else yellow."""
    if success_pct >= 80:
        return "bg-success-subtle text-success border border-success"
    if success_pct >= 60:
        return "bg-primary-subtle text-primary border border-primary"
    return "bg-warning-subtle text-warning border border-warning"


def get_employee_stats():
    """
    Builds the Matched / Rematches / Success % row for every user in the
    Laboratory department.

    - matched   -> raw count of every formula row (DC + MB) where this user
                   is the `matcher`, regardless of is_final.
    - rematches -> for every cm_no chain (A9170a, A9170b, A9170c, ...), the
                   existence of the next letter means the PREVIOUS letter's
                   match got rematched, so the rematch is credited to the
                   previous letter's matcher (not the new attempt's matcher).
    - success % -> matched / (matched + rematches)
    """
    # NOTE: adjust this regex if tbl_role.name doesn't literally contain
    # these words.
    eligible_users = tbl_user.objects.filter(
        role__department__iregex=r'(laboratory)'
    )

    all_rows = _formula_rows(["cm_no_id", "matcher_id"])

    # --- matched: simple per-user row count across both tables ---
    matched_counts = defaultdict(int)
    for row in all_rows:
        if row["matcher_id"]:
            matched_counts[row["matcher_id"]] += 1

    # --- build base -> {suffix: matcher_id}, no is_final filter ---
    # Example: "A9170" -> {"a": 12, "b": 7} means user 12 did the first
    # attempt and user 7 did the first rematch.
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
                continue  # 'a' is the first attempt, nothing came before it
            prev_letter = chr(ord(suffix) - 1)  # 'b' -> 'a', 'c' -> 'b', ...
            prev_matcher = suffix_map.get(prev_letter)
            if prev_matcher:
                rematch_counts[prev_matcher] += 1

    employee_stats = []
    for user in eligible_users:
        matched = matched_counts.get(user.id, 0)
        rematches = rematch_counts.get(user.id, 0)
        total = matched + rematches
        success_pct = round((matched / total) * 100) if total else 0

        employee_stats.append({
            "name": f"{user.first_name} {user.last_name}",
            "matched": matched,
            "rematches": rematches,
            "success_pct": success_pct,
            "badge_class": _badge_for(success_pct),
        })

    # temporarily add the past records
    # --- fold legacy tbl_master_formula_encode counts into matched totals ---
    # legacy_counts = _get_legacy_matched_counts()
    # for emp in employee_stats:
    #     key = emp["name"].strip().lower()
    #     legacy_total = legacy_counts.get(key)
    #     if legacy_total:
    #         emp["matched"] += legacy_total
    #         total = emp["matched"] + emp["rematches"]
    #         emp["success_pct"] = round((emp["matched"] / total) * 100) if total else 0
    #         emp["badge_class"] = _badge_for(emp["success_pct"])
    # end

    # Highest number of matches first
    employee_stats.sort(key=lambda e: e["matched"], reverse=True)
    return employee_stats


# =====================================================================
# SAMPLE VS ORDER CHART (donut chart)
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
# ENTRY POINT: assembles everything the dashboard template needs
# =====================================================================

def get_dashboard_context():
    """
    Called by the dashboard view. Each key below is a variable the template
    uses, e.g. {{ total_cmf }}.
    """
    completed_this_week, percent_change, trend = get_completed_samples_stats()
    kpis = get_cmf_kpis()

    return {
        # completed samples this week card
        "completed_this_week": completed_this_week,
        "percent_change": percent_change,
        "trend": trend,

        # monthly matches chart
        "monthly_chart_data": get_monthly_chart_data(),

        # KPI cards (right column)
        "total_cmf": kpis["total_cmf"],              # All CMF
        "pending_count": kpis["pending_count"],      # Pending CMF
        "completed_count": kpis["completed_count"],  # Completed CMF
        "total_matches": get_total_matches(),        # Total Matches

        # employee performance table
        "employee_stats": get_employee_stats(),

        # sample vs order chart
        "sample_order_chart_data": get_sample_vs_order_data(),
    }