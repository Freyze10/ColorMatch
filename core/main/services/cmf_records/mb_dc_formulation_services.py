import re
from django.http import JsonResponse
from django.db.models import Max
from main.models import (
    tbl_cmf, tbl_cmf_formula, tbl_coding_materials, tbl_mb_extruder_formula, tbl_resins_selected, 
    tbl_cmf_process02, tbl_master_formula, tbl_generated_prod_code
)

def get_formulation_details(request):
    cm_no = request.GET.get('cm_no')
    mat_id = request.GET.get('mat_id') # Passed from JS
    
    cmf = tbl_cmf.objects.filter(cm_no=cm_no).first()
    if not cmf:
        return JsonResponse({'error': 'Not found'}, status=404)

    formula_info = tbl_cmf_formula.objects.filter(cm_no=cm_no).first()
    colorant_type = (cmf.colorant_type or "").upper()
    
    # 1. Concatenate Data
    resins_qs = tbl_resins_selected.objects.filter(cm_no=cmf).select_related('resin_no').order_by('pk')
    resin_str = ", ".join([r.resin_no.abbreviation for r in resins_qs if r.resin_no])
    
    processes = tbl_cmf_process02.objects.filter(cmf_formula_no=formula_info).values_list('process_no__name', flat=True)
    app_str = ", ".join(filter(None, processes))

    # 2. Product Code Generation
    generated_code = ""
    generated_lot = ""
    if colorant_type == 'MB':
        # Get the prefix letter (e.g., 'G')
        prefix = cmf.in_code_no.code if cmf.in_code_no else ""
        
        if prefix:
            # We look for the pattern: Prefix + Fixed (A) + 5 Digits + Fixed (E)
            # Adjust the 'A' and 'E' if your fixed characters are different
            # Regex: ^[Prefix]A(\d{5})E$
            pattern = rf'^{prefix}A(\d{{5}})E$'
            
            # Helper function to find the max number in a specific table
            def get_max_from_table(model, field_name, search_prefix, regex_pattern):
                codes = model.objects.filter(**{f"{field_name}__startswith": search_prefix}).values_list(field_name, flat=True)
                nums = []
                for c in codes:
                    match = re.match(regex_pattern, str(c))
                    if match:
                        nums.append(int(match.group(1)))
                return max(nums) if nums else 0

            # Get max from Master Formula
            max_mf = get_max_from_table(tbl_master_formula, 'product_code', prefix, pattern)
            
            # Get max from Generated Prod Code
            max_gen = get_max_from_table(tbl_generated_prod_code, 'product_code', prefix, pattern)
            
            # Determine the final latest number and increment
            latest_num = max(max_mf, max_gen)
            new_num = latest_num + 1
            
            # Format back to string: Prefix + A + 5-digit zero-padded number + E
            # Example: G + A + 32213 + E = GA32213E
            generated_code = f"{prefix}A{str(new_num).zfill(5)}E"

            # --- LOT NUMBER LOGIC (NEW) ---
        lot_prefix = "CMA-"
        # Fetch all lots starting with CMA-
        existing_lots = tbl_mb_extruder_formula.objects.filter(lot_no__startswith=lot_prefix).values_list('lot_no', flat=True)
        
        lot_nums = []
        for lot in existing_lots:
            # Extract digits after "CMA-"
            match = re.search(r'CMA-(\d+)', str(lot))
            if match:
                lot_nums.append(int(match.group(1)))
        
        if lot_nums:
            next_lot_val = max(lot_nums) + 1
            generated_lot = f"CMA-{next_lot_val}"
        else:
            # Default starting point if no records exist
            generated_lot = "CMA-10001"
    
    elif colorant_type == 'DC':
        if not mat_id:
            generated_code = "(Select Material)"
        else:
            try:
                # Part A: Material Code (e.g., 'D')
                mat_ref = tbl_coding_materials.objects.get(pk=mat_id)
                mat_part = mat_ref.code or ""

                # Part B: First Resin Code (e.g., 'E')
                first_resin = resins_qs.first()
                resin_part = first_resin.resin_no.code if (first_resin and first_resin.resin_no) else ""

                # Part C: Color Code Prefix (e.g., 'B')
                color_part = cmf.in_code_no.code if cmf.in_code_no else ""

                # Construct Prefix: "DE-B"
                prefix = f"{mat_part}{resin_part}-{color_part}"
                
                # Regex for "DE-B17780E": Prefix + 5 digits + E
                pattern = rf'^{prefix}(\d{{5}})E$'

                def get_max_val(model):
                    codes = model.objects.filter(product_code__startswith=prefix).values_list('product_code', flat=True)
                    nums = []
                    for c in codes:
                        m = re.match(pattern, str(c))
                        if m: nums.append(int(m.group(1)))
                    return max(nums) if nums else 0

                max_mf = get_max_val(tbl_master_formula)
                max_gen = get_max_val(tbl_generated_prod_code)
                
                next_num = max(max_mf, max_gen) + 1
                generated_code = f"{prefix}{str(next_num).zfill(5)}E"

            except Exception as e:
                generated_code = f"Error: {str(e)}"


    data = {
        'customer': formula_info.customer if formula_info else "",
        'resin': resin_str,
        'color': cmf.in_code_no.color if cmf.in_code_no else (cmf.color_desc or ""),
        'product_code': generated_code if generated_code else (cmf.in_code_no.code if cmf.in_code_no else ""),
        'dosage': formula_info.dosage if formula_info else "",
        'lot_no': generated_lot,
        'application': app_str,
        'finished_product': formula_info.finished_product if formula_info else "",
        'colorant_type': colorant_type,
    }
    return JsonResponse(data)


def check_lot_number(request):
    lot_no = request.GET.get('lot_no', '').strip()
    formula_id = request.GET.get('formula_id', '').strip()
    exists = False

    if lot_no and lot_no.upper() != 'N/A':
        qs = tbl_mb_extruder_formula.objects.filter(lot_no__iexact=lot_no)
        # Exclude current formula if editing
        if formula_id and formula_id.isdigit():
            qs = qs.exclude(pk=int(formula_id))
        exists = qs.exists()

    return JsonResponse({'exists': exists})