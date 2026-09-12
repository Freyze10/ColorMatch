from datetime import datetime

from django.core.cache import cache
from django.db import transaction
from django.http import JsonResponse
from django.db.models import Q, Value, CharField
from django.db.models.functions import Coalesce
from django.db.models.expressions import OuterRef, Subquery, Case, When
from main.utils.log_audit_trail import log_audit
from main.models import (
    tbl_feedback_details, tbl_cmf_pending_completed, tbl_cmf_formula,
    tbl_cmf_dates, tbl_mb_extruder_formula, tbl_dc_extruder_formula,
    tbl_submitted_selected,
)

CACHE_KEY = 'feedback_records_list'

# Canonical list — every value the DB column can legally hold.
FEEDBACK_STATUS_OPTIONS = [
    'Pending',
    'Rematch',
    'Abandoned',
    'Ordered',
    'Approved with result',
    'Approved without result',
    'Request for additional samples',
    'Approved and request for samples',
]

# Always available, regardless of what was submitted.
BASE_STATUSES = ['Rematch', 'Abandoned', 'Ordered']

# When Sample is among the submitted items — full 3-choice set.
SAMPLE_STATUSES = [
    'Approved with result',
    'Approved without result',
    'Request for additional samples',
]

# When only Chips and/or Price were submitted (no Sample) — no "with result" option.
CHIP_PRICE_STATUSES = [
    'Approved without result',
    'Request for additional samples',
    'Approve and request for samples',
]

def get_feedback_status_choices(selected_option_names):
    """
    Given the option names from tbl_submitted_selected (e.g. ['Sample'],
    ['Chips', 'Price']), returns the list of status strings selectable
    for this record.

    - 'Sample' present (alone or combined with Chips/Price) -> full 3-choice set.
    - Only 'Chips' and/or 'Price' present -> Chips/Price choice set.
    - Nothing submitted yet / tracking record missing -> show every specific
      choice so nothing is wrongly hidden.
    """
    names = set(selected_option_names)

    if 'Sample' in names:
        specific = SAMPLE_STATUSES
    elif names & {'Chips', 'Price'}:
        specific = CHIP_PRICE_STATUSES
    else:
        specific = list(dict.fromkeys(SAMPLE_STATUSES + CHIP_PRICE_STATUSES))

    return list(dict.fromkeys(BASE_STATUSES + specific))

def _format_val(val):
    """Standardizes values for comparison."""
    if val is None or val == "" or val == "None":
        return "---"
    return str(val).strip()


def _parse_date(d_str):
    """Converts MM/DD/YYYY string from form to Python date object."""
    if not d_str:
        return None
    try:
        return datetime.strptime(d_str.strip(), '%m/%d/%Y').date()
    except ValueError:
        return None


def _get_selected_option_names(tracking):
    """Returns the submitted-option names (Sample/Chips/Price) for a tracking record."""
    if not tracking:
        return []
    return list(
        tbl_submitted_selected.objects.filter(completed_id=tracking).values_list('option_id__name', flat=True)
    )



def get_feedback_form_data(feedback_no):
    """
    Fetches a single feedback record with all related CMF/RS context,
    formatted for the feedback entry form. Returns {} if not found.
    """
    form_data = {}
    fb = tbl_feedback_details.objects.select_related('cm_no', 'rs_no').filter(feedback_no=feedback_no).first()
    if not fb:
        return form_data

    tracking = None

    if fb.cm_no:
        pending_info = tbl_cmf_pending_completed.objects.filter(cm_no=fb.cm_no).select_related('code').first()
        formula = tbl_cmf_formula.objects.filter(cm_no=fb.cm_no).first()
        dates = tbl_cmf_dates.objects.filter(cm_no=fb.cm_no).first()
        pending = tbl_cmf_pending_completed.objects.filter(cm_no=fb.cm_no).first()
        tracking = pending

        form_data = {
            'feedback_no': fb.feedback_no,
            'matching_no': fb.cm_no.cm_no,
            'customer': formula.customer if formula else '',
            'date_created': dates.form_made.strftime('%m/%d/%Y') if dates and dates.form_made else '',
            'required_date': dates.date_required if dates else '',
            'date_received': dates.date_received_lab if dates else '',
            'due_date': dates.due_date_lab.strftime('%m/%d/%Y') if dates and dates.due_date_lab else '',
            'finished_product': formula.finished_product if formula else '',
            'color_description': fb.cm_no.color_desc or '',
            'matching_type': fb.cm_no.matching_type or '',
            'sales_person': fb.cm_no.sm.name if fb.cm_no.sm else '',
            'current_status': 'Completed' if (pending and pending.is_completed) else 'Pending',
            'pending_reason': pending.reason if pending else '',
            'product_code': pending_info.code.product_code if pending_info and pending_info.code else "",
            'code_description': pending.code_details if pending else '',
            'date_submitted': pending.date_submitted.strftime('%m/%d/%Y') if pending and pending.date_submitted else '',
            'ar_number': pending.ar_no if pending else '',
            'ar_date': pending.ar_date.strftime('%m/%d/%Y') if pending and pending.ar_date else '',
            'record_type': 'cmf',
            'feedback_status': fb.status or 'Pending',
            'date_sample_received': fb.date_sample_received.strftime('%m/%d/%Y') if fb.date_sample_received else '',
            'comments': fb.comment or '',
            'storage_details': fb.storage_details or '',
        }

    elif fb.rs_no:
        pending_info = tbl_cmf_pending_completed.objects.filter(rs_no=fb.rs_no).select_related('code').first()
        pending = tbl_cmf_pending_completed.objects.filter(rs_no=fb.rs_no).first()
        dates = tbl_cmf_dates.objects.filter(rs_no=fb.rs_no).first()
        tracking = pending

        form_data = {
            'feedback_no': fb.feedback_no,
            'matching_no': fb.rs_no.rs_no,
            'customer': fb.rs_no.customer or '',
            'date_created': dates.form_made.strftime('%m/%d/%Y') if dates and dates.form_made else '',
            'required_date': dates.date_required if dates else '',
            'date_received': dates.date_received_lab if dates else '',
            'due_date': dates.due_date_lab.strftime('%m/%d/%Y') if dates and dates.due_date_lab else '',
            'finished_product': fb.rs_no.finished_product or '',
            'color_description': fb.rs_no.color_desc or '',
            'matching_type': fb.rs_no.matching_type or '',
            'sales_person': fb.rs_no.sm_no.name if fb.rs_no.sm_no else '',
            'current_status': 'Completed' if (pending and pending.is_completed) else 'Pending',
            'pending_reason': pending.reason if pending else '',
            'product_code': pending_info.code.product_code if pending_info and pending_info.code else "",
            'code_description': pending.code_details if pending else '',
            'date_submitted': pending.date_submitted.strftime('%m/%d/%Y') if pending and pending.date_submitted else '',
            'ar_number': pending.ar_no if pending else '',
            'ar_date': pending.ar_date.strftime('%m/%d/%Y') if pending and pending.ar_date else '',
            'record_type': 'rs',
            'feedback_status': fb.status or 'Pending',
            'date_sample_received': fb.date_sample_received.strftime('%m/%d/%Y') if fb.date_sample_received else '',
            'comments': fb.comment or '',
            'storage_details': fb.storage_details or '',
        }

    # --- Compute the allowed status choices for this record ---
    selected_names = _get_selected_option_names(tracking)
    form_data['status_choices'] = get_feedback_status_choices(selected_names)

    return form_data


def get_feedback_queryset():
    """
    Base queryset for Feedback Records with every display field annotated
    at the DB level via subqueries. Pagination/search/sort all run in SQL,
    so a page load only touches `length` rows instead of the whole table.
    """
    mb_final_code = tbl_mb_extruder_formula.objects.filter(
        cm_no=OuterRef('cm_no'), is_final=True
    ).values('code__product_code')[:1]

    dc_final_code = tbl_dc_extruder_formula.objects.filter(
        cm_no=OuterRef('cm_no'), is_final=True
    ).values('code__product_code')[:1]

    cmf_formula = tbl_cmf_formula.objects.filter(cm_no=OuterRef('cm_no'))

    cmf_dates_cm = tbl_cmf_dates.objects.filter(cm_no=OuterRef('cm_no'))
    cmf_dates_rs = tbl_cmf_dates.objects.filter(rs_no=OuterRef('rs_no'))

    rs_pending_code = tbl_cmf_pending_completed.objects.filter(
        rs_no=OuterRef('rs_no')
    ).values('code__product_code')[:1]

    return tbl_feedback_details.objects.select_related('cm_no', 'rs_no', 'code').annotate(
        matching_no=Coalesce('cm_no__cm_no', 'rs_no__rs_no'),
        customer=Coalesce(Subquery(cmf_formula.values('customer')[:1]), 'rs_no__customer'),
        color_desc=Coalesce('cm_no__color_desc', 'rs_no__color_desc'),
        finished_prod=Coalesce(Subquery(cmf_formula.values('finished_product')[:1]), 'rs_no__finished_product'),
        matching_type=Coalesce('cm_no__matching_type', 'rs_no__matching_type'),
        required_date=Coalesce(
            Subquery(cmf_dates_cm.values('date_required')[:1]),
            Subquery(cmf_dates_rs.values('date_required')[:1]),
        ),
        due_date=Coalesce(
            Subquery(cmf_dates_cm.values('due_date_lab')[:1]),
            Subquery(cmf_dates_rs.values('due_date_lab')[:1]),
        ),
        prod_code=Coalesce(
            Subquery(mb_final_code),
            Subquery(dc_final_code),
            Subquery(rs_pending_code),
            'code__product_code',
        ),
        mode=Case(
            When(cm_no__isnull=False, then=Value('cmf')),
            default=Value('rs'),
            output_field=CharField(),
        ),
    )

COLUMN_FIELD_MAP = {
    'Matching No.': 'matching_no',
    'Customer': 'customer',
    'Product Code': 'prod_code',
    'Color Description': 'color_desc',
    'Finished Product': 'finished_prod',
    'Type': 'matching_type',
    'Status': 'status',
}


def get_feedback_records_data(request):
    """DataTables server-side endpoint for the Feedback Records table."""
    draw = int(request.GET.get('draw', 1))
    start = int(request.GET.get('start', 0))
    length = int(request.GET.get('length', 100))
    search_value = request.GET.get('search[value]', '').strip()
    col_choice = request.GET.get('column_choice', 'all')

    queryset = get_feedback_queryset()
    total_records = queryset.count()

    if search_value:
        field = COLUMN_FIELD_MAP.get(col_choice)
        if field:
            queryset = queryset.filter(**{f'{field}__icontains': search_value})
        else:
            queryset = queryset.filter(
                Q(matching_no__icontains=search_value) |
                Q(customer__icontains=search_value) |
                Q(prod_code__icontains=search_value) |
                Q(color_desc__icontains=search_value) |
                Q(finished_prod__icontains=search_value) |
                Q(matching_type__icontains=search_value) |
                Q(status__icontains=search_value) |
                Q(comment__icontains=search_value) |
                Q(storage_details__icontains=search_value)
            )

    filtered_records = queryset.count()

    page = queryset.order_by('-feedback_no')[start:start + length].values(
        'feedback_no', 'matching_no', 'customer', 'prod_code', 'color_desc',
        'finished_prod', 'required_date', 'due_date', 'matching_type',
        'status', 'comment', 'storage_details', 'mode',
    )

    data = [
        {
            'feedback_no': row['feedback_no'],
            'matching_no': row['matching_no'] or '---',
            'customer': row['customer'] or '---',
            'prod_code': row['prod_code'] or '---',
            'color_desc': row['color_desc'] or '---',
            'finished_prod': row['finished_prod'] or '---',
            'required_date': row['required_date'] or '---',
            'due_date': row['due_date'].strftime('%m/%d/%Y') if row['due_date'] else '---',
            'type': row['matching_type'] or '---',
            'status': row['status'],
            'details': row['comment'] or '---',
            'package_details': row['storage_details'] or '---',
            'mode': row['mode'],
        }
        for row in page
    ]

    return JsonResponse({
        "draw": draw,
        "recordsTotal": total_records,
        "recordsFiltered": filtered_records,
        "data": data,
    })


def save_feedback_entry(request, feedback_no):
    """
    Handles the save/update + audit-diff logic for a single feedback
    record, validating the submitted status against the allowed set
    for this record's submitted items. Returns (success: bool, message: str).
    """
    try:
        with transaction.atomic():
            data = request.POST

            fb_instance = tbl_feedback_details.objects.select_related('cm_no', 'rs_no').filter(feedback_no=feedback_no).first()
            if not fb_instance:
                return False, "Feedback record not found."

            parent_no = fb_instance.cm_no.cm_no if fb_instance.cm_no else fb_instance.rs_no.rs_no

            # --- Validate submitted status against the allowed set for this record ---
            tracking = None
            if fb_instance.cm_no:
                tracking = tbl_cmf_pending_completed.objects.filter(cm_no=fb_instance.cm_no).first()
            elif fb_instance.rs_no:
                tracking = tbl_cmf_pending_completed.objects.filter(rs_no=fb_instance.rs_no).first()

            selected_names = _get_selected_option_names(tracking)
            allowed_statuses = get_feedback_status_choices(selected_names)

            submitted_status = data.get('feedback_status', '')
            if submitted_status and submitted_status not in allowed_statuses:
                return False, f"'{submitted_status}' is not a valid status for this record's submitted items."

            diff_logs = []
            update_map = {
                'feedback_status': ('status', 'Status'),
                'date_sample_received': ('date_sample_received', 'Sample Received Date', _parse_date),
                'comments': ('comment', 'Comments'),
                'storage_details': ('storage_details', 'Storage Details'),
            }

            for post_key, mapping in update_map.items():
                attr, label = mapping[0], mapping[1]
                transform = mapping[2] if len(mapping) > 2 else None

                old_db_val = getattr(fb_instance, attr)
                raw_new_val = data.get(post_key, '')
                new_form_val = transform(raw_new_val) if transform else raw_new_val

                curr_str = _format_val(old_db_val)
                new_str = _format_val(new_form_val)

                if curr_str != new_str:
                    diff_logs.append(f"{label} ({curr_str} -> {new_str})")
                    setattr(fb_instance, attr, new_form_val)

            if diff_logs:
                fb_instance.save()
                cache.delete(CACHE_KEY)
                log_msg = f"Feedback for {parent_no}. Changes: {', '.join(diff_logs)}"
                log_audit(request, "Updated", log_msg)
                return True, f"Feedback for {parent_no} successfully updated."
            else:
                return True, "No changes were made to the feedback."

    except Exception as e:
        return False, f"Error updating feedback: {str(e)}"