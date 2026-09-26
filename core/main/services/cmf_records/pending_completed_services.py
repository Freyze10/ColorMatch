from datetime import datetime, date
from decimal import Decimal
from django.db import transaction
from django.db.models import Q
from django.core.cache import cache
from django.contrib import messages

# Adjust these imports to match your project's model/audit paths
from main.models import (
    tbl_cmf,
    tbl_rs,
    tbl_cmf_pending_completed,
    tbl_feedback_details,
    tbl_generated_prod_code,
    tbl_submitted_option,
    tbl_submitted_selected
)

# --- HELPERS ---
def format_val(val):
    """Standardizes values for audit comparison."""
    if val is True: return "Completed"
    if val is False: return "Pending"
    if val is None or val == "" or val == "None": return "---"
    if isinstance(val, (date, datetime)):
        return val.strftime('%m/%d/%Y')
    if isinstance(val, (Decimal, float)):
        return format(float(val), ".2f")
    return str(val).strip()

def parse_date(d_str):
    if not d_str: return None
    try: return datetime.strptime(d_str.strip(), '%m/%d/%Y').date()
    except ValueError: return None

def get_prod_code_obj(code_str):
    if not code_str or not code_str.strip(): return None
    obj, _ = tbl_generated_prod_code.objects.get_or_create(product_code=code_str.strip())
    return obj

def save_pending_completed_entry(request, log_audit):
    """
    Handles saving and updating tracking and feedback for CMF and RS records.
    Cascades completed tracking to linked tbl_rs when updating a previously uncompleted CMF.
    """
    data = request.POST
    record_no = data.get('record_no') or request.GET.get('no')
    record_type = data.get('record_type') or request.GET.get('type', 'cmf')

    data = request.POST
    diff_logs = []
    tracking_instance = None
    feedback_instance = None
    parent_display = ""
    has_rs_code_cleared = False
    cmf_was_completed = False  # Flag to store CMF status before update

    try:
        # 1. Identify Parent and Get/Create Instances
        if record_type == 'cmf':
            cmf_obj = tbl_cmf.objects.filter(cm_no=record_no).first()
            if not cmf_obj: raise Exception(f"CMF {record_no} not found.")
            tracking_instance, _ = tbl_cmf_pending_completed.objects.get_or_create(cm_no=cmf_obj)
            feedback_instance, _ = tbl_feedback_details.objects.get_or_create(cm_no=cmf_obj)
            parent_display = f"CMF: {record_no}"

            # STEP A: Check if this CMF tracking record was ALREADY completed before updating
            cmf_was_completed = bool(tracking_instance.is_completed)
        else:
            rs_obj = tbl_rs.objects.filter(pk=record_no).first() if str(record_no).isdigit() else tbl_rs.objects.filter(rs_no=record_no).first()
            if not rs_obj: raise Exception("RS record not found.")
            tracking_instance, _ = tbl_cmf_pending_completed.objects.get_or_create(rs_no=rs_obj, defaults={'code': None})
            feedback_instance, _ = tbl_feedback_details.objects.get_or_create(rs_no=rs_obj, defaults={'code': None})
            parent_display = f"RS: {rs_obj.rs_no}"

        # 2. Update Map for Tracking Table (Shared fields)
        update_map = {
            'status': (tracking_instance, 'is_completed', 'Status', lambda x: x == 'Completed'),
            'pending_reason': (tracking_instance, 'reason', 'Reason', str),
            'lot_no': (tracking_instance, 'lot_no', 'Lot Number', str),
            'date_submitted': (tracking_instance, 'date_submitted', 'Date Submitted', parse_date),
            'ar_no': (tracking_instance, 'ar_no', 'AR No.', str),
            'ar_date': (tracking_instance, 'ar_date', 'AR Date', parse_date),
        }

        # Product Code & Code Description apply ONLY to CMF
        if record_type == 'cmf':
            update_map['product_code'] = (tracking_instance, 'code', 'Product Code', get_prod_code_obj)
            if 'code_description' in data:
                update_map['code_description'] = (tracking_instance, 'code_details', 'Code Details', str)
        else:
            # FOR RS: Strictly ensure code is null in both tracking and feedback
            if tracking_instance.code is not None:
                tracking_instance.code = None
                has_rs_code_cleared = True
            if feedback_instance.code is not None:
                feedback_instance.code = None
                has_rs_code_cleared = True

        # 3. Update Map for Feedback Table
        feedback_map = {
            'qty_given': (feedback_instance, 'quantity_given', 'Qty Given', lambda x: Decimal(x) if x else None),
            'set_pc': (feedback_instance, 'pieces', 'Sets/Pcs', lambda x: int(x) if x else None),
        }

        with transaction.atomic():
            # Process Tracking Diffs
            for post_key, (inst, attr, label, transform) in update_map.items():
                if post_key not in data:
                    continue
                current_val = getattr(inst, attr)
                new_val = transform(data.get(post_key, ''))
                
                curr_str = format_val(current_val.product_code if attr == 'code' and current_val else current_val)
                new_str = format_val(new_val.product_code if attr == 'code' and new_val else new_val)

                if curr_str != new_str:
                    diff_logs.append(f"{label} ({curr_str} -> {new_str})")
                    setattr(inst, attr, new_val)

            # Process Feedback Diffs
            for post_key, (inst, attr, label, transform) in feedback_map.items():
                if post_key not in data:
                    continue
                current_val = getattr(inst, attr)
                new_val = transform(data.get(post_key, ''))
                
                curr_str, new_str = format_val(current_val), format_val(new_val)
                if curr_str != new_str:
                    diff_logs.append(f"{label} ({curr_str} -> {new_str})")
                    setattr(inst, attr, new_val)

            # Sync Code FK to Feedback (CMF ONLY)
            if record_type == 'cmf' and feedback_instance.code != tracking_instance.code:
                feedback_instance.code = tracking_instance.code

            # Save if there are changes or if RS code was cleared
            if diff_logs or has_rs_code_cleared:
                tracking_instance.save()
                feedback_instance.save()

            # --- 4. Sync Submitted Options (Sample/Chips/Price) for the current record ---
            if tracking_instance.pk is None:
                tracking_instance.save()

            submitted_ids = set(int(i) for i in data.getlist('submitted_options') if i.isdigit())
            existing_ids = set(
                tbl_submitted_selected.objects
                .filter(completed_id=tracking_instance)
                .values_list('option_id', flat=True)
            )

            if submitted_ids != existing_ids:
                to_add = submitted_ids - existing_ids
                to_remove = existing_ids - submitted_ids

                if to_remove:
                    tbl_submitted_selected.objects.filter(
                        completed_id=tracking_instance, option_id__in=to_remove
                    ).delete()

                if to_add:
                    option_objs = tbl_submitted_option.objects.filter(option_id__in=to_add)
                    for option_obj in option_objs:
                        tbl_submitted_selected.objects.get_or_create(
                            completed_id=tracking_instance, option_id=option_obj
                        )

                old_names = list(
                    tbl_submitted_option.objects.filter(option_id__in=existing_ids).values_list('name', flat=True)
                )
                new_names = list(
                    tbl_submitted_option.objects.filter(option_id__in=submitted_ids).values_list('name', flat=True)
                )
                diff_logs.append(
                    f"Submitted ({', '.join(old_names) or '---'} -> {', '.join(new_names) or '---'})"
                )

            # =====================================================================
            # 5. CMF -> RS CASCADE SYNC
            # Scenario:
            # If updating a CMF and it was NOT completed previously (cmf_was_completed is False):
            # Check if this CMF is linked to any RS in tbl_rs.
            # If linked, update that RS's pending/completed and feedback records too.
            # Submitted options for RS will ONLY include Sample and Chips (Price excluded).
            # =====================================================================
            if record_type == 'cmf' and not cmf_was_completed:
                linked_rs_records = tbl_rs.objects.filter(cm_no=cmf_obj)

                if linked_rs_records.exists():
                    # Allowed option IDs for RS: strictly Sample and Chips
                    rs_allowed_ids = set(
                        tbl_submitted_option.objects.filter(
                            Q(name__iexact='sample') | Q(name__iexact='chips')
                        ).values_list('option_id', flat=True)
                    )
                    # Filter submitted options from POST to only include Sample / Chips
                    target_rs_submitted_ids = submitted_ids.intersection(rs_allowed_ids)

                    for linked_rs in linked_rs_records:
                        # 5.1 Get or create tracking and feedback for the linked RS
                        rs_tracking, _ = tbl_cmf_pending_completed.objects.get_or_create(
                            rs_no=linked_rs, defaults={'code': None}
                        )
                        rs_feedback, _ = tbl_feedback_details.objects.get_or_create(
                            rs_no=linked_rs, defaults={'code': None}
                        )

                        # 5.2 Copy tracking fields from CMF to RS (code stays None for RS)
                        rs_tracking.is_completed = tracking_instance.is_completed
                        rs_tracking.reason = tracking_instance.reason
                        rs_tracking.lot_no = tracking_instance.lot_no
                        rs_tracking.date_submitted = tracking_instance.date_submitted
                        rs_tracking.ar_no = tracking_instance.ar_no
                        rs_tracking.ar_date = tracking_instance.ar_date
                        rs_tracking.code = None  # RS never stores product code
                        rs_tracking.save()

                        # 5.3 Copy feedback fields from CMF to RS
                        rs_feedback.quantity_given = feedback_instance.quantity_given
                        rs_feedback.pieces = feedback_instance.pieces
                        rs_feedback.code = None  # RS never stores product code
                        rs_feedback.save()

                        # 5.4 Sync submitted options for RS (Sample / Chips ONLY)
                        existing_rs_opt_ids = set(
                            tbl_submitted_selected.objects
                            .filter(completed_id=rs_tracking)
                            .values_list('option_id', flat=True)
                        )

                        if existing_rs_opt_ids != target_rs_submitted_ids:
                            rs_to_remove = existing_rs_opt_ids - target_rs_submitted_ids
                            rs_to_add = target_rs_submitted_ids - existing_rs_opt_ids

                            if rs_to_remove:
                                tbl_submitted_selected.objects.filter(
                                    completed_id=rs_tracking, option_id__in=rs_to_remove
                                ).delete()

                            if rs_to_add:
                                for opt_obj in tbl_submitted_option.objects.filter(option_id__in=rs_to_add):
                                    tbl_submitted_selected.objects.get_or_create(
                                        completed_id=rs_tracking, option_id=opt_obj
                                    )

                    diff_logs.append(
                        f"Cascaded tracking to linked RS ({', '.join(r.rs_no for r in linked_rs_records)})"
                    )

            # Audit trail and feedback messages
            if diff_logs or has_rs_code_cleared:
                log_audit(request, "Updated", f"Updated Status for {parent_display}. Changes: {', '.join(diff_logs)}")
                messages.success(request, f"Successfully updated tracking for {parent_display}")
                cache.delete('cmf_records_list')
                cache.delete('rs_records_list')
            else:
                messages.info(request, "No changes detected.")
    except Exception as e:
        messages.error(request, f"Error updating record: {str(e)}")