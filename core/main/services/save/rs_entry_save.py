import re
import json
from django.db import transaction
from django.core.cache import cache
from datetime import datetime, date
from main.services.save.utils import to_bool, format_date, clean_numeric
from main.models import (
    tbl_cmf_dates, tbl_feedback_details, tbl_cmf_color_req, tbl_cmf_pending_completed, 
    tbl_cmf_process, tbl_cmf_process02, tbl_cmf_salesman, tbl_resin, 
    tbl_resins_selected, tbl_rs, tbl_generated_prod_code
)
from main.utils.log_audit_trail import log_audit

# --- 1. AUDIT & UTILITY HELPERS ---

def _get_prod_code_obj(code_str):
    """Helper to resolve the product code string into a database object."""
    if not code_str or not code_str.strip():
        return None
    code_obj, _ = tbl_generated_prod_code.objects.get_or_create(
        product_code=code_str.strip()
    )
    return code_obj

def format_val(val):
    """Standardizes values to readable strings for audit comparison."""
    if val is True or str(val).lower() == 'true': return "Yes"
    if val is False or str(val).lower() == 'false': return "No"
    if val is None or val == "" or val == "None": return "---"
    
    # Handle Date/Datetime objects from Database (format to match UI input)
    if isinstance(val, (date, datetime)):
        return val.strftime('%m/%d/%Y')
    
    # Handle ISO Date strings from POST (YYYY-MM-DD -> MM/DD/YYYY)
    val_str = str(val).strip()
    if re.match(r'^\d{4}-\d{2}-\d{2}$', val_str):
        try:
            return datetime.strptime(val_str, '%Y-%m-%d').strftime('%m/%d/%Y')
        except: pass
            
    return val_str

def get_rs_pretty_name(field):
    """Maps database field names to readable labels for the audit log."""
    mapping = {
        'rs_no': 'RS No.', 'customer': 'Customer', 'quantity_required': 'Qty required',
        'finished_product': 'Finished Product', 'color_desc': 'Color Description',
        'primary_color': 'Primary Color', 'colorant_type': 'Colorant Type',
        'sm_no': 'Salesman', 'name': 'Color Requirement',
        'form_made': 'Date Created', 'date_required': 'Req. Date',
        'date_received_lab': 'Date Received', 'due_date_lab': 'Due Date'
    }
    return mapping.get(field, field.replace('_', ' ').title())

def _extract_rs_data(request):
    """Extracts and cleans raw POST data for RS processing."""
    data = request.POST

    colorant_type = data.get('colorantType')
    if colorant_type == "Other":
        colorant_type = data.get('colorantTypeOther')

    color_req = data.get('colorReq')
    if color_req == "other":
        color_req = data.get('colorReq_other')

    return {
        "rs_no": data.get('rs_no'),
        "customer": data.get('customer'),
        "salesman": data.get('salesman'),
        "primary_color": data.get('primary_color'),
        "quantity_required": data.get('quantity_kg'),
        "finished_product": data.get('finished_product'),
        "color_desc": data.get('color_description'),
        "date_form_made": format_date(data.get('date_created')),
        "date_lab_received": data.get('date_received'),
        "date_required": data.get('required_date'),
        "due_date": format_date(data.get('due_date')),
        "colorant_type": colorant_type,
        "color_req": color_req,
        "product_code_str": data.get('product_code'),
    }

# --- 2. MAIN LOGIC FUNCTIONS ---

def save_rs_complete_entry(request):
    """Creates a new RS entry."""
    with transaction.atomic():
        data = _extract_rs_data(request)

        salesman_obj = tbl_cmf_salesman.objects.filter(name=(data["salesman"] or "").strip()).first()
        if not salesman_obj:
            raise Exception(f"Salesman Error: '{data['salesman']}' is not registered.")

        selected_resins = request.POST.getlist('resin')
        selected_processes = request.POST.getlist('process')
        code_obj = _get_prod_code_obj(data["product_code_str"])

        rs_obj = tbl_rs.objects.create(
            rs_no=data["rs_no"],
            customer=data["customer"],
            quantity_required=data["quantity_required"],
            finished_product=data["finished_product"],
            matching_type="request",
            color_desc=data["color_desc"],
            primary_color=data["primary_color"],
            colorant_type=data["colorant_type"],
            user=request.user,
            sm_no=salesman_obj
        )
        
        tbl_cmf_dates.objects.create(
            rs_no=rs_obj,
            form_made=data["date_form_made"],
            date_received_lab=data["date_lab_received"],
            date_required=data["date_required"],
            due_date_lab=data["due_date"],
        )

        for r_id in selected_resins:
            res_ref = tbl_resin.objects.get(resin_no=r_id)
            tbl_resins_selected.objects.create(rs_no=rs_obj, resin_no=res_ref)

        for p_name in selected_processes:
            p_name = request.POST.get('otherProcess') if p_name == "others" else p_name
            if p_name:
                p_ref, _ = tbl_cmf_process.objects.get_or_create(name=p_name.strip())
                tbl_cmf_process02.objects.create(rs_no=rs_obj, process_no=p_ref)

        if data["color_req"]:
            tbl_cmf_color_req.objects.create(name=data["color_req"], rs_no=rs_obj)

        tbl_cmf_pending_completed.objects.create(rs_no=rs_obj, code=code_obj, is_completed=False)
        tbl_feedback_details.objects.create(rs_no=rs_obj)

        log_audit(request, "Saved", f"New RS Entry: {rs_obj.rs_no}")
        cache.delete('rs_records_list')

    return rs_obj

def update_rs_complete_entry(request, original_rs_id):
    """Updates an existing RS entry with detailed technical audit trail."""
    diff_logs = []

    with transaction.atomic():
        # Fetch the EXISTING instance
        rs_instance = tbl_rs.objects.filter(id=original_rs_id).select_related('sm_no').first()
        if not rs_instance:
            raise Exception(f"RS record (id={original_rs_id}) was not found.")

        extracted = _extract_rs_data(request)
        salesman_obj = tbl_cmf_salesman.objects.filter(name=(extracted["salesman"] or "").strip()).first()
        code_obj = _get_prod_code_obj(extracted["product_code_str"])
        
        # --- A. TRACK HEADER CHANGES ---
        header_map = {
            'rs_no': extracted["rs_no"],
            'customer': extracted["customer"],
            'quantity_required': extracted["quantity_required"],
            'finished_product': extracted["finished_product"],
            'color_desc': extracted["color_desc"],
            'primary_color': extracted["primary_color"],
            'colorant_type': extracted["colorant_type"],
            'sm_no': salesman_obj
        }

        for field, new_val in header_map.items():
            current_val = getattr(rs_instance, field)
            curr_str = format_val(current_val.name if field == 'sm_no' and current_val else current_val)
            new_str = format_val(new_val.name if field == 'sm_no' and new_val else new_val)

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
                    diff_logs.append(f"{get_rs_pretty_name(d_field)} ({format_val(d_old)} -> format_val(d_new))")

        # --- C. TRACK SELECTIONS ---
        # 1. Resins
        curr_resins = ", ".join(sorted(tbl_resins_selected.objects.filter(rs_no=rs_instance).values_list('resin_no__abbreviation', flat=True)))
        selected_resins_ids = [r for r in request.POST.getlist('resin') if r.strip()]
        new_resins_str = ", ".join(sorted(list(tbl_resin.objects.filter(resin_no__in=selected_resins_ids).values_list('abbreviation', flat=True))))
        if curr_resins != new_resins_str:
            diff_logs.append(f"Resins ({curr_resins or 'None'} -> {new_resins_str or 'None'})")

        # 2. Processes
        curr_procs = ", ".join(sorted(tbl_cmf_process02.objects.filter(rs_no=rs_instance).values_list('process_no__name', flat=True)))
        raw_procs = request.POST.getlist('process')
        new_procs_list = sorted([request.POST.get('otherProcess', '').strip() if p == "others" else p.strip() for p in raw_procs if p.strip()])
        new_procs_str = ", ".join(new_procs_list)
        if curr_procs != new_procs_str:
            diff_logs.append(f"Processes ({curr_procs or 'None'} -> {new_procs_str or 'None'})")

        # 3. Color Requirement
        old_req_obj = tbl_cmf_color_req.objects.filter(rs_no=rs_instance).first()
        curr_req_str, new_req_str = format_val(old_req_obj.name if old_req_obj else ""), format_val(extracted["color_req"])
        if curr_req_str != new_req_str:
            diff_logs.append(f"Color Req ({curr_req_str} -> {new_req_str})")

        # --- 3. COMMIT UPDATES TO DATABASE ---
        # Update header fields on existing instance
        for field, val in header_map.items(): 
            setattr(rs_instance, field, val)
        rs_instance.save()

        # Update sub-tables
        tbl_cmf_dates.objects.filter(rs_no=rs_instance).update(**date_updates)
        
        tbl_resins_selected.objects.filter(rs_no=rs_instance).delete()
        for r_id in selected_resins_ids:
            tbl_resins_selected.objects.create(rs_no=rs_instance, resin_no=tbl_resin.objects.get(resin_no=r_id))

        tbl_cmf_process02.objects.filter(rs_no=rs_instance).delete()
        for name in new_procs_list:
            p_ref, _ = tbl_cmf_process.objects.get_or_create(name=name)
            tbl_cmf_process02.objects.create(rs_no=rs_instance, process_no=p_ref)

        tbl_cmf_color_req.objects.update_or_create(rs_no=rs_instance, defaults={'name': extracted["color_req"]})
        tbl_cmf_pending_completed.objects.filter(rs_no=rs_instance).update(code=code_obj)

        # --- 4. LOGGING ---
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