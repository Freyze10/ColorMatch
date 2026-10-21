import json
import re
from django.http import JsonResponse
from django.db.models import Q, Max
from main.models import (
    tbl_cmf, tbl_cmf_formula, tbl_coding_materials, tbl_dc_extruder_formula, tbl_dc_extruder_materials, tbl_dc_extruder_version, tbl_master_formula_encode, tbl_master_formula_info, tbl_mb_extruder_formula, tbl_mb_extruder_formula02, tbl_resins_selected, 
    tbl_cmf_process02, tbl_master_formula, tbl_generated_prod_code, tbl_field_note
)
from django.contrib.auth import get_user_model
User = get_user_model()

def get_formulation_details(request):
    cm_no = request.GET.get('cm_no')
    mat_id = request.GET.get('mat_id') # Passed from JS
    
    cmf = tbl_cmf.objects.filter(cm_no=cm_no).first()
    if not cmf:
        return JsonResponse({'error': 'Not found'}, status=404)

    formula_info = tbl_cmf_formula.objects.filter(cm_no=cm_no).first()
    colorant_type = (cmf.colorant_type or "").upper()

    # 1. Fetch Dosage Note (prioritized for new formulas)
    dosage_note_obj = tbl_field_note.objects.filter(
        Q(cmf_formula_no=formula_info) | Q(cmf_formula_no__cm_no=cmf),
        Q(field__iexact='dosage') | Q(field__iexact='dosage_note')
    ).exclude(note__isnull=True).exclude(note='').order_by('-id').first()

    dosage_val = dosage_note_obj.note.strip() if (dosage_note_obj and dosage_note_obj.note) else (formula_info.dosage if formula_info else "")
    
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
        'color_desc': cmf.color_desc.upper() or (cmf.in_code_no.color or ""),
        'color': cmf.in_code_no.color or "",
        'primary_color_id': cmf.in_code_no.in_code_no if cmf.in_code_no else "",
        'product_code': generated_code if generated_code else (cmf.in_code_no.code if cmf.in_code_no else ""),
        'dosage': dosage_val,
        'lot_no': "", #generated_lot = next suggestion lot number, temporarily removed when entering past record
        'application': app_str.upper() if app_str else "",
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


def check_product_code_formula(request):
    """
    Checks if a product code already exists in MB/DC formulas and whether
    its material composition matches the incoming formula.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=400)

    try:
        payload = json.loads(request.body)
    except Exception:
        payload = request.POST

    product_code = (payload.get('product_code') or '').strip()
    formula_type = (payload.get('formula_type') or 'MB').upper()
    formula_id = payload.get('formula_id')
    submitted_materials = payload.get('materials', [])

    if not product_code:
        return JsonResponse({'exists': False})

    # Helper: normalizes MB ingredients list ignoring zero values
    def _norm_mb(items):
        norm = []
        for item in items:
            m_name = (item.get('material') or '').strip().lower()
            try:
                val = round(float(item.get('value') or item.get('percentage') or 0), 4)
            except (ValueError, TypeError):
                val = 0.0
            if m_name and val != 0:
                norm.append((m_name, val))
        return sorted(norm)

    # Helper: normalizes DC versions list ignoring zero values
    def _norm_dc(items):
        norm = []
        for item in items:
            m_name = (item.get('material') or '').strip().lower()
            v_no = int(item.get('version_no') or 1)
            try:
                val = round(float(item.get('value') or 0), 4)
            except (ValueError, TypeError):
                val = 0.0
            if m_name and val != 0:
                norm.append((m_name, v_no, val))
        return sorted(norm)

    if formula_type == 'MB':
        norm_submitted = _norm_mb(submitted_materials)
        qs = tbl_mb_extruder_formula.objects.filter(code__product_code__iexact=product_code)
        if formula_id and str(formula_id).isdigit():
            qs = qs.exclude(pk=int(formula_id))

        if not qs.exists():
            return JsonResponse({'exists': False})

        has_same_formula = False
        for f in qs:
            db_items = list(tbl_mb_extruder_formula02.objects.filter(mb=f).values('material', 'value'))
            if _norm_mb(db_items) == norm_submitted:
                has_same_formula = True
                break

        return JsonResponse({
            'exists': True,
            'is_same': has_same_formula,
            'count': qs.count()
        })

    elif formula_type == 'DC':
        norm_submitted = _norm_dc(submitted_materials)
        qs = tbl_dc_extruder_formula.objects.filter(code__product_code__iexact=product_code)
        if formula_id and str(formula_id).isdigit():
            qs = qs.exclude(pk=int(formula_id))

        if not qs.exists():
            return JsonResponse({'exists': False})

        has_same_formula = False
        for f in qs:
            db_items = list(
                tbl_dc_extruder_version.objects.filter(material__dc=f)
                .values('material__material', 'version_no', 'value')
            )
            formatted_items = [
                {'material': d['material__material'], 'version_no': d['version_no'], 'value': d['value']}
                for d in db_items
            ]
            if _norm_dc(formatted_items) == norm_submitted:
                has_same_formula = True
                break

        return JsonResponse({
            'exists': True,
            'is_same': has_same_formula,
            'count': qs.count()
        })

    return JsonResponse({'exists': False})


def _resolve_matcher_id(match_by_text):
    """Maps free-text legacy or current match_by strings to active lab user IDs."""
    if not match_by_text:
        return None
    
    clean_text = match_by_text.strip().lower()
    
    # Check direct username or full name matches first
    for u in User.objects.filter(is_active=True):
        full_name = f"{u.first_name} {u.last_name}".strip().lower()
        if clean_text in full_name or full_name in clean_text or clean_text == u.username.lower():
            return u.id

    # Handle known keyword mappings
    if 'ann' in clean_text or 'ana' in clean_text:
        u = User.objects.filter(first_name__iexact='Ana').first()
    elif 'ernie' in clean_text:
        u = User.objects.filter(first_name__iexact='Ernie').first()
    elif 'geelyn' in clean_text:
        u = User.objects.filter(first_name__iexact='Geelyn').first()
    elif 'jinky' in clean_text:
        u = User.objects.filter(first_name__iexact='Jinky').first()
    elif 'linzy' in clean_text:
        u = User.objects.filter(first_name__icontains='Linzy').first()
    else:
        return None
        
    return u.id if u else None

def get_matching_formula_by_product_code(product_code_str, formula_type, cm_no_str=None):
    if not product_code_str:
        return None

    clean_code = product_code_str.strip()
    f_type = formula_type.upper()

    base_payload = {
        'index_no': '', 'dosage': '', 'mix_time': '', 'notes': '', 'matcher_id': '',
        'html_code_hex': '', 'cyan': '', 'magenta': '', 'yellow': '', 'black': '',
        'total_concentration': '', 'colormatch_date': '' 
    }

    # 1. Check Extruder History First
    prod_code_obj = tbl_generated_prod_code.objects.filter(product_code__iexact=clean_code).first()
    if prod_code_obj:
        if f_type == 'MB':
            formula = tbl_mb_extruder_formula.objects.filter(code=prod_code_obj).order_by('-mb_no').first()
            if formula:
                details = tbl_mb_extruder_formula02.objects.filter(mb=formula)
                ingredients = [{'material': d.material, 'value': float(d.value or 0), 'weight': float(d.weight or 0)} for d in details]
                
                payload = base_payload.copy()
                payload.update({
                    'formula_type': 'MB', 
                    'source': 'extruder',
                    'ingredients': ingredients,
                    'html_code_hex': formula.html or '',
                    'cyan': float(formula.c) if formula.c is not None else '',
                    'magenta': float(formula.m) if formula.m is not None else '',
                    'yellow': float(formula.y) if formula.y is not None else '',
                    'black': float(formula.k) if formula.k is not None else '',
                })
                return payload

        elif f_type == 'DC':
            formula = tbl_dc_extruder_formula.objects.filter(code=prod_code_obj).order_by('-dc_no').first()
            if formula:
                materials = tbl_dc_extruder_materials.objects.filter(dc=formula)
                material_rows = []
                for m in materials:
                    versions = [float(v.value or 0) for v in m.versions.all().order_by('version_no')]
                    while len(versions) < 10: versions.append(0)
                    material_rows.append({'material': m.material, 'versions': versions[:10]})
                
                payload = base_payload.copy()
                payload.update({
                    'formula_type': 'DC', 
                    'source': 'extruder',
                    'material_rows': material_rows,
                    'html_code_hex': formula.html or '',
                    'cyan': float(formula.c) if formula.c is not None else '',
                    'magenta': float(formula.m) if formula.m is not None else '',
                    'yellow': float(formula.y) if formula.y is not None else '',
                    'black': float(formula.k) if formula.k is not None else '',
                })
                return payload

    # 2. Fallback to tbl_master_formula if product code has no extruder record
    if cm_no_str and cm_no_str.upper() != 'N/A':
        clean_cm = cm_no_str.strip().upper()
        
        # Look for master formula matching product code and exact/partial CMF string
        master = None
        for mf in tbl_master_formula.objects.filter(product_code__iexact=clean_code, is_deleted=False).order_by('-form_id'):
            if mf.cm_no and mf.cm_no.strip().upper() == clean_cm:
                master = mf
                break

        if master:
            encode = tbl_master_formula_encode.objects.filter(form=master).first()
            matcher_id = _resolve_matcher_id(encode.match_by if encode else '')
            mix_time_val = ''.join(filter(str.isdigit, master.mix_time)) if master.mix_time else '5'
            materials_info = tbl_master_formula_info.objects.filter(form=master, is_deleted=False).order_by('sequence_no')

            payload = base_payload.copy()
            payload.update({
                'index_no': master.index_no or '',
                'source': 'master',                
                'dosage': float(master.ld) if master.ld else '',
                'mix_time': mix_time_val,
                'notes': master.notes or '',
                'matcher_id': matcher_id,
                'html_code_hex': master.html_code_hex or '',
                'cyan': float(master.cyan) if master.cyan is not None else '',
                'magenta': float(master.magenta) if master.magenta is not None else '',
                'yellow': float(master.yellow) if master.yellow is not None else '',
                'black': float(master.black) if master.black is not None else '',
                'total_concentration': float(master.total_concentration) if master.total_concentration is not None else '',
                'colormatch_date': master.colormatch_date.strftime('%m/%d/%Y') if master.colormatch_date else '',
            })

            if f_type == 'MB':
                ingredients = [{'material': m.material_code, 'value': float(m.concentration or 0), 'weight': 0} for m in materials_info]
                payload.update({'formula_type': 'MB', 'source': 'master', 'ingredients': ingredients})
                return payload
            elif f_type == 'DC':
                material_rows = []
                for m in materials_info:
                    # For DC master formula, we pass the concentration directly into V1, rest 0
                    versions = [float(m.concentration or 0)] + [0] * 9
                    material_rows.append({'material': m.material_code, 'versions': versions})
                payload.update({'formula_type': 'DC', 'source': 'master', 'material_rows': material_rows})
                return payload

    return None

def ajax_lookup_formula_by_code(request):
    product_code = request.GET.get('product_code', '').strip()
    formula_type = request.GET.get('formula_type', 'MB').strip()
    cm_no = request.GET.get('cm_no', '').strip()

    if not product_code:
        return JsonResponse({'found': False, 'error': 'Product code is required.'}, status=400)

    data = get_matching_formula_by_product_code(product_code, formula_type, cm_no)
    if data:
        return JsonResponse({'found': True, 'data': data})
    
    return JsonResponse({'found': False})