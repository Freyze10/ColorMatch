from datetime import datetime

from django.http import JsonResponse
import re

from main.models import tbl_cmf, tbl_cmf_pending_completed, tbl_dc_extruder_formula, tbl_mb_extruder_formula

def check_previous_matching(request):
    cm_no_input = request.GET.get('cm_no', '').strip()
    original_cm_no = request.GET.get('original_cm_no', '').strip()

    if not cm_no_input:
        return JsonResponse({'match': False, 'exists_exact': False})

    # 1. HARD VALIDATION: Case-insensitive check (__iexact)
    # If updating, exclude the original CMF so it doesn't collide with itself
    exists_query = tbl_cmf.objects.filter(cm_no__iexact=cm_no_input)
    if original_cm_no:
        exists_query = exists_query.exclude(cm_no__iexact=original_cm_no)

    exists_exact = exists_query.exists()

    # 2. SEQUENTIAL VALIDATION (c through z)
    sequential_error = None
    is_editing_same = bool(original_cm_no and cm_no_input.lower() == original_cm_no.lower())
    # This regex captures the base part and the last letter suffix (e.g., 'A9151', 'c')
    match_parts = re.match(r'^(.+)([a-zA-Z])$', cm_no_input)
    # Only run sequential check if not editing the existing record unchanged
    if not is_editing_same:
        match_parts = re.match(r'^(.+)([a-zA-Z])$', cm_no_input)
        if match_parts:
            base, suffix = match_parts.groups()
            suffix = suffix.lower()

            # Check only if suffix is 'c' or higher
            if 'c' <= suffix <= 'z':
                prev_suffix = chr(ord(suffix) - 1)
                prev_cm_no = f"{base}{prev_suffix}"

                # Check if the required previous version exists (case-insensitive)
                if not tbl_cmf.objects.filter(cm_no__iexact=prev_cm_no).exists():
                    sequential_error = f"Cannot create '{cm_no_input}'. The previous version '{prev_cm_no}' must exist first."

    # 3. SUGGESTION LOGIC (Only run if no sequential error and doesn't exist yet)
    match_found = False
    latest_cm_no = None
    if not sequential_error and not exists_exact and not is_editing_same:
        if re.search(r'[a-zA-Z]$', cm_no_input):
            base_sug = re.sub(r'[a-zA-Z]$', '', cm_no_input)
            sug_query = tbl_cmf.objects.filter(
                cm_no__istartswith=base_sug
            ).exclude(cm_no__iexact=cm_no_input)

            if original_cm_no:
                sug_query = sug_query.exclude(cm_no__iexact=original_cm_no)

            latest_record = sug_query.order_by('-cm_no').first()
            if latest_record:
                match_found = True
                latest_cm_no = latest_record.cm_no

    return JsonResponse({
        'exists_exact': exists_exact,
        'sequential_error': sequential_error,
        'match': match_found,
        'latest_cm_no': latest_cm_no
    })

def check_prod_code_cmf(request):
    code_no = request.GET.get('code_no')
    
    # --- CHECK BY PRODUCT CODE (For RS) ---
    if code_no:
        # Find latest MB or DC formula that used this product code and has a linked CMF
        mb = tbl_mb_extruder_formula.objects.filter(code_id=code_no, cm_no__isnull=False).select_related('cm_no').order_by('-date', '-mb_no').first()
        dc = tbl_dc_extruder_formula.objects.filter(code_id=code_no, cm_no__isnull=False).select_related('cm_no').order_by('-date', '-dc_no').first()

        latest_cm_no = None
        if mb and dc:
            latest_cm_no = mb.cm_no.cm_no if (mb.date or datetime.date.min) >= (dc.date or datetime.date.min) else dc.cm_no.cm_no
        elif mb:
            latest_cm_no = mb.cm_no.cm_no
        elif dc:
            latest_cm_no = dc.cm_no.cm_no
        else:
            # Fallback to pending_completed table if not found in extruder formulas
            pending = tbl_cmf_pending_completed.objects.filter(code_id=code_no, cm_no__isnull=False).select_related('cm_no').order_by('-completed_id').first()
            if pending:
                latest_cm_no = pending.cm_no.cm_no

        if latest_cm_no:
            return JsonResponse({'match': True, 'cm_no': latest_cm_no})
        return JsonResponse({'match': False})