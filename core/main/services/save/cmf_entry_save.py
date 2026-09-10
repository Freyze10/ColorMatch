import re
import json
from django.core.cache import cache
from django.db import transaction
from datetime import datetime, date

from django.http import Http404, HttpResponse
from main.services.save.utils import to_bool, format_date, clean_numeric
from main.utils.log_audit_trail import log_audit
from main.models import (
    tbl_cmf, tbl_cmf_color_req, tbl_cmf_dates, tbl_cmf_formula, 
    tbl_cmf_process, tbl_cmf_process02, tbl_cmf_scanned, tbl_resin, tbl_resins_selected,
    tbl_cmf_specification, tbl_cmf_specification02, tbl_cmf_salesman,
    tbl_cmf_pending_completed, tbl_feedback_details
)

def _handle_file_uploads(request, cmf_instance):
    """Reads files from request.FILES and saves them as binary to the database."""
    files = request.FILES.getlist('file')
    for f in files:
        tbl_cmf_scanned.objects.create(
            cm=cmf_instance,
            file_name=f.name,
            file_type=f.content_type,
            file_content=f.read(), # Stores the actual bytes in the BinaryField
            user=request.user
        )
    return len(files)

def blank_to_none(val):
    """Returns None if val is missing/empty/whitespace, otherwise the stripped value."""
    if val is None:
        return None
    val = val.strip()
    return val if val else None

def save_cmf_complete_entry(request):
    data = request.POST
    
    # --- 1. CLEAN AND VALIDATE LISTS ---
    selected_resins = [r for r in data.getlist('resin') if r.strip()]
    selected_processes = [p for p in data.getlist('process') if p.strip()]
    selected_specs = [s for s in data.getlist('specification') if s.strip()]

    if not selected_resins:
        raise Exception("Selection Required: At least one Resin Type must be selected.")
    if not selected_processes:
        raise Exception("Selection Required: At least one Process must be selected.")

    # --- 2. DATABASE TRANSACTION ---
    with transaction.atomic():
        salesman_name = data.get('salesman').strip()
        salesman_obj = tbl_cmf_salesman.objects.filter(name=salesman_name).first()
        if not salesman_obj:
            raise Exception(f"Salesman Error: '{salesman_name}' is not a registered salesman.")

        cm_no = data.get('cmf_no').strip()
        if tbl_cmf.objects.filter(cm_no=cm_no).exists():
            raise Exception(f"Duplicate Error: CMF No. {cm_no} already exists.")

        ct_value = data.get('colorantType')
        if ct_value == "Other": ct_value = data.get('colorantTypeOther')

        cmf_main = tbl_cmf.objects.create(
            cm_no=cm_no,
            matching_type=data.get('matchType'),
            product_status=data.get('product_status'),
            est_qty_order=clean_numeric(data.get('est_qty_order')),
            in_code_no_id=data.get('primary_color'),
            color_desc=data.get('color_description'),
            qty_resin_testing=data.get('qty_resin_test'),
            is_resin_provided=to_bool(data.get('customerResin')),
            mi_c_resin=data.get('mi_customer_resin'),
            is_sample_available=to_bool(data.get('sampleColorant')),
            colorant_type=ct_value,
            is_guide_to_return=to_bool(data.get('color_guide_return')),
            temperature=data.get('processing_temp'),
            is_low_cost=to_bool(data.get('is_low_cost')),
            remarks=data.get('remarks'),
            user=request.user,
            sm=salesman_obj
        )

        c_req = data.get('colorReq')
        if c_req == "other": c_req = data.get('colorReq_other')
        tbl_cmf_color_req.objects.create(name=c_req, cm_no=cmf_main)

        tbl_cmf_dates.objects.create(
            form_made=format_date(data.get('date_created')),
            date_required=blank_to_none(data.get('required_date')),
            date_received_lab=blank_to_none(data.get('date_received')),
            submit_to_lab=blank_to_none(data.get('submit_to_lab')),
            due_date_lab=format_date(data.get('due_date')),
            cm_no=cmf_main
        )

        formula_obj = tbl_cmf_formula.objects.create(
            customer=data.get('customer'),
            finished_product=data.get('finished_product'),
            dosage=clean_numeric(data.get('dosage')),
            cm_no=cmf_main
        )

        for p_name in selected_processes:
            p_name = data.get('otherProcess') if p_name == "others" else p_name
            if p_name:
                p_ref, _ = tbl_cmf_process.objects.get_or_create(name=p_name.strip())
                tbl_cmf_process02.objects.create(cmf_formula_no=formula_obj, process_no=p_ref)

        for r_id in selected_resins:
            resin_ref = tbl_resin.objects.get(resin_no=r_id)
            tbl_resins_selected.objects.create(cm_no=cmf_main, resin_no=resin_ref)

        for s_name in selected_specs:
            s_name = data.get('specificationOther') if s_name == "Others" else s_name
            if s_name:
                s_ref, _ = tbl_cmf_specification.objects.get_or_create(name=s_name.strip())
                tbl_cmf_specification02.objects.create(cm_no=cmf_main, spec_no=s_ref)
        
        tbl_cmf_pending_completed.objects.create(cm_no=cmf_main)
        tbl_feedback_details.objects.create(cm_no=cmf_main)

        num_files = _handle_file_uploads(request, cmf_main)
        
        cache.delete('cmf_records_list')
        log_audit(request, "Saved", f"New CMF Entry: {cmf_main.cm_no} ({num_files} attachments)")
    return cmf_main

def update_cmf_complete_entry(request, original_cmf_no):
    data = request.POST
    diff_logs = []

    # --- 1. HELPERS ---
    def format_val(val):
        """Standardizes values to readable strings for comparison."""
        if val is True or str(val).lower() == 'true': return "Yes"
        if val is False or str(val).lower() == 'false': return "No"
        if val is None or val == "" or val == "None": return "---"
        
        # Handle Date/Datetime objects from Database
        if isinstance(val, (date, datetime)):
            return val.strftime('%m/%d/%Y')
        
        # Handle Date-like strings (e.g. '2026-05-12' -> '05/12/2026')
        val_str = str(val).strip()
        if re.match(r'^\d{4}-\d{2}-\d{2}$', val_str):
            try:
                return datetime.strptime(val_str, '%Y-%m-%d').strftime('%m/%d/%Y')
            except: pass
            
        return val_str

    def get_pretty_name(field):
        mapping = {
            'matching_type': 'Matching Type', 'product_status': 'Product Status', 
            'est_qty_order': 'Est. Qty Order',  'in_code_no_id': 'Primary Color',
            'color_desc': 'Color Description', 'qty_resin_testing': 'Qty Resin',
            'is_resin_provided': 'Resin Provided', 'mi_c_resin': 'MI Resin',
            'is_sample_available': 'Sample Available', 'colorant_type': 'Colorant Type',
            'is_guide_to_return': 'Guide Return', 'temperature': 'Temp',
            'is_low_cost': 'Low Cost', 'remarks': 'Remarks', 'sm': 'Salesman',
            'customer': 'Customer', 'finished_product': 'Finished Product', 'dosage': 'Dosage',
            'color_req': 'Color Requirement', 'form_made': 'Date Created', 
            'date_required': 'Req. Date', 'date_received_lab': 'Date Received', 'due_date_lab': 'Due Date',
            'submit_to_lab': 'Submit to Lab'
        }
        return mapping.get(field, field.replace('_', ' ').title())

    # --- 2. PREPARE INPUTS ---
    selected_resins = [r for r in data.getlist('resin') if r.strip()]
    selected_processes = [p for p in data.getlist('process') if p.strip()]
    selected_specs = [s for s in data.getlist('specification') if s.strip()]

    with transaction.atomic():
        old_cmf = tbl_cmf.objects.filter(cm_no=original_cmf_no).first()
        if not old_cmf: raise Exception("CMF not found.")

        salesman_name = data.get('salesman', '').strip()
        salesman_obj = tbl_cmf_salesman.objects.filter(name=salesman_name).first()

        new_cmf_no = data.get('cmf_no').strip()
        renaming = new_cmf_no != original_cmf_no
        
        ct_value = data.get('colorantType')
        if ct_value == "Other": ct_value = data.get('colorantTypeOther')

        # --- A. TRACK HEADER CHANGES ---
        header_map = {
            'matching_type': data.get('matchType'),
            'product_status': data.get('product_status'),
            'est_qty_order': clean_numeric(data.get('est_qty_order')),
            'in_code_no_id': int(data.get('primary_color')) if data.get('primary_color') else None,
            'color_desc': data.get('color_description'),
            'qty_resin_testing': data.get('qty_resin_test'),
            'is_resin_provided': to_bool(data.get('customerResin')),
            'mi_c_resin': data.get('mi_customer_resin'),
            'is_sample_available': to_bool(data.get('sampleColorant')),
            'colorant_type': ct_value,
            'is_guide_to_return': to_bool(data.get('color_guide_return')),
            'temperature': data.get('processing_temp'),
            'is_low_cost': to_bool(data.get('is_low_cost')),
            'remarks': data.get('remarks'),
            'sm': salesman_obj
        }

        for field, new_val in header_map.items():
            current_val = getattr(old_cmf, field)
            curr_str = format_val(current_val.name if field == 'sm' and current_val else current_val)
            new_str = format_val(new_val.name if field == 'sm' and new_val else new_val)
            if field == 'est_qty_order':
                curr_str = str(float(current_val or 0))
                new_str = str(float(new_val or 0))

            if curr_str != new_str:
                diff_logs.append(f"{get_pretty_name(field)} ({curr_str} -> {new_str})")

        # --- B. TRACK COLOR REQUIREMENT ---
        old_req_obj = tbl_cmf_color_req.objects.filter(cm_no=old_cmf).first()
        new_req_val = data.get('colorReq_other') if data.get('colorReq') == "other" else data.get('colorReq')
        
        old_req_str = format_val(old_req_obj.name if old_req_obj else "")
        new_req_str = format_val(new_req_val)
        if old_req_str != new_req_str:
            diff_logs.append(f"Color Requirement ({old_req_str} -> {new_req_str})")

        # --- C. TRACK DATES (STRICT MM/DD/YYYY) ---
        old_dates_obj = tbl_cmf_dates.objects.filter(cm_no=old_cmf).first()
        if old_dates_obj:
            # Comparing Raw Strings from POST vs Database formatted strings
            date_comparisons = [
                ('form_made', data.get('date_created')),
                ('date_required', data.get('required_date')),
                ('date_received_lab', data.get('date_received')),
                ('submit_to_lab', data.get('submit_to_lab')),
                ('due_date_lab', data.get('due_date')),
            ]
            for field_name, new_date_str in date_comparisons:
                db_val = getattr(old_dates_obj, field_name)
                db_str = format_val(db_val)
                input_str = format_val(blank_to_none(new_date_str))
                
                if db_str != input_str:
                    diff_logs.append(f"{get_pretty_name(field_name)} ({db_str} -> {input_str})")

        # --- D. TRACK FORMULA ---
        formula_obj, _ = tbl_cmf_formula.objects.get_or_create(cm_no=old_cmf)
        formula_map = {
            'customer': data.get('customer'),
            'finished_product': data.get('finished_product'),
            'dosage': str(clean_numeric(data.get('dosage')))
        }
        for f_field, f_val in formula_map.items():
            curr_f_val = format_val(getattr(formula_obj, f_field))
            new_f_val = format_val(f_val)
            if curr_f_val != new_f_val:
                diff_logs.append(f"{get_pretty_name(f_field)} ({curr_f_val} -> {new_f_val})")

        # --- E. TRACK JUNCTIONS ---
        # Resins
        curr_resins = ", ".join(sorted(tbl_resins_selected.objects.filter(cm_no=old_cmf).values_list('resin_no__abbreviation', flat=True)))
        new_resins_str = ", ".join(sorted(list(tbl_resin.objects.filter(resin_no__in=selected_resins).values_list('abbreviation', flat=True))))
        if curr_resins != new_resins_str:
            diff_logs.append(f"Resins ({curr_resins or 'None'} -> {new_resins_str or 'None'})")

        # Processes
        curr_procs = ", ".join(sorted(tbl_cmf_process02.objects.filter(cmf_formula_no=formula_obj).values_list('process_no__name', flat=True)))
        new_procs_list = sorted([data.get('otherProcess', '').strip() if p.lower() == "others" else p.strip() for p in selected_processes if p.strip()])
        new_procs_str = ", ".join(new_procs_list)
        if curr_procs != new_procs_str:
            diff_logs.append(f"Processes ({curr_procs or 'None'} -> {new_procs_str or 'None'})")

        # Specifications
        curr_specs = ", ".join(sorted(tbl_cmf_specification02.objects.filter(cm_no=old_cmf).values_list('spec_no__name', flat=True)))
        new_specs_list = sorted([data.get('specificationOther', '').strip() if s == "Others" else s.strip() for s in selected_specs if s.strip()])
        new_specs_str = ", ".join(new_specs_list)
        if curr_specs != new_specs_str:
            diff_logs.append(f"Specifications ({curr_specs or 'None'} -> {new_specs_str or 'None'})")

        # --- 3. DATABASE EXECUTION ---
        if renaming:
            if tbl_cmf.objects.filter(cm_no=new_cmf_no).exists(): raise Exception("Duplicate No.")
            cmf_main = tbl_cmf.objects.create(cm_no=new_cmf_no, user=old_cmf.user, **header_map)
            for model in [tbl_cmf_color_req, tbl_cmf_dates, tbl_cmf_formula, tbl_resins_selected, tbl_cmf_specification02, tbl_cmf_pending_completed, tbl_feedback_details]:
                model.objects.filter(cm_no=old_cmf).update(cm_no=cmf_main)
            old_cmf.delete()
        else:
            cmf_main = old_cmf
            for field, val in header_map.items(): setattr(cmf_main, field, val)
            cmf_main.save()

        # Update Related
        tbl_cmf_color_req.objects.filter(cm_no=cmf_main).update(name=new_req_val)
        tbl_cmf_dates.objects.filter(cm_no=cmf_main).update(
            form_made=format_date(data.get('date_created')),
            date_required=blank_to_none(data.get('required_date')),
            date_received_lab=blank_to_none(data.get('date_received')),
            submit_to_lab=blank_to_none(data.get('submit_to_lab')),
            due_date_lab=format_date(data.get('due_date'))
        )
        tbl_cmf_formula.objects.filter(cm_no=cmf_main).update(**formula_map)
        
        # Junctions
        tbl_cmf_process02.objects.filter(cmf_formula_no__cm_no=cmf_main).delete()
        for name in new_procs_list:
            p_ref, _ = tbl_cmf_process.objects.get_or_create(name=name)
            tbl_cmf_process02.objects.create(cmf_formula_no=tbl_cmf_formula.objects.get(cm_no=cmf_main), process_no=p_ref)

        tbl_resins_selected.objects.filter(cm_no=cmf_main).delete()
        for r_id in selected_resins:
            resin_ref = tbl_resin.objects.get(resin_no=r_id)
            tbl_resins_selected.objects.create(cm_no=cmf_main, resin_no=resin_ref)

        tbl_cmf_specification02.objects.filter(cm_no=cmf_main).delete()
        for name in new_specs_list:
            s_ref, _ = tbl_cmf_specification.objects.get_or_create(name=name)
            tbl_cmf_specification02.objects.create(cm_no=cmf_main, spec_no=s_ref)

        num_files = _handle_file_uploads(request, cmf_main)
        if num_files > 0:
            diff_logs.append(f"Added {num_files} attachments")

        # --- 4. LOGGING ---
        log_msg = f"CMF: {original_cmf_no}"
        if renaming: log_msg += f" (Renamed to {new_cmf_no})"
        log_msg += ". Changes: " + (", ".join(diff_logs) if diff_logs else "No technical changes.")

        cache.delete('cmf_records_list')
        log_audit(request, "Updated", log_msg)

    return cmf_main


def download_cmf_attachment(request, attachment_id):
    attachment = tbl_cmf_scanned.objects.filter(pk=attachment_id).first()
    if not attachment:
        raise Http404("Attachment not found.")

    response = HttpResponse(attachment.file_content, content_type=attachment.file_type or 'application/octet-stream')
    response['Content-Disposition'] = f'attachment; filename="{attachment.file_name}"'
    return response