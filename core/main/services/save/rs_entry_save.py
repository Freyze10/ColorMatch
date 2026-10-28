import re
import json
from django.db import transaction
from django.core.cache import cache
from django.contrib.auth import get_user_model
from datetime import datetime, date
from main.services.save.utils import to_bool, format_date, clean_numeric
from main.models import (
    tbl_cmf, tbl_cmf_dates, tbl_feedback_details, tbl_cmf_color_req, tbl_cmf_pending_completed, 
    tbl_cmf_process, tbl_cmf_process02, tbl_cmf_salesman, tbl_resin, 
    tbl_resins_selected, tbl_rs, tbl_generated_prod_code
)
from main.utils.log_audit_trail import log_audit

User = get_user_model()

# --- 1. AUDIT & UTILITY HELPERS ---

def format_val(val):
    """Standardizes values to readable strings for audit comparison."""
    if val is True or str(val).lower() == 'true': return "Yes"
    if val is False or str(val).lower() == 'false': return "No"
    if val is None or val == "" or val == "None": return "---"
    
    # Handle Date/Datetime objects from Database
    if isinstance(val, (date, datetime)):
        return val.strftime('%m/%d/%Y')
    
    # Handle ISO Date strings from POST (YYYY-MM-DD -> MM/DD/YYYY)
    val_str = str(val).strip()
    if re.match(r'^\d{4}-\d{2}-\d{2}$', val_str):
        try:
            return datetime.strptime(val_str, '%Y-%m-%d').strftime('%m/%d/%Y')
        except Exception:
            pass
            
    return val_str

def get_rs_pretty_name(field):
    """Maps database field names to readable labels for the audit log."""
    mapping = {
        'rs_no': 'RS No.',
        'cm_no': 'CMF No.',
        'customer': 'Customer',
        'quantity_required': 'Qty required',
        'sm_no': 'Salesman',
        'approved_by': 'Approved By',
        'form_made': 'Date Created',
        'date_required': 'Req. Date',
        'date_received_lab': 'Date Received',
        'due_date_lab': 'Due Date',
    }
    return mapping.get(field, field.replace('_', ' ').title())

def _extract_rs_data(request):
    """Extracts and cleans raw POST data for RS processing."""
    data = request.POST
    return {
        "rs_no": (data.get('rs_no') or '').strip(),
        "cm_no": (data.get('cm_no') or '').strip(),
        "customer": (data.get('customer') or '').strip(),
        "salesman": (data.get('salesman') or '').strip(),
        "quantity_required": clean_numeric(data.get('quantity_kg')),
        "approved_by_id": data.get('approved_by'),
        "date_form_made": format_date(data.get('date_created')),
        "date_lab_received": data.get('date_received'),
        "date_required": data.get('required_date'),
        "due_date": format_date(data.get('due_date')),
    }

# --- 2. MAIN LOGIC FUNCTIONS ---

def save_rs_complete_entry(request):
    """Creates a new RS entry."""
    with transaction.atomic():
        data = _extract_rs_data(request)

        # 1. Resolve Foreign Keys
        salesman_obj = tbl_cmf_salesman.objects.filter(name=data["salesman"]).first()
        if not salesman_obj and data["salesman"]:
            raise Exception(f"Salesman Error: '{data['salesman']}' is not registered.")

        cmf_obj = None
        if data["cm_no"]:
            cmf_obj = tbl_cmf.objects.filter(cm_no=data["cm_no"]).first()
            if not cmf_obj:
                raise Exception(f"CMF Error: CMF '{data['cm_no']}' not found.")

        approved_by_obj = None
        if data["approved_by_id"]:
            approved_by_obj = User.objects.filter(id=data["approved_by_id"]).first()

        # 2. Create RS Header Record
        rs_obj = tbl_rs.objects.create(
            rs_no=data["rs_no"],
            cm_no=cmf_obj,
            customer=data["customer"],
            quantity_required=data["quantity_required"],
            sm_no=salesman_obj,
            approved_by=approved_by_obj,
            user=request.user
        )
        
        # 3. Create Schedule Dates Record
        tbl_cmf_dates.objects.create(
            rs_no=rs_obj,
            form_made=data["date_form_made"],
            date_received_lab=data["date_lab_received"],
            date_required=data["date_required"],
            due_date_lab=data["due_date"],
        )

        # 4. Create Tracking Entry: code is kept NULL for RS creation
        tbl_cmf_pending_completed.objects.create(
            rs_no=rs_obj,
            code=None,  # <--- Kept NULL as requested
            is_completed=False
        )

        # 5. Create Feedback Details row
        tbl_feedback_details.objects.create(
            rs_no=rs_obj
        )

        log_audit(request, "Saved", f"New RS Entry: {rs_obj.rs_no}")
        cache.delete('rs_records_list')

    return rs_obj

def update_rs_complete_entry(request, original_rs_id):
    """Updates an existing RS entry with detailed technical audit trail."""
    diff_logs = []

    with transaction.atomic():
        rs_instance = tbl_rs.objects.filter(id=original_rs_id).select_related('sm_no', 'cm_no', 'approved_by').first()
        if not rs_instance:
            raise Exception(f"RS record (id={original_rs_id}) was not found.")

        extracted = _extract_rs_data(request)
        
        salesman_obj = tbl_cmf_salesman.objects.filter(name=extracted["salesman"]).first()
        cmf_obj = tbl_cmf.objects.filter(cm_no=extracted["cm_no"]).first() if extracted["cm_no"] else None
        approved_by_obj = User.objects.filter(id=extracted["approved_by_id"]).first() if extracted["approved_by_id"] else None

        # --- A. TRACK HEADER CHANGES ---
        header_map = {
            'rs_no': extracted["rs_no"],
            'cm_no': cmf_obj,
            'customer': extracted["customer"],
            'quantity_required': extracted["quantity_required"],
            'sm_no': salesman_obj,
            'approved_by': approved_by_obj,
        }

        for field, new_val in header_map.items():
            current_val = getattr(rs_instance, field)

            # Format related objects for clear audit reading
            if field == 'sm_no':
                curr_str = current_val.name if current_val else "---"
                new_str = new_val.name if new_val else "---"
            elif field == 'cm_no':
                curr_str = current_val.cm_no if current_val else "---"
                new_str = new_val.cm_no if new_val else "---"
            elif field == 'approved_by':
                curr_str = f"{current_val.first_name} {current_val.last_name}".strip() if current_val else "---"
                new_str = f"{new_val.first_name} {new_val.last_name}".strip() if new_val else "---"
            elif field == 'quantity_required':
                curr_str = str(float(current_val or 0))
                new_str = str(float(new_val or 0))
            else:
                curr_str = format_val(current_val)
                new_str = format_val(new_val)

            if curr_str != new_str:
                diff_logs.append(f"{get_rs_pretty_name(field)} ({curr_str} -> {new_str})")

        # --- B. TRACK DATES ---
        old_dates_obj = tbl_cmf_dates.objects.filter(rs_no=rs_instance).first()
        date_updates = {
            'form_made': extracted["date_form_made"],
            'date_required': extracted["date_required"],
            'date_received_lab': extracted["date_lab_received"],
            'due_date_lab': extracted["due_date"],
        }
        if old_dates_obj:
            for d_field, d_new in date_updates.items():
                d_old = getattr(old_dates_obj, d_field)
                if format_val(d_old) != format_val(d_new):
                    diff_logs.append(f"{get_rs_pretty_name(d_field)} ({format_val(d_old)} -> {format_val(d_new)})")

        # --- C. COMMIT UPDATES TO DATABASE ---
        for field, val in header_map.items(): 
            setattr(rs_instance, field, val)
        rs_instance.save()

        # Update dates
        if old_dates_obj:
            tbl_cmf_dates.objects.filter(rs_no=rs_instance).update(**date_updates)
        else:
            tbl_cmf_dates.objects.create(rs_no=rs_instance, **date_updates)

        # --- D. LOGGING ---
        log_msg = f"RS Entry: {rs_instance.rs_no}"
        if diff_logs:
            log_msg += ". Changes: " + (", ".join(diff_logs))
        else:
            log_msg += ". No technical fields modified."

        log_audit(request, "Updated", log_msg)
        cache.delete('rs_records_list')

    return rs_instance


def build_form_data(rs_instance):
    dates = tbl_cmf_dates.objects.filter(rs_no=rs_instance).first()

    # Look up Product Code
    pending = tbl_cmf_pending_completed.objects.filter(rs_no=rs_instance).select_related('code').first()
    if not (pending and pending.code) and rs_instance.cm_no:
        pending = tbl_cmf_pending_completed.objects.filter(cm_no=rs_instance.cm_no).select_related('code').first()
    product_code = pending.code.product_code if (pending and pending.code) else ''

    # --- GET FULL NAME INSTEAD OF ID ---
    approved_by_name = ""
    if rs_instance.approved_by:
        full_name = f"{rs_instance.approved_by.first_name} {rs_instance.approved_by.last_name}".strip()
        approved_by_name = full_name if full_name else rs_instance.approved_by.username

    return {
        'original_rs_id': rs_instance.id,
        'rs_no': rs_instance.rs_no or '',
        'cm_no': rs_instance.cm_no.cm_no if rs_instance.cm_no else '',
        'product_code': product_code,
        'customer': rs_instance.customer or '',
        'salesman': rs_instance.sm_no.name if rs_instance.sm_no else '',
        'quantity_kg': rs_instance.quantity_required or '',

        # Full Name for display:
        'approved_by': approved_by_name,
        # Keep ID available if you still have an edit dropdown:
        'approved_by_id': rs_instance.approved_by_id or '',

        # Dates
        'date_created': dates.form_made.strftime('%m/%d/%Y') if (dates and dates.form_made) else '',
        'required_date': dates.date_required if dates else '',
        'date_received': dates.date_received_lab if dates else '',
        'due_date': dates.due_date_lab.strftime('%m/%d/%Y') if (dates and dates.due_date_lab) else '',
    }