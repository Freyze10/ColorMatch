from datetime import datetime, date
from decimal import Decimal, InvalidOperation
import json
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.utils import cache
from main.utils.log_audit_trail import log_audit
from ...models import (
    tbl_cmf, tbl_cmf_formula, tbl_cmf_pending_completed, tbl_formula_resin, tbl_formula_resin_selected, tbl_generated_prod_code, tbl_internal_color_code,
    tbl_mb_extruder_formula, tbl_mb_extruder_formula02, tbl_standalone_formula, tbl_standalone_formula_resins
)
User = get_user_model()

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
            return format(float(val), ".8f")
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
            'internal_color': 'Internal Color', 'index_no': 'Index Ref. No.',
        }
        return mapping.get(field, field.replace('_', ' ').title())

    # Normalizer for materials: ignores 0 values and formats numbers identically
    def _norm_ings(ing_list):
        normalized = []
        for item in ing_list:
            m_name = (item.get('material') or '').strip().lower()
            try:
                val_f = round(float(item.get('value') or 0), 8)
            except (ValueError, TypeError):
                val_f = 0.0
            try:
                wgt_f = round(float(item.get('weight') or 0), 8)
            except (ValueError, TypeError):
                wgt_f = 0.0

            # Only track if material exists and either value or weight is non-zero
            if m_name and (val_f != 0 or wgt_f != 0):
                normalized.append((m_name, val_f, wgt_f))
        return sorted(normalized)

    LOT_EXEMPT = {'NA', 'NONE'}
    lot_no = (post_data.get('lot_number') or '').strip()

    if lot_no and lot_no.upper() not in LOT_EXEMPT:
        dup = tbl_mb_extruder_formula.objects.filter(lot_no=lot_no)
        if formula_id:
            dup = dup.exclude(pk=formula_id)
        if dup.exists():
            raise Exception("The Lot Number provided already exists.")
        
    try:
        with transaction.atomic():
            # 1. Resolve Color Selection First
            color_id = post_data.get('color')
            color_obj = tbl_internal_color_code.objects.filter(pk=color_id).first() if color_id else None

            # 2. Resolve Product Code and bind the internal color code relation
            prod_code_str = post_data.get('product', '').strip()
            prod_code_obj = None
            
            if prod_code_str:
                # Use update_or_create or get_or_create while explicitly passing/updating in_code
                prod_code_obj, created = tbl_generated_prod_code.objects.get_or_create(
                    product_code=prod_code_str,
                    defaults={'in_code': color_obj}
                )
                # If the product code already existed in tbl_generated_prod_code but lacked an in_code link, update it:
                if not created and color_obj and not prod_code_obj.in_code:
                    prod_code_obj.in_code = color_obj
                    prod_code_obj.save(update_fields=['in_code'])

            # Resolve Personnel (The new Matcher Account)
            matcher_id = post_data.get('matcher_id')
            matcher_obj = User.objects.filter(pk=matcher_id).first() if matcher_id else None
            
            # Also get the full name string to keep 'matched_by' updated
            matched_by_text = matcher_obj.get_full_name() if matcher_obj else ""

            # 2. Resolve Parent (Strictly CMF / Standalone 'N/A')
            raw_cm_no = (
                post_data.get('cmf_number') or 
                post_data.get('record_id') or 
                post_data.get('cm_no') or 
                ''
            ).strip()

            cmf_obj = None
            is_na_record = raw_cm_no.upper() in ('N/A', 'NA', 'NONE')

            if raw_cm_no and not is_na_record:
                cmf_obj = tbl_cmf.objects.filter(cm_no=raw_cm_no).first()

            parent_label = f"CMF: {cmf_obj.cm_no}" if cmf_obj else f"CMF: {raw_cm_no or 'N/A'}"

            diff_logs = []

            # NOTE: the selected color is saved on the FORMULA itself (internal_color, see header_params).
            # The CMF keeps its own (primary) color; it is no longer overwritten from the formula form.

            # 3. Standardize Date
            raw_date = post_data.get('date')
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

            # --- TOTAL WEIGHT: number, or "NONE" -> stored as NULL ---
            raw_total_weight = (post_data.get('total_weight') or '').strip()
            is_none_weight = raw_total_weight.upper() == 'NONE'

            if is_none_weight:
                total_weight_val = None
            else:
                try:
                    total_weight_val = Decimal(raw_total_weight or 0)
                except InvalidOperation:
                    raise ValueError("Total Weight must be a number or NONE.")

            # 5. Header Params]
            is_final_val = post_data.get('is_final') == 'true'
            
            # --- 2. SET AS FINAL: Unset any OTHER formula marked final for the SAME parent record ---
            # The formula being saved is excluded: otherwise it is reset to False here, and the audit
            # trail reports "Final Formula (False -> True)" on every save of a formula that is already final.
            if is_final_val and cmf_obj:
                others = tbl_mb_extruder_formula.objects.filter(cm_no=cmf_obj)
                if formula_id:
                    others = others.exclude(pk=formula_id)
                others.update(is_final=False)

            header_params = {
                'index_no': post_data.get('index_no'),
                'date': formatted_date,
                'cm_no': cmf_obj,
                'code': prod_code_obj,
                'internal_color': color_obj,   # NEW: the color picked in this formula
                'customer_color': post_data.get('color_desc'),
                'lot_no': lot_no,
                'mixing_time': post_data.get('mixing_time'),
                'notes': post_data.get('note'),
                'matcher': matcher_obj,      # NEW: User Object
                'matched_by': matched_by_text, 
                'weighted_by': post_data.get('weighed_by'),
                'encoded_by': post_data.get('encoded_by'),
                'total_weight': total_weight_val,
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
                'is_final': is_final_val,
            }

            ingredients_changed = False

            # --- 5.5 SYNC DOSAGE BACK TO THE CMF-LEVEL FORMULA RECORD ---
            # touch it (and only log it) if the posted value actually
            # differs from what's on file.
            if cmf_obj:
                cmf_formula = tbl_cmf_formula.objects.filter(cm_no=cmf_obj).order_by('-cmf_formula_no').first()
                if cmf_formula:
                    posted_dosage = parse_dosage(post_data.get('dosage'))
                    
                    # Safe comparison handling Decimal vs None
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
            # Gather newly submitted ingredient rows
            new_ings = []
            for i in range(1, 11):
                mat = post_data.get(f'material_{i}', '').strip()
                if mat:
                    new_ings.append({
                        'material': mat,
                        'value': Decimal(clean_num(post_data.get(f'percentage_{i}')) or 0),
                        'weight': None if is_none_weight
                                else Decimal(clean_num(post_data.get(f'weight_{i}')) or 0),
                    })

            if formula_id:
                header = tbl_mb_extruder_formula.objects.get(pk=formula_id)
                
                # --- TRACK HEADER CHANGES ---
                for field, new_val in header_params.items():
                    current_val = getattr(header, field)
                    
                    # Logic for FK Display
                    if field == 'code':
                        curr_str = format_val(current_val.product_code if current_val else "")
                        new_str = format_val(new_val.product_code if new_val else "")
                    elif field == 'internal_color':
                        curr_str = format_val(current_val.color if current_val else "")
                        new_str = format_val(new_val.color if new_val else "")
                    elif field == 'total_weight':
                        curr_str = 'NONE' if current_val is None else format_val(current_val)
                        new_str = 'NONE' if new_val is None else format_val(new_val)
                    elif field in ['cm_no', 'rs_no']:
                        continue # These are usually fixed parent references
                    else:
                        curr_str = format_val(current_val)
                        new_str = format_val(new_val)

                    if curr_str != new_str:
                        diff_logs.append(f"{get_pretty_name(field)} ({curr_str} -> {new_str})")
                        setattr(header, field, new_val)
                header.save()

                # --- TRACK & SAVE RESIN SELECTION CHANGES ---
                existing_resins = list(
                    tbl_formula_resin_selected.objects.filter(mb_no=header)
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
                    tbl_formula_resin_selected.objects.filter(mb_no=header).delete()
                    new_records = [
                        tbl_formula_resin_selected(mb_no=header, formula_resin_id_id=rid)
                        for rid in posted_resin_ids
                    ]
                    tbl_formula_resin_selected.objects.bulk_create(new_records)
                
                # --- TRACK INGREDIENT CHANGES ---
                old_ings = list(tbl_mb_extruder_formula02.objects.filter(mb=header).values('material', 'value', 'weight'))
                # Compare ignoring zero/blank values and rounding discrepancies
                ingredients_changed = _norm_ings(old_ings) != _norm_ings(new_ings)

                if ingredients_changed:
                    tbl_mb_extruder_formula02.objects.filter(mb=header).delete()
                    for ing in new_ings:
                        tbl_mb_extruder_formula02.objects.create(mb=header, **ing)

                action_type = "Updated"
            else:
                header = tbl_mb_extruder_formula.objects.create(**header_params)
                 # Save Selected Resins
                if posted_resin_ids:
                    new_records = [
                        tbl_formula_resin_selected(mb_no=header, formula_resin_id_id=rid)
                        for rid in posted_resin_ids
                    ]
                    tbl_formula_resin_selected.objects.bulk_create(new_records)

                for ing in new_ings:
                    tbl_mb_extruder_formula02.objects.create(mb=header, **ing)
                    
                action_type = "Saved"

             # --- ADDED: HANDLE STANDALONE FORMULA DETAILS (If N/A was selected) ---
            
            if is_na_record:
                standalone_defaults = {
                    'customer': post_data.get('customer'),
                    'dosage': parse_dosage(post_data.get('dosage')),
                    'finished_product': post_data.get('finished_product'),
                    'process': post_data.get('application'),
                }
                
                standalone_obj, _ = tbl_standalone_formula.objects.update_or_create(
                    mb_no=header,
                    defaults=standalone_defaults
                )
                
                tbl_standalone_formula_resins.objects.filter(standalone=standalone_obj).delete()
                if posted_resin_ids:
                    sa_resins = [
                        tbl_standalone_formula_resins(standalone=standalone_obj, resin_no_id=rid)
                        for rid in posted_resin_ids
                    ]
                    tbl_standalone_formula_resins.objects.bulk_create(sa_resins)
            else:
                tbl_standalone_formula.objects.filter(mb_no=header).delete()

            # --- UPDATE PENDING/COMPLETED STATUS RECORD BASED ON IS_FINAL ---
            new_status_code = header.code if header.is_final else None
            if header.cm_no_id:
                tbl_cmf_pending_completed.objects.filter(cm_no=header.cm_no).update(code=new_status_code)

            # --- FINAL LOGGING ---
            lot_display = header.lot_no if header.lot_no else "N/A"
            if action_type == "Updated":
                msg = f"MB Formula (Lot: {lot_display}) for {parent_label}."
                if not diff_logs and not ingredients_changed:
                    msg += " No technical changes."
                else:
                    if diff_logs:
                        msg += " Changes: " + ", ".join(diff_logs)
                    if ingredients_changed:
                        if diff_logs:
                            msg += " (Material Breakdown was modified)."
                        else:
                            msg += " Changes: Material Breakdown was modified."
            else:
                msg = f"New MB Formula (Lot: {lot_display}) for {parent_label}."
                if diff_logs:
                    msg += " Changes: " + ", ".join(diff_logs)

            log_audit(request, action_type, msg)
            return header

    except IntegrityError:
        raise Exception("The Lot Number provided already exists.")
    except Exception as e:
        raise Exception(f"Database Error: {str(e)}")