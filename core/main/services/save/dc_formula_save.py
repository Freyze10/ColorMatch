import json
from decimal import Decimal
from datetime import datetime, date
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from main.utils.log_audit_trail import log_audit
from ...models import (
    tbl_cmf, tbl_rs, tbl_generated_prod_code,
    tbl_dc_extruder_formula, tbl_dc_extruder_materials, tbl_dc_extruder_version,
    tbl_coding_materials
)

MAX_MATERIAL_ROWS = 10
MAX_VERSIONS = 10

User = get_user_model()
def save_dc_complete_formula(request):
    post_data = request.POST
    formula_id = post_data.get('formula_id')
    record_type = post_data.get('record_type', 'cmf')

    def clean_num(val):
        if val is None:
            return None
        v = str(val).strip()
        return v if v else None

    def format_val(val):
        if val is None or val == "" or val == "None":
            return "---"
        if isinstance(val, (Decimal, float)):
            return format(float(val), ".4f")
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
        }
        return mapping.get(field, field.replace('_', ' ').title())

    try:
        with transaction.atomic():
            # 1. Resolve Product Code
            prod_code_str = post_data.get('product_code', '').strip()
            prod_code_obj, _ = tbl_generated_prod_code.objects.get_or_create(product_code=prod_code_str) if prod_code_str else (None, False)

            # Resolve Personnel (The new Matcher Account)
            matcher_id = post_data.get('matcher_id')
            matcher_obj = User.objects.filter(pk=matcher_id).first() if matcher_id else None
            
            # Also get the full name string to keep 'matched_by' updated
            matched_by_text = matcher_obj.get_full_name() if matcher_obj else ""

            # Resolve Material Code Instance
            mat_code_id = post_data.get('material_code_id')
            mat_code_obj = tbl_coding_materials.objects.filter(pk=mat_code_id).first() if mat_code_id else None

            # 2. Resolve Parent
            cmf_obj = None
            rs_obj = None
            cm_display = ""

            if record_type == 'rs':
                rs_obj = tbl_rs.objects.get(pk=post_data.get('record_id'))
                cm_display = rs_obj.rs_no
                dosage_val = clean_num(post_data.get('dosage'))
                if dosage_val is not None:
                    rs_obj.dosage = dosage_val
                    rs_obj.save(update_fields=['dosage'])
            else:
                cmf_obj = tbl_cmf.objects.get(cm_no=post_data.get('record_id'))
                cm_display = cmf_obj.cm_no

            # 3. Standardize Date
            raw_date = post_data.get('date_matched')
            formatted_date = datetime.strptime(raw_date, '%m/%d/%Y').date() if raw_date else None

            # 4. Header Data
            header_params = {
                'date': formatted_date,
                'cm_no': cmf_obj,
                'rs_no': rs_obj,
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
            

            # --- Capture old materials/versions BEFORE any changes, for
            # the audit-log diff comparison further down.
            old_snapshot = []
            if formula_id:
                header = tbl_dc_extruder_formula.objects.get(pk=formula_id)
                old_snapshot = list(
                    tbl_dc_extruder_version.objects
                    .filter(material__dc=header)
                    .select_related('material')
                    .values('material__material', 'version_no', 'value')
                )

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
                action_type = "Updated"
            else:
                header = tbl_dc_extruder_formula.objects.create(**header_params)
                action_type = "Saved"

            # --- MATERIALS & VERSIONS ---
            # Delete-and-recreate, same pattern as the original ingredients
            # logic: whatever grid cells were actually filled in on submit
            # become the new source of truth. A material added only under
            # version 3, for example, simply has no version rows for 1-2
            # because those cells were left blank — no explicit "no
            # relation" bookkeeping needed beyond that.
            tbl_dc_extruder_version.objects.filter(material__dc=header).delete()
            tbl_dc_extruder_materials.objects.filter(dc=header).delete()

            new_snapshot = []
            for row in range(1, MAX_MATERIAL_ROWS + 1):
                mat_name = post_data.get(f'material_{row}', '').strip()
                if not mat_name:
                    continue

                material_obj = tbl_dc_extruder_materials.objects.create(dc=header, material=mat_name)

                for version_no in range(1, MAX_VERSIONS + 1):
                    raw_val = clean_num(post_data.get(f'value_{row}_{version_no}'))
                    if raw_val is None:
                        continue
                    value_decimal = Decimal(raw_val)
                    tbl_dc_extruder_version.objects.create(
                        material=material_obj,
                        version_no=version_no,
                        value=value_decimal,
                    )
                    new_snapshot.append({
                        'material__material': mat_name,
                        'version_no': version_no,
                        'value': value_decimal,
                    })
            # Audit Diff Comparison
            def _norm(snapshot):
                return sorted(
                    (s['material__material'], s['version_no'], str(s['value']))
                    for s in snapshot
                )

            ingredients_changed = _norm(old_snapshot) != _norm(new_snapshot)

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

            log_audit(request, action_type, msg)
            return header

    except Exception as e:
        raise Exception(f"Database Error: {str(e)}")