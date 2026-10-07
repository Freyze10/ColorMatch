import json
from decimal import Decimal, InvalidOperation
from datetime import datetime, date
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from main.utils.log_audit_trail import log_audit
from ...models import (
    tbl_cmf, tbl_formula_resin, tbl_formula_resin_selected, tbl_generated_prod_code,
    tbl_dc_extruder_formula, tbl_dc_extruder_materials, tbl_dc_extruder_version,
    tbl_coding_materials, tbl_cmf_formula
)

MAX_MATERIAL_ROWS = 10
MAX_VERSIONS = 10

def parse_dosage(raw_val):
    """Converts numeric inputs to Decimal, saves 'NA'/'N/A'/non-numeric as None (NULL)."""
    if not raw_val:
        return None
    cleaned = str(raw_val).replace('%', '').strip()
    if cleaned.upper() in ('NA', 'N/A', 'NONE'):
        return None
    try:
        return Decimal(cleaned)
    except (ValueError, TypeError, InvalidOperation):
        return None

User = get_user_model()
def save_dc_complete_formula(request):
    post_data = request.POST
    formula_id = post_data.get('formula_id')

    def clean_num(val):
        if val is None:
            return None
        v = str(val).strip()
        return v if v else None

    def format_val(val):
        if val is None or val == "" or val == "None":
            return "---"
        if isinstance(val, (Decimal, float)):
            return format(float(val), ".8f")
        if isinstance(val, (date, datetime)):
            return val.strftime('%m/%d/%Y')
        return str(val).strip()

    def get_pretty_name(field):
        mapping = {
            'date': 'Date Matched', 'sample_size': 'Sample Size',
            'mixing_time': 'Mixing Time', 'matched_by': 'Matched By',
            'weighted_by': 'Weighed By', 'encoded_by': 'Encoded By',
            'total_weight': 'Total Weight', 'html': 'sRGB Hex',
            'L': 'Spectro L', 'A': 'Spectro A', 'B': 'Spectro B',
            'C': 'Spectro C', 'H': 'Spectro H', 'notes': 'Note',
            'code': 'Product Code', 'material_code': 'Material Code',
            'matcher': 'Matcher Account', 'is_final': 'Final Formula',
            'cm_no': 'CMF No.',
        }
        return mapping.get(field, field.replace('_', ' ').title())

    try:
        with transaction.atomic():
            # 1. Resolve Product Code
            prod_code_str = post_data.get('product_code', '').strip()
            prod_code_obj, _ = tbl_generated_prod_code.objects.get_or_create(product_code=prod_code_str) if prod_code_str else (None, False)
            print(prod_code_str, prod_code_obj)
            # Resolve Personnel (The new Matcher Account)
            matcher_id = post_data.get('matcher_id')
            matcher_obj = User.objects.filter(pk=matcher_id).first() if matcher_id else None
            
            # Also get the full name string to keep 'matched_by' updated
            matched_by_text = matcher_obj.get_full_name() if matcher_obj else ""

            # Resolve Material Code Instance
            mat_code_id = post_data.get('material_code_id')
            mat_code_obj = tbl_coding_materials.objects.filter(pk=mat_code_id).first() if mat_code_id else None

            # 2. RESOLVE CMF (Checks 'cmf_number' from HTML select/input, then fallbacks)
            raw_cm_no = (
                post_data.get('cmf_number') or 
                post_data.get('record_id') or 
                post_data.get('cm_no') or 
                ''
            ).strip()

            cmf_obj = None
            if raw_cm_no and raw_cm_no.upper() != 'N/A':
                cmf_obj = tbl_cmf.objects.filter(cm_no=raw_cm_no).first()

            cm_display = cmf_obj.cm_no if cmf_obj else (raw_cm_no or "N/A")

            # 3. Standardize Date
            raw_date = post_data.get('date_matched')
            formatted_date = datetime.strptime(raw_date, '%m/%d/%Y').date() if raw_date else None

            # 4. RESOLVE RESINS (EXISTING ID OR NEW CUSTOM ENTRY)
            posted_resins_raw = post_data.getlist('formula_resin')
            posted_resin_ids = []

            for raw_val in posted_resins_raw:
                val_str = str(raw_val).strip()
                if not val_str:
                    continue

                if val_str.isdigit():
                    # Existing Resin ID
                    r_id = int(val_str)
                    if tbl_formula_resin.objects.filter(pk=r_id).exists():
                        posted_resin_ids.append(r_id)
                else:
                    # New Custom Resin Entry -> Check if already exists (case-insensitive) or create new
                    existing_r = tbl_formula_resin.objects.filter(resin__iexact=val_str).first()
                    if existing_r:
                        posted_resin_ids.append(existing_r.formula_resin_id)
                    else:
                        new_r = tbl_formula_resin.objects.create(resin=val_str)
                        posted_resin_ids.append(new_r.formula_resin_id)

            # 5. Header Data
            header_params = {
                'date': formatted_date,
                'cm_no': cmf_obj,
                'code': prod_code_obj,
                'material_code': mat_code_obj,
                'sample_size': post_data.get('sample_size'),
                'mixing_time': post_data.get('mixing_time'),
                'notes': post_data.get('note'),
                'matcher': matcher_obj,      # NEW: User Object
                'matched_by': matched_by_text, 
                'weighted_by': post_data.get('weighed_by'),
                'encoded_by': post_data.get('encoded_by'),
                'total_weight': Decimal(clean_num(post_data.get('total_weight')) or 0),
                'L': clean_num(post_data.get('spectro_l')),
                'A': clean_num(post_data.get('spectro_a')),
                'B': clean_num(post_data.get('spectro_b')),
                'C': clean_num(post_data.get('spectro_c')),
                'H': clean_num(post_data.get('spectro_h')),
                'html': post_data.get('srgb_hex'),
                'c': clean_num(post_data.get('cmyk_c')),
                'm': clean_num(post_data.get('cmyk_m')),
                'y': clean_num(post_data.get('cmyk_y')),
                'k': clean_num(post_data.get('cmyk_k')),
                'is_final': post_data.get('is_final') == 'true',
            }

            diff_logs = []

            # --- 5.5 SYNC DOSAGE BACK TO THE CMF-LEVEL FORMULA RECORD ---
            if cmf_obj:
                cmf_formula = tbl_cmf_formula.objects.filter(cm_no=cmf_obj).order_by('-cmf_formula_no').first()
                if cmf_formula:
                    posted_dosage = parse_dosage(post_data.get('dosage'))

                    is_different = False
                    if cmf_formula.dosage is None and posted_dosage is not None:
                        is_different = True
                    elif cmf_formula.dosage is not None and posted_dosage is None:
                        is_different = True
                    elif cmf_formula.dosage is not None and posted_dosage is not None:
                        is_different = (cmf_formula.dosage != posted_dosage)

                    if is_different:
                        old_disp = format_val(cmf_formula.dosage) if cmf_formula.dosage is not None else "NA"
                        new_disp = format_val(posted_dosage) if posted_dosage is not None else "NA"
                        diff_logs.append(f"CMF Dosage ({old_disp} -> {new_disp})")
                        cmf_formula.dosage = posted_dosage
                        cmf_formula.save(update_fields=['dosage'])

            # =========================================================
            # 6. CAPTURE EXISTING DATA BEFORE SAVING (FOR ACCURATE DIFF)
            # =========================================================
            old_materials_map = {}

            if formula_id:
                header = tbl_dc_extruder_formula.objects.get(pk=formula_id)

                # Capture existing materials & non-zero values: {(mat_name, version_no): round(val, 4)}
                existing_versions = tbl_dc_extruder_version.objects.filter(
                    material__dc=header
                ).select_related('material')

                for v in existing_versions:
                    m_name = (v.material.material or '').strip().lower()
                    val_float = float(v.value or 0)
                    if m_name and round(val_float, 4) != 0:
                        key = (m_name, v.version_no)
                        old_materials_map[key] = round(old_materials_map.get(key, 0.0) + val_float, 4)

                # Track Header Changes
                for field, new_val in header_params.items():
                    current_val = getattr(header, field)
                    if field == 'code':
                        curr_str = format_val(current_val.product_code if current_val else "")
                        new_str = format_val(new_val.product_code if new_val else "")
                    elif field == 'material_code':
                        curr_str = format_val(current_val.name if current_val else "")
                        new_str = format_val(new_val.name if new_val else "")
                    elif field in ['cm_no', 'rs_no']:
                        continue
                    else:
                        curr_str, new_str = format_val(current_val), format_val(new_val)

                    if curr_str != new_str:
                        diff_logs.append(f"{get_pretty_name(field)} ({curr_str} -> {new_str})")
                        setattr(header, field, new_val)
                header.save()

                # --- TRACK & SAVE RESIN SELECTION CHANGES ---
                existing_resins = list(
                    tbl_formula_resin_selected.objects.filter(dc_no=header)
                    .select_related('formula_resin_id')
                )
                existing_resin_ids = [r.formula_resin_id.pk for r in existing_resins]

                if set(existing_resin_ids) != set(posted_resin_ids):
                    old_names = [r.formula_resin_id.resin for r in existing_resins if r.formula_resin_id]
                    new_names = list(
                        tbl_formula_resin.objects.filter(formula_resin_id__in=posted_resin_ids)
                        .values_list('resin', flat=True)
                    )
                    # diff_logs.append(
                    #     f"Resin Used ({', '.join(old_names) or '---'} -> {', '.join(new_names) or '---'})"
                    # )

                    # Replace old selections with new selections
                    tbl_formula_resin_selected.objects.filter(dc_no=header).delete()
                    new_records = [
                        tbl_formula_resin_selected(dc_no=header, formula_resin_id_id=rid)
                        for rid in posted_resin_ids
                    ]
                    tbl_formula_resin_selected.objects.bulk_create(new_records)
                action_type = "Updated"
            else:
                header = tbl_dc_extruder_formula.objects.create(**header_params)
                # Save Selected Resins
                if posted_resin_ids:
                    new_records = [
                        tbl_formula_resin_selected(dc_no=header, formula_resin_id_id=rid)
                        for rid in posted_resin_ids
                    ]
                    tbl_formula_resin_selected.objects.bulk_create(new_records)
                action_type = "Saved"

            # =========================================================
            #  PARSE SUBMITTED MATERIALS & VERSIONS
            # =========================================================
            new_materials_map = {}

            # Clear old records to write the new grid
            tbl_dc_extruder_version.objects.filter(material__dc=header).delete()
            tbl_dc_extruder_materials.objects.filter(dc=header).delete()

            for row in range(1, MAX_MATERIAL_ROWS + 1):
                mat_name = post_data.get(f'material_{row}', '').strip()
                if not mat_name:
                    continue

                material_obj = tbl_dc_extruder_materials.objects.create(dc=header, material=mat_name)

                for version_no in range(1, MAX_VERSIONS + 1):
                    raw_val = clean_num(post_data.get(f'value_{row}_{version_no}'))
                    if raw_val is None:
                        continue
                    try:
                        val_float = float(raw_val)
                        value_decimal = Decimal(raw_val)
                    except (ValueError, TypeError):
                        continue

                    tbl_dc_extruder_version.objects.create(
                        material=material_obj,
                        version_no=version_no,
                        value=value_decimal,
                    )

                    # Only track non-zero values in the comparison map
                    if round(val_float, 4) != 0:
                        key = (mat_name.lower(), version_no)
                        new_materials_map[key] = round(new_materials_map.get(key, 0.0) + val_float, 4)

            # Strict Numerical Comparison: ignores zeros and decimal precision formatting
            ingredients_changed = (old_materials_map != new_materials_map)

            # --- FINAL LOGGING ---
            code_display = prod_code_obj.product_code if prod_code_obj else "---"

            if action_type == "Updated":
                msg = f"DC Formula (CMF: {cm_display} | Code: {code_display} ). "
                if not diff_logs and not ingredients_changed:
                    msg += "No technical changes."
                else:
                    if diff_logs:
                        msg += f"Changes: {', '.join(diff_logs)}. "
                    if ingredients_changed:
                        msg += "Material composition updated."
            else:
                msg = f"New DC Formula (CMF: {cm_display} | Code: {code_display} )."
                if diff_logs:
                    msg += f" Changes: {', '.join(diff_logs)}."

            log_audit(request, action_type, msg)
            return header

    except Exception as e:
        raise Exception(f"Database Error: {str(e)}")