from datetime import datetime, date
from decimal import Decimal
import json
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from main.utils.log_audit_trail import log_audit
from ...models import (
    tbl_cmf, tbl_rs, tbl_generated_prod_code,
    tbl_mb_extruder_formula, tbl_mb_extruder_formula02
)
User = get_user_model()

def save_mb_complete_formula(request):
    post_data = request.POST
    formula_id = post_data.get('formula_id')
    record_type = post_data.get('record_type', 'cmf')

    # --- 1. HELPERS ---
    def clean_num(val):
        if val is None: return None
        v = str(val).strip()
        return v if v else None

    def format_val(val):
        """Standardizes values to readable strings for audit comparison."""
        if val is None or val == "" or val == "None": return "---"
        if isinstance(val, (Decimal, float)):
            return format(float(val), ".6f")
        if isinstance(val, (date, datetime)):
            return val.strftime('%m/%d/%Y')
        return str(val).strip()

    def get_pretty_name(field):
        mapping = {
            'lot_no': 'Lot Number', 'mixing_time': 'Mixing Time',
            'matched_by': 'Matched By', 'weighted_by': 'Weighed By',
            'encoded_by': 'Encoded By', 'total_weight': 'Total Weight',
            'html': 'sRGB Hex', 'L': 'Spectro L', 'A': 'Spectro A',
            'B': 'Spectro B', 'C': 'Spectro C', 'H': 'Spectro H',
            'notes': 'Note', 'code': 'Product Code', 'date': 'Date',
            'matcher': 'Matcher Account', 'is_final': 'Final Formula',
        }
        return mapping.get(field, field.replace('_', ' ').title())

    try:
        with transaction.atomic():
            # 1. Resolve Product Code
            prod_code_str = post_data.get('product', '').strip()
            prod_code_obj, _ = tbl_generated_prod_code.objects.get_or_create(product_code=prod_code_str) if prod_code_str else (None, False)

            # Resolve Personnel (The new Matcher Account)
            matcher_id = post_data.get('matcher_id')
            matcher_obj = User.objects.filter(pk=matcher_id).first() if matcher_id else None
            
            # Also get the full name string to keep 'matched_by' updated
            matched_by_text = matcher_obj.get_full_name() if matcher_obj else ""

            # 2. Resolve Parent
            cmf_obj = None
            rs_obj = None
            parent_label = ""
            if record_type == 'rs':
                rs_obj = tbl_rs.objects.get(pk=post_data.get('record_id'))
                parent_label = f"RS: {rs_obj.rs_no}"
                dosage_val = clean_num(post_data.get('dosage'))
                if dosage_val is not None:
                    rs_obj.dosage = dosage_val
                    rs_obj.save(update_fields=['dosage'])
            else:
                cmf_obj = tbl_cmf.objects.get(cm_no=post_data.get('record_id'))
                parent_label = f"CMF: {cmf_obj.cm_no}"

            # 3. Standardize Date
            raw_date = post_data.get('date')
            formatted_date = datetime.strptime(raw_date, '%m/%d/%Y').date() if raw_date else None

            # 4. Header Params
            header_params = {
                'date': formatted_date,
                'cm_no': cmf_obj,
                'rs_no': rs_obj,
                'code': prod_code_obj,
                'lot_no': post_data.get('lot_number'),
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
            }

            diff_logs = []
            ingredients_changed = False

            if formula_id:
                header = tbl_mb_extruder_formula.objects.get(pk=formula_id)
                
                # --- TRACK HEADER CHANGES ---
                for field, new_val in header_params.items():
                    current_val = getattr(header, field)
                    
                    # Logic for FK Display
                    if field == 'code':
                        curr_str = format_val(current_val.product_code if current_val else "")
                        new_str = format_val(new_val.product_code if new_val else "")
                    elif field in ['cm_no', 'rs_no']:
                        continue # These are usually fixed parent references
                    else:
                        curr_str = format_val(current_val)
                        new_str = format_val(new_val)

                    if curr_str != new_str:
                        diff_logs.append(f"{get_pretty_name(field)} ({curr_str} -> {new_str})")
                        setattr(header, field, new_val)
                header.save()

                # --- TRACK INGREDIENT CHANGES ---
                old_ings = list(tbl_mb_extruder_formula02.objects.filter(mb=header).values('material', 'value', 'weight'))
                
                new_ings = []
                for i in range(1, 11):
                    mat = post_data.get(f'material_{i}', '').strip()
                    if mat:
                        new_ings.append({
                            'material': mat,
                            'value': Decimal(clean_num(post_data.get(f'percentage_{i}')) or 0),
                            'weight': Decimal(clean_num(post_data.get(f'weight_{i}')) or 0)
                        })

                # Deep compare lists
                if json.dumps([(i['material'], str(i['value']), str(i['weight'])) for i in old_ings]) != \
                   json.dumps([(i['material'], str(i['value']), str(i['weight'])) for i in new_ings]):
                    ingredients_changed = True
                    tbl_mb_extruder_formula02.objects.filter(mb=header).delete()
                    for ing in new_ings:
                        tbl_mb_extruder_formula02.objects.create(mb=header, **ing)

                action_type = "Updated"
            else:
                header = tbl_mb_extruder_formula.objects.create(**header_params)
                for i in range(1, 11):
                    mat = post_data.get(f'material_{i}', '').strip()
                    if mat:
                        tbl_mb_extruder_formula02.objects.create(
                            mb=header,
                            material=mat,
                            value=clean_num(post_data.get(f'percentage_{i}')) or 0,
                            weight=clean_num(post_data.get(f'weight_{i}')) or 0
                        )
                action_type = "Saved"

            # --- FINAL LOGGING ---
            lot_display = header.lot_no if header.lot_no else "N/A"
            if action_type == "Updated":
                if not diff_logs and not ingredients_changed:
                    msg = f"MB Formula (Lot: {lot_display}) with no technical changes."
                else:
                    msg = f"MB Formula (Lot: {lot_display}). Changes: " + ", ".join(diff_logs)
                    if ingredients_changed:
                        msg += " (Material Breakdown was modified)."
            else:
                msg = f"New MB Formula (Lot: {lot_display}) for {parent_label}."

            log_audit(request, action_type, msg)
            return header

    except IntegrityError:
        raise Exception("The Lot Number provided already exists.")
    except Exception as e:
        raise Exception(f"Database Error: {str(e)}")