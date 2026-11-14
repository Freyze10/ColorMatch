from datetime import date, datetime
from django.db.models.functions import Lower
from django.core.cache import cache
from django.db import transaction
from django.http import JsonResponse
from django.db.models import F, Q, DateField, Value, CharField
from django.db.models.functions import Coalesce
from django.db.models.expressions import OuterRef, Subquery, Case, When
from main.services.cmf_records import cmf_records_services
from main.utils.log_audit_trail import log_audit
from main.models import (
    tbl_cmf_salesman, tbl_feedback_details, tbl_cmf_pending_completed, tbl_cmf_formula,
    tbl_cmf_dates, tbl_mb_extruder_formula, tbl_dc_extruder_formula, tbl_submitted_option,
    tbl_submitted_selected,
)

CACHE_KEY = 'feedback_records_list'

# Canonical list — every value the DB column can legally hold.
FEEDBACK_STATUS_OPTIONS = [
    'Pending',
    'Rematch',
    'Abandoned',
    'Rejected',
    'Ordered',
    'Approved with result',
    'Approved without result',
    'Request for additional samples',
    'Approved and request for samples',
]

# Always available, regardless of what was submitted.
BASE_STATUSES = ['Rematch', 'Abandoned', 'Ordered', 'Rejected']

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
    'Approved and request for samples',
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
    Fetches a single feedback record (CMF or RS) with all related context,
    submitted options, and tracking details. Returns {} if not found.
    """
    form_data = {}

    fb = (
        tbl_feedback_details.objects
        .select_related('cm_no', 'cm_no__sm', 'rs_no', 'rs_no__sm_no', 'rs_no__cm_no')
        .filter(feedback_no=feedback_no)
        .filter(Q(cm_no__isnull=False) | Q(rs_no__isnull=False))
        .first()
    )
    if not fb:
        return form_data

    cmf = fb.cm_no
    rs = fb.rs_no if not cmf else None
    is_rs = rs is not None

    # The CMF used for formula info / color / final formula (an RS can be linked to a CMF)
    ref_cmf = cmf or (rs.cm_no if rs else None)

    # 1. Fetch related records (RS has its own tracking and dates rows)
    if is_rs:
        tracking = tbl_cmf_pending_completed.objects.filter(rs_no=rs).select_related('code').first()
        dates = tbl_cmf_dates.objects.filter(rs_no=rs).first()
        if not dates and ref_cmf:
            dates = tbl_cmf_dates.objects.filter(cm_no=ref_cmf).first()
    else:
        tracking = tbl_cmf_pending_completed.objects.filter(cm_no=cmf).select_related('code').first()
        dates = tbl_cmf_dates.objects.filter(cm_no=cmf).first()

    formula = tbl_cmf_formula.objects.filter(cm_no=ref_cmf).first() if ref_cmf else None

    # 2. Resolve Product Code & Lot Number (same hierarchy as cmf_pending_completed)
    final_formula = None
    if ref_cmf:
        final_formula = tbl_mb_extruder_formula.objects.filter(cm_no=ref_cmf, is_final=True).select_related('code').first()
        if not final_formula:
            final_formula = tbl_dc_extruder_formula.objects.filter(cm_no=ref_cmf, is_final=True).select_related('code').first()

    final_prod_code = (
        final_formula.code.product_code if final_formula and final_formula.code else
        (tracking.code.product_code if tracking and tracking.code else "")
    )

    selected_lot = (
        tracking.lot_no if tracking and tracking.lot_no else
        (final_formula.lot_no if final_formula and final_formula.lot_no else "N/A")
    )

    # 3. Retrieve Submitted Options (using tbl_submitted_option and tbl_submitted_selected)
    all_options = list(tbl_submitted_option.objects.all())

    selected_option_ids = list(
        tbl_submitted_selected.objects.filter(completed_id=tracking).values_list('option_id', flat=True)
    ) if tracking else []

    selected_names = list(
        tbl_submitted_selected.objects.filter(completed_id=tracking).values_list('option_id__name', flat=True)
    ) if tracking else []

    # 4. Header values: CMF or RS
    if is_rs:
        matching_no = rs.rs_no or ''
        customer = rs.customer or (formula.customer if formula else '')
        sales_person = rs.sm_no.name if rs.sm_no else ''
    else:
        matching_no = cmf.cm_no
        customer = formula.customer if formula else ''
        sales_person = cmf.sm.name if cmf.sm else ''

    color_desc = (ref_cmf.color_desc if ref_cmf else '') or ''

    # 5. Build complete form_data
    form_data = {
        'feedback_no': fb.feedback_no,
        'matching_no': matching_no,
        'customer': customer,
        'date_created': dates.form_made.strftime('%m/%d/%Y') if dates and dates.form_made else '',
        'required_date': dates.date_required if dates else '',
        'date_received': dates.date_received_lab if dates else '',
        'due_date': dates.due_date_lab.strftime('%m/%d/%Y') if dates and dates.due_date_lab else '',
        'finished_product': formula.finished_product if formula else '',
        'color_description': color_desc,
        'sales_person': sales_person,
        'product_code': final_prod_code,

        # Right Column tracking & feedback details
        'current_status': 'Completed' if (tracking and tracking.is_completed) else 'Pending',
        'pending_reason': tracking.reason if tracking else '',
        'code_description': tracking.code_details if tracking else color_desc,
        'lot_no': selected_lot,
        'quantity_kg': fb.quantity_given if fb.quantity_given is not None else '',
        'set_pc': fb.pieces if fb.pieces is not None else '',
        'date_submitted': tracking.date_submitted.strftime('%m/%d/%Y') if tracking and tracking.date_submitted else '',
        'ar_number': tracking.ar_no if tracking else '',
        'ar_date': tracking.ar_date.strftime('%m/%d/%Y') if tracking and tracking.ar_date else '',

        # Submitted options context for checkboxes & conditional visibility
        'submitted_options': all_options,
        'selected_option_ids': selected_option_ids,
        'has_sample': any('sample' in n.lower() for n in selected_names),
        'has_chips': any('chip' in n.lower() for n in selected_names),
        'has_price': any('price' in n.lower() for n in selected_names),
        'submitted_str': ", ".join(selected_names),

        "salesman": cmf_records_services.get_salesman_list(),
        'submitted_by_id': fb.submitted_by_id,

        # Feedback specific editable fields
        'record_type': 'rs' if is_rs else 'cmf',
        'feedback_status': fb.status or 'Pending',
        'abandoned_reason': fb.abandoned_reason or '',
        'order_form_no': fb.order_form_no or '',
        'date_sample_received': fb.date_sample_received.strftime('%m/%d/%Y') if fb.date_sample_received else '',
        'comments': fb.comment or '',
        'storage_details': fb.storage_details or '',
    }

    # RS records under the same CMF that have no feedback status yet (used by the Save question)
    form_data['pending_rs'] = [
        (r.rs_no.rs_no or f"RS #{r.rs_no_id}") for r in _get_pending_rs_feedback(cmf, exclude_pk=fb.pk)
    ] if (cmf and not is_rs) else []

    # 6. Compute the allowed status choices for this record
    form_data['status_choices'] = get_feedback_status_choices(selected_names)

    return form_data


def get_feedback_queryset():
    """
    Base queryset for Feedback Records: CMF records and RS records.
    Each value is read from the CMF side first, then from the RS side.
    An RS that is linked to a CMF also uses that CMF for color, finished product and final formula.
    """
    # Final formula codes: by the feedback's CMF, or by the CMF linked to its RS
    mb_final_code = tbl_mb_extruder_formula.objects.filter(
        cm_no=OuterRef('cm_no'), is_final=True
    ).values('code__product_code')[:1]
    dc_final_code = tbl_dc_extruder_formula.objects.filter(
        cm_no=OuterRef('cm_no'), is_final=True
    ).values('code__product_code')[:1]
    rs_mb_final_code = tbl_mb_extruder_formula.objects.filter(
        cm_no=OuterRef('rs_no__cm_no'), is_final=True
    ).values('code__product_code')[:1]
    rs_dc_final_code = tbl_dc_extruder_formula.objects.filter(
        cm_no=OuterRef('rs_no__cm_no'), is_final=True
    ).values('code__product_code')[:1]

    cmf_formula = tbl_cmf_formula.objects.filter(cm_no=OuterRef('cm_no'))
    rs_cmf_formula = tbl_cmf_formula.objects.filter(cm_no=OuterRef('rs_no__cm_no'))

    cmf_dates = tbl_cmf_dates.objects.filter(cm_no=OuterRef('cm_no'))
    rs_dates = tbl_cmf_dates.objects.filter(rs_no=OuterRef('rs_no'))

    cmf_pending = tbl_cmf_pending_completed.objects.filter(cm_no=OuterRef('cm_no'))
    rs_pending = tbl_cmf_pending_completed.objects.filter(rs_no=OuterRef('rs_no'))

    return (
        tbl_feedback_details.objects.filter(Q(cm_no__isnull=False) | Q(rs_no__isnull=False))
        .select_related('cm_no', 'rs_no', 'code')
        .annotate(
            matching_no=Coalesce(F('cm_no__cm_no'), F('rs_no__rs_no'), output_field=CharField()),
            customer=Coalesce(
                Subquery(cmf_formula.values('customer')[:1], output_field=CharField()),
                F('rs_no__customer'),
                output_field=CharField(),
            ),
            color_desc=Coalesce(
                F('cm_no__color_desc'), F('rs_no__cm_no__color_desc'),
                output_field=CharField(),
            ),
            finished_prod=Coalesce(
                Subquery(cmf_formula.values('finished_product')[:1], output_field=CharField()),
                Subquery(rs_cmf_formula.values('finished_product')[:1], output_field=CharField()),
                output_field=CharField(),
            ),
            # RS records show "RS" in the Type column
            matching_type=Coalesce(F('cm_no__matching_type'), Value('RS'), output_field=CharField()),
            required_date=Coalesce(
                Subquery(cmf_dates.values('date_required')[:1], output_field=CharField()),
                Subquery(rs_dates.values('date_required')[:1], output_field=CharField()),
                output_field=CharField(),
            ),
            due_date=Coalesce(
                Subquery(cmf_dates.values('due_date_lab')[:1], output_field=DateField()),
                Subquery(rs_dates.values('due_date_lab')[:1], output_field=DateField()),
                output_field=DateField(),
            ),
            date_submitted=Coalesce(
                Subquery(cmf_pending.values('date_submitted')[:1], output_field=DateField()),
                Subquery(rs_pending.values('date_submitted')[:1], output_field=DateField()),
                output_field=DateField(),
            ),
            ar_no=Coalesce(
                Subquery(cmf_pending.values('ar_no')[:1], output_field=CharField()),
                Subquery(rs_pending.values('ar_no')[:1], output_field=CharField()),
                output_field=CharField(),
            ),
            prod_code=Coalesce(
                Subquery(mb_final_code, output_field=CharField()),
                Subquery(dc_final_code, output_field=CharField()),
                Subquery(rs_mb_final_code, output_field=CharField()),
                Subquery(rs_dc_final_code, output_field=CharField()),
                'code__product_code',
                output_field=CharField(),
            ),
            mode=Case(
                When(cm_no__isnull=False, then=Value('cmf')),
                default=Value('rs'),
                output_field=CharField(),
            ),
        )
    )

COLUMN_FIELD_MAP = {
    'Matching No.': 'matching_no',
    'Customer': 'customer',
    'Product Code': 'prod_code',
    'Color Description': 'color_desc',
    'Finished Product': 'finished_prod',
    'Type': 'matching_type',
    'AR No.': 'ar_no',
    'Status': 'status',
}

# 0-based indices strictly matching the new 12-column table order
ORDER_COLUMN_MAP = {
    '0': 'matching_no',
    '1': 'customer',
    '2': 'prod_code',
    '3': 'color_desc',
    '4': 'finished_prod',
    '5': 'matching_type',
    '6': 'required_date',
    '7': 'due_date',
    '8': 'date_submitted',
    '9': 'ar_no',
    '10': 'status',
    '11': 'comment',
}

def format_date_safe(val):
    if not val:
        return '---'
    if isinstance(val, (datetime, date)):
        return val.strftime('%m/%d/%Y')
    try:
        return datetime.strptime(str(val).split('T')[0], '%Y-%m-%d').strftime('%m/%d/%Y')
    except Exception:
        return str(val)

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
                Q(ar_no__icontains=search_value) |
                Q(status__icontains=search_value) |
                Q(comment__icontains=search_value)
            )

    filtered_records = queryset.count()

    order_col = request.GET.get('order[0][column]')
    order_dir = request.GET.get('order[0][dir]', 'asc')
    if order_col is not None and order_col in ORDER_COLUMN_MAP:
        sort_field = ORDER_COLUMN_MAP[order_col]
        queryset = queryset.order_by(f"{'-' if order_dir == 'desc' else ''}{sort_field}")
    else:
        queryset = queryset.order_by('-feedback_no')

    page = queryset[start:start + length].values(
        'feedback_no', 'matching_no', 'customer', 'prod_code', 'color_desc',
        'finished_prod', 'matching_type', 'required_date', 'due_date',
        'date_submitted', 'ar_no', 'status', 'comment', 'mode',
    )

    data = [
        {
            'feedback_no': row['feedback_no'],
            'matching_no': row['matching_no'] or '---',
            'customer': row['customer'] or '---',
            'prod_code': row['prod_code'] or '---',
            'color_desc': row['color_desc'] or '---',
            'finished_prod': row['finished_prod'] or '---',
            'type': row['matching_type'] or '---',
            'required_date': row['required_date'] or '---',
            'due_date': format_date_safe(row['due_date']),
            'date_submitted': format_date_safe(row['date_submitted']),
            'ar_no': row['ar_no'] or '---',
            'status': row['status'] or '---',
            'details': row['comment'] or '---',
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

# Statuses that mean "no feedback yet" (the default is 'waiting for result')
NO_FEEDBACK_STATUSES = ['pending', 'waiting for result']


def _get_pending_rs_feedback(cmf, exclude_pk=None):
    """RS feedback rows linked to this CMF that have no feedback status yet."""
    qs = (
        tbl_feedback_details.objects
        .filter(rs_no__cm_no=cmf)
        .annotate(status_lc=Lower('status'))
        .filter(Q(status__isnull=True) | Q(status='') | Q(status_lc__in=NO_FEEDBACK_STATUSES))
        .select_related('rs_no')
        .order_by('rs_no__rs_no')
    )
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    return list(qs)

def _apply_to_rs_feedback(source_fb):
    """
    Copies the saved CMF feedback to the RS records under the same CMF that have no status yet.
    An RS is skipped when the status isn't allowed for its own submitted items (Sample / Chips / Price).
    Returns (updated_rs_numbers, skipped_rs_numbers).
    """
    updated, skipped = [], []
    for rs_fb in _get_pending_rs_feedback(source_fb.cm_no, exclude_pk=source_fb.pk):
        label = rs_fb.rs_no.rs_no or f"RS #{rs_fb.rs_no_id}"

        tracking = tbl_cmf_pending_completed.objects.filter(rs_no=rs_fb.rs_no).first()
        allowed = get_feedback_status_choices(_get_selected_option_names(tracking))
        if source_fb.status not in allowed:
            skipped.append(label)
            continue

        rs_fb.status = source_fb.status
        rs_fb.abandoned_reason = source_fb.abandoned_reason
        rs_fb.order_form_no = source_fb.order_form_no
        rs_fb.date_sample_received = source_fb.date_sample_received
        rs_fb.comment = source_fb.comment
        rs_fb.storage_details = source_fb.storage_details
        rs_fb.submitted_by_id = source_fb.submitted_by_id
        rs_fb.save()
        updated.append(label)

    return updated, skipped

def save_feedback_entry(request, feedback_no):
    try:
        with transaction.atomic():
            data = request.POST

            fb_instance = (
                tbl_feedback_details.objects
                .select_related('cm_no', 'rs_no', 'submitted_by')
                .filter(feedback_no=feedback_no)
                .first()
            )
            if not fb_instance:
                return False, "Feedback record not found."

            parent_no = fb_instance.cm_no.cm_no if fb_instance.cm_no else (fb_instance.rs_no.rs_no if fb_instance.rs_no else "N/A")

            # --- Validation for status ---
            tracking = None
            if fb_instance.cm_no:
                tracking = tbl_cmf_pending_completed.objects.filter(cm_no=fb_instance.cm_no).first()
            elif fb_instance.rs_no:
                tracking = tbl_cmf_pending_completed.objects.filter(rs_no=fb_instance.rs_no).first()

            selected_names = _get_selected_option_names(tracking)
            allowed_statuses = get_feedback_status_choices(selected_names)

            submitted_status = data.get('feedback_status', '').strip()
            if submitted_status and submitted_status not in allowed_statuses:
                return False, f"'{submitted_status}' is not a valid status for this record's submitted items."

            status_clean = submitted_status.lower()

            # --- Foreign Key: Submitted By (sm_no) ---
            submitted_by_raw = data.get('submitted_by', '').strip()
            if not submitted_by_raw:
                return False, "Please select who submitted this feedback."

            try:
                new_sm_id = int(submitted_by_raw)
            except (ValueError, TypeError):
                return False, "Invalid sales person selected."

            # --- Conditional Fields Validation & Clean ---
            abandoned_reason = data.get('abandoned_reason', '').strip()
            if status_clean == 'abandoned' and not abandoned_reason:
                return False, "Please provide the reason why matching was abandoned."

            order_form_no = data.get('order_form_no', '').strip()
            if status_clean == 'ordered' and not order_form_no:
                return False, "Please provide the Order Form No."

            clean_abandoned_reason = abandoned_reason if status_clean == 'abandoned' else None
            clean_order_form_no = order_form_no if status_clean == 'ordered' else None

            diff_logs = []

            # 1. Audit diff for Submitted By (Names instead of raw IDs)
            old_sm_id = fb_instance.submitted_by_id
            if old_sm_id != new_sm_id:
                old_name = fb_instance.submitted_by.name if fb_instance.submitted_by else "None"
                new_sm_obj = tbl_cmf_salesman.objects.filter(sm_no=new_sm_id).first()
                new_name = new_sm_obj.name if new_sm_obj else "None"
                diff_logs.append(f"Submitted By ({old_name} -> {new_name})")
                fb_instance.submitted_by_id = new_sm_id

            # 2. Standard field diffs
            update_map = {
                'feedback_status': ('status', 'Status', lambda v: v.strip() if v else None),
                'abandoned_reason': ('abandoned_reason', 'Abandoned Reason', lambda _: clean_abandoned_reason),
                'order_form_no': ('order_form_no', 'Order Form No', lambda _: clean_order_form_no),
                'date_sample_received': ('date_sample_received', 'Sample Received Date', _parse_date),
                'comments': ('comment', 'Comments', lambda v: v.strip() if v else None),
                'storage_details': ('storage_details', 'Storage Details', lambda v: v.strip() if v else None),
            }

            for post_key, mapping in update_map.items():
                attr, label = mapping[0], mapping[1]
                transform = mapping[2] if len(mapping) > 2 else None

                old_db_val = getattr(fb_instance, attr)
                raw_new_val = data.get(post_key, '')
                new_form_val = transform(raw_new_val) if transform else (raw_new_val.strip() if isinstance(raw_new_val, str) else raw_new_val)

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

            # --- RS: also apply to the RS records under the same CMF that have no status yet ---
            rs_updated, rs_skipped = [], []
            apply_to_rs = (
                data.get('update_rs') == '1'
                and fb_instance.cm_no_id is not None
                and status_clean not in ('', 'pending')
            )
            if apply_to_rs:
                rs_updated, rs_skipped = _apply_to_rs_feedback(fb_instance)
                if rs_updated:
                    cache.delete(CACHE_KEY)
                    log_audit(
                        request, "Updated",
                        f"Feedback of CMF {parent_no} also applied to RS: {', '.join(rs_updated)} "
                        f"(Status: {fb_instance.status})"
                    )

            # --- Result message ---
            if not diff_logs and not rs_updated:
                msg = "No changes were made to the feedback."
            else:
                msg = f"Feedback for {parent_no} successfully updated."
                if rs_updated:
                    msg += f" Also applied to RS: {', '.join(rs_updated)}."
            if rs_skipped:
                msg += f" Skipped (status not allowed for their submitted items): {', '.join(rs_skipped)}."
            return True, msg

    except Exception as e:
        return False, f"Error updating feedback: {str(e)}"