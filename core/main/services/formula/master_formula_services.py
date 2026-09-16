from django.contrib import messages
from django.core.cache import cache
from django.db.models.functions import Concat
from django.shortcuts import get_object_or_404
from django.utils import timezone
import json
from datetime import datetime
from django.db import transaction
from django.http import JsonResponse
from django.db.models import Q, Max, Value
from django.shortcuts import render
from main.utils.log_audit_trail import log_audit
from main.services.cmf_records import cmf_records_services
from django.views.decorators.clickjacking import xframe_options_exempt
from main.models import (
    tbl_cmf_formula, tbl_cmf_process02, tbl_dc_extruder_formula, tbl_dc_extruder_materials, tbl_dc_extruder_version, 
    tbl_master_formula, tbl_master_formula_info, tbl_master_formula_encode, 
    tbl_cmf, tbl_mb_extruder_formula, tbl_mb_extruder_formula02, tbl_resins_selected, tbl_rs
)
from django.contrib.auth import get_user_model 
User = get_user_model()

CACHE_TIMEOUT = 3600  # 1 hour

# --- 1. DATA RETRIEVAL (FOR ENTRY/EDIT) ---

def get_master_formula_details(form_id):
    """Fetches full details for a single master formula."""
    formula = tbl_master_formula.objects.filter(pk=form_id, is_deleted=False).first()
    if not formula:
        return None

    # Helper function to strip trailing zeros and the decimal point if whole number
    def clean_num(val):
        if val is None or val == "":
            return "0"
        try:
            # Convert to float and use %g formatter 
            # %g automatically removes trailing zeros and dots
            # Example: 10.00000 -> "10", 0.23000 -> "0.23"
            return format(float(val), 'g')
        except (ValueError, TypeError):
            return val

    is_locked = False
    if formula.date:
        # If the record is more than 3 days old, lock it
        # .days > 3 means on the 4th day it becomes read-only
        if (timezone.now().date() - formula.date).days > 3:
            is_locked = True

    encode = tbl_master_formula_encode.objects.filter(form=formula).first()
    materials = list(
        tbl_master_formula_info.objects.filter(form=formula, is_deleted=False)
        .order_by('sequence_no')
        .values('material_code', 'concentration')
    )

    return {
        'form_id': formula.form_id,
        'index_no': formula.index_no or '',
        'date': formula.date.strftime('%m/%d/%Y') if formula.date else '',
        'is_locked': is_locked,
        'customer': formula.customer or '',
        'product_code': formula.product_code or '',
        'prod_color': formula.prod_color or '',
        'total_concentration': format(formula.total_concentration or 0, ".6f"),
        'sum_of_concentration': format(formula.dosage or 0, ".6f"),
        'dosage': format(formula.ld or 0, ".6f"),
        'mix_time': formula.mix_time or '',
        'resin': formula.resin or '',
        'application': formula.application or '',
        'cm_no': formula.cm_no or 'N/A',
        'colormatch_date': formula.colormatch_date.strftime('%m/%d/%Y') if formula.colormatch_date else '',
        'notes': formula.notes or '---',
        'html_code_hex': formula.html_code_hex or '',
        'cyan': clean_num(formula.cyan),
        'magenta': clean_num(formula.magenta),
        'yellow': clean_num(formula.yellow),
        'black': clean_num(formula.black),
        'updated_by': encode.updated_by if encode else '',
        'updated_time': formula.date_modified or '',
        'matched_by': encode.match_by if encode else '',
        'encoded_by': encode.encoded_by if encode else '',
        'materials': materials,
        'colorant_type': formula.colorant_type or '',
    }

def get_all_matching_numbers():
    """Fetches unique CM/RS numbers for the TomSelect dropdown."""
    nos = cache.get('matching_numbers_list')
    if not nos:
        cmf_nos = list(tbl_cmf.objects.exclude(cm_no__isnull=True).exclude(cm_no='').values_list('cm_no', flat=True))
        rs_nos = list(tbl_rs.objects.exclude(rs_no__isnull=True).exclude(rs_no='').values_list('rs_no', flat=True))
        nos = sorted(list(set(cmf_nos + rs_nos)))
        cache.set('matching_numbers_list', nos, CACHE_TIMEOUT)
    return nos

def get_master_formula_context(form_id=None, request=None):
    """Context for the Master Formula page."""
    if form_id:
        form_data = get_master_formula_details(form_id)
    else:
        max_id = tbl_master_formula.objects.aggregate(Max('form_id'))['form_id__max'] or 0
        form_data = {'form_id': max_id + 1, 'is_new': True}

    user_list = list(
        User.objects.filter(is_active=True)
        .exclude(first_name="")
        .annotate(full_name=Concat('first_name', Value(' '), 'last_name'))
        .values_list('full_name', flat=True)
        .distinct()
        .order_by('full_name')
    )
    allowed_departments = ['Laboratory', 'Information Technology', 'Sales']
    is_allowed = request.user.role.department in allowed_departments or request.user.is_superuser
        
    return {
        'form_data': form_data,
        'matching_numbers': get_all_matching_numbers(),
        'users': user_list,
        'materials': cmf_records_services.get_raw_material_codes(),
        'customers': cmf_records_services.get_customer_list(),
        'is_allowed': is_allowed,
    }

# --- 2. DATA TABLES ---

def get_master_formula_records_json(request):
    """Server-side DataTables logic for Master Formula records."""
    draw = int(request.GET.get('draw', 1))
    start = int(request.GET.get('start', 0))
    length = int(request.GET.get('length', 1000))
    
    search_value = request.GET.get('search[value]', '').strip()
    search_col = request.GET.get('search_column', 'all') # New parameter
    
    queryset = tbl_master_formula.objects.filter(is_deleted=False)
    total_records = queryset.count()

    # Apply Column-Specific Search
    if search_value:
        if search_col == 'form_id':
            queryset = queryset.filter(form_id__icontains=search_value)
        elif search_col == 'index_no':
            queryset = queryset.filter(index_no__icontains=search_value)
        elif search_col == 'customer':
            queryset = queryset.filter(customer__icontains=search_value)
        elif search_col == 'product_code':
            queryset = queryset.filter(product_code__icontains=search_value)
        elif search_col == 'prod_color':
            queryset = queryset.filter(prod_color__icontains=search_value)
        else:
            # "All Fields" search (Default)
            queryset = queryset.filter(
                Q(form_id__icontains=search_value) |
                Q(index_no__icontains=search_value) |
                Q(customer__icontains=search_value) |
                Q(product_code__icontains=search_value) |
                Q(prod_color__icontains=search_value)
            )

    # Column Ordering (Kept Same)
    order_col = request.GET.get('order[0][column]', '0')
    order_dir = request.GET.get('order[0][dir]', 'desc')
    mapping = {'0': 'form_id', '1': 'index_no', '2': 'customer', '3': 'product_code', '4': 'prod_color'}
    sort_field = mapping.get(order_col, 'form_id')
    queryset = queryset.order_by(f"{'-' if order_dir == 'desc' else ''}{sort_field}")

    filtered_records = queryset.count()
    queryset = queryset[start:start + length]

    data = [{
        "form_id": row.form_id,
        "index_no": row.index_no or "-",
        "customer": row.customer or "-",
        "product_code": row.product_code or "-",
        "prod_color": row.prod_color or "-",
        "total_concentration": format(row.total_concentration or 0, ".6f"),
        "ld": format(row.ld or 0, ".6f"),
    } for row in queryset]

    return JsonResponse({"draw": draw, "recordsTotal": total_records, "recordsFiltered": filtered_records, "data": data})

# --- 3. PERSISTENCE (SAVE / AUDIT) ---

def save_master_formula(request):
    """
    Handles creating or updating a Master Formula with specific field mapping 
    and metadata persistence rules.
    """
    try:
        with transaction.atomic():
            data = request.POST
            form_id = data.get('form_id')
            is_new = data.get('is_new_flag') == 'true'
            
            # Format: "08/07/26 11:28:51 AM"
            timestamp_str = timezone.now().strftime('%m/%d/%y %I:%M:%S %p')
            
            diff_logs = []

            # 1. RESOLVE OR CREATE HEADER (tbl_master_formula)
            if not is_new and form_id:
                mf = tbl_master_formula.objects.get(pk=form_id)
                action_type = "Updated"
                
                # --- Audit Log Diff Logic ---
                field_map_for_logs = {
                    'customer': ('customer', 'Customer'),
                    'index_no': ('index_no', 'Index #'),
                    'product_code': ('product_code', 'Product Code'),
                    'prod_color': ('prod_color', 'Color'),
                    'sum_of_concentration': ('dosage', 'Sum of Con'), # dosage field holds sum
                    'dosage': ('ld', 'Dosage'),                       # ld field holds dosage
                    'mix_time': ('mix_time', 'Mixing Time'),
                    'resin': ('resin', 'Resin'),
                    'application': ('application', 'Application'),
                    'notes': ('notes', 'Notes'),
                    'html_code_hex': ('html_code_hex', 'Hex Code'),
                }

                for post_key, (model_attr, label) in field_map_for_logs.items():
                    old_val = str(getattr(mf, model_attr) or '').strip()
                    new_val = str(data.get(post_key) or '').strip()
                    if old_val != new_val:
                        diff_logs.append(f"{label}: {old_val} -> {new_val}")

                mf.date_modified = timestamp_str # Set specific timestamp string
            else:
                mf = tbl_master_formula()
                if form_id: 
                    mf.form_id = form_id 
                action_type = "Saved"
                mf.date = timezone.now().date()  # Set creation date
                mf.date_modified = "---"        # New formula gets triple dash
                mf.is_deleted = False
                mf.is_used = False

            # 2. MAP FIELDS (AS REQUESTED)
            mf.index_no = data.get('index_no')
            mf.customer = data.get('customer')
            mf.product_code = data.get('product_code')
            mf.prod_color = data.get('prod_color')
            
            # Requested Mappings:
            mf.dosage = data.get('sum_of_concentration') or 0   # Sum of Con -> dosage field
            mf.ld = data.get('dosage') or 0                   # Dosage -> ld field
            
            mf.total_concentration = data.get('total_concentration') or 0
            mf.mix_time = data.get('mix_time')
            mf.resin = data.get('resin')
            mf.application = data.get('application')
            mf.cm_no = data.get('cm_no')
            mf.notes = data.get('notes')
            mf.html_code_hex = data.get('html_code_hex')
            
            # CMYK Parsing
            mf.cyan = data.get('cyan') if data.get('cyan') else None
            mf.magenta = data.get('magenta') if data.get('magenta') else None
            mf.yellow = data.get('yellow') if data.get('yellow') else None
            mf.black = data.get('black') if data.get('black') else None
            
            dt_str = data.get('colormatch_date')
            if dt_str:
                try: 
                    mf.colormatch_date = datetime.strptime(dt_str, '%m/%d/%Y').date()
                except: 
                    pass
            mf.save()

            # 3. HANDLE MATERIALS (tbl_master_formula_info)
            tbl_master_formula_info.objects.filter(form=mf).delete()
            materials_json = data.get('materials_data')
            if materials_json:
                for i, mat in enumerate(json.loads(materials_json)):
                    tbl_master_formula_info.objects.create(
                        form=mf, 
                        sequence_no=i+1, 
                        material_code=mat['material'], 
                        concentration=mat['concentration']
                    )

            # 4. HANDLE METADATA (tbl_master_formula_encode)
            encode, created = tbl_master_formula_encode.objects.get_or_create(form=mf)
            
            # Get User Fullname
            user_fullname = f"{request.user.first_name} {request.user.last_name}".strip()
            if not user_fullname:
                user_fullname = request.user.username

            if is_new:
                # Save birth data only on new record
                encode.match_by = data.get('matched_by')
                encode.encoded_by = data.get('encoded_by') or user_fullname
                encode.updated_by = "---"
            else:
                # On update, only update the updated_by field
                encode.updated_by = user_fullname
            encode.save()

            # 5. UPDATE SOURCE REFERENCE
            source_pk, source_type = data.get('source_formula_pk'), data.get('source_formula_type')
            if source_pk and source_type:
                model = tbl_mb_extruder_formula if source_type == 'MB' else tbl_dc_extruder_formula
                model.objects.filter(pk=source_pk).update(in_master_formula=True)

            # 6. AUDIT TRAIL
            if is_new:
                log_message = f"New Master Formula Entry: #{mf.form_id}"
            else:
                details = ", ".join(diff_logs) if diff_logs else "No technical changes"
                log_message = f"Master Formula #{mf.form_id}. Changes: {details}"

            log_audit(request, action_type, log_message)
            return True, mf.form_id

    except Exception as e:
        return False, str(e)

# --- 4. LOOKUP ---
def master_formula_lookup(request):
    """Lookup logic. Returns MB formulas and only the LATEST Trial (Version) for each DC record."""
    matching_no = request.GET.get('matching_no', '').strip()
    error, mb_list, dc_list, color = None, [], [], ''
    parent = {'customer': '', 'resin_used': '', 'colorant_type': '', 'process': '', 'dosage': ''}

    if not matching_no:
        error = "No matching number provided."
    else:
        cmf = tbl_cmf.objects.filter(cm_no=matching_no).first()
        rs_records = tbl_rs.objects.filter(rs_no=matching_no) if not cmf else None

        if not cmf and (not rs_records or not rs_records.exists()):
            error = f'No records found for "{matching_no}".'
        else:
            if cmf:
                formula_info = tbl_cmf_formula.objects.filter(cm_no=cmf).first()
                parent.update({
                    'customer': formula_info.customer if formula_info else "",
                    'colorant_type': cmf.colorant_type or "",
                    'dosage': formula_info.dosage if formula_info else "",
                })
                parent['resin_used'] = ", ".join(tbl_resins_selected.objects.filter(cm_no=cmf).values_list('resin_no__abbreviation', flat=True))
                parent['process'] = ", ".join(tbl_cmf_process02.objects.filter(cmf_formula_no=formula_info).values_list('process_no__name', flat=True))
                mb_qs = tbl_mb_extruder_formula.objects.filter(cm_no=cmf).select_related('code')
                dc_qs = tbl_dc_extruder_formula.objects.filter(cm_no=cmf).select_related('code')
                color = cmf.in_code_no.color if cmf.in_code_no else (cmf.color_desc or '---')
            else:
                rs_ids = list(rs_records.values_list('id', flat=True))
                base_rs = rs_records.first()
                parent.update({
                    'customer': base_rs.customer or "",
                    'colorant_type': base_rs.colorant_type or "",
                    'dosage': getattr(base_rs, 'dosage', '') or '',
                })
                parent['resin_used'] = ", ".join(tbl_resins_selected.objects.filter(rs_no_id__in=rs_ids).values_list('resin_no__abbreviation', flat=True).distinct())
                parent['process'] = ", ".join(tbl_cmf_process02.objects.filter(rs_no_id__in=rs_ids).values_list('process_no__name', flat=True).distinct())
                mb_qs = tbl_mb_extruder_formula.objects.filter(rs_no_id__in=rs_ids).select_related('code')
                dc_qs = tbl_dc_extruder_formula.objects.filter(rs_no_id__in=rs_ids).select_related('code')
                color = base_rs.primary_color or base_rs.color_desc or '---'

            # PROCESS MB
            for f in mb_qs:
                ingredients = [{'material': i.material, 'value': float(i.value or 0)} 
                               for i in tbl_mb_extruder_formula02.objects.filter(mb=f)]
                mb_list.append({
                    'header': f, 'pk': f.pk, 'ingredients': ingredients,
                    'sum_con': format(sum(item['value'] for item in ingredients), ".6f"),
                    'script_id': f'mf-ing-mb-{f.pk}',
                    'cm_no': matching_no
                })

            # PROCESS DC (Only the Latest/Final Version per record)
            for f in dc_qs:
                # 1. Find the maximum version number that has data for this specific formula record
                max_v = tbl_dc_extruder_version.objects.filter(
                    material__dc=f
                ).aggregate(Max('version_no'))['version_no__max']

                if max_v is not None:
                    # 2. Get ingredients only for that specific highest version
                    version_rows = tbl_dc_extruder_version.objects.filter(
                        material__dc=f, 
                        version_no=max_v
                    ).select_related('material')

                    ingredients = [
                        {'material': v.material.material, 'value': float(v.value or 0)}
                        for v in version_rows if v.value is not None
                    ]

                    if ingredients:
                        dc_list.append({
                            'header': f, 
                            'pk': f.pk, 
                            'version_no': max_v, # Pass the version number to show "Trial #X" in UI
                            'ingredients': ingredients,
                            'sum_con': format(sum(item['value'] for item in ingredients), ".6f"),
                            'script_id': f'mf-ing-dc-{f.pk}', # Simplified ID as it's 1-to-1 with header now
                            'cm_no': matching_no
                        })

    return render(request, "modal/master-formula/master_formula_lookup.html", {
        'matching_no': matching_no, 'error': error, 'color': color, 'parent': parent,
        'mb_formulas': mb_list, 'dc_formulas': dc_list
    })




def print_master_formula(request, form_id):
    data = get_master_formula_details(form_id)
    if not data:
        return messages.error(f"Master Formula #{form_id} not found.")
    data['pdf_generated_on'] = timezone.now().strftime('%m/%d/%y %I:%M:%S %p')
    data['department_and_user'] = f"{request.user.role.department} # {request.user.username}"
    return render(request, "print-html/master_formula_print.html", {"f": data})

print_master_formula = xframe_options_exempt(print_master_formula)


def log_master_formula_print(request, formula_id):
    try:
        # Get the record from the database
        formula = get_object_or_404(tbl_master_formula, pk=formula_id)
        
        # Construct description for audit trail
        desc = f"Printed Master Formula (Form ID: {formula.form_id or 'N/A'})"

        # Call your existing log_audit function
        log_audit(request, "Printed", desc)
        
        return JsonResponse({'status': 'success'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

# lookup all the trials
# def master_formula_lookup(request):
#     """Lookup logic. Returns EACH Trial (Version) of a DC Formula as a separate entry."""
#     matching_no = request.GET.get('matching_no', '').strip()
#     error, mb_list, dc_list, color = None, [], [], ''
#     parent = {'customer': '', 'resin_used': '', 'colorant_type': '', 'process': '', 'dosage': ''}

#     if not matching_no:
#         error = "No matching number provided."
#     else:
#         cmf = tbl_cmf.objects.filter(cm_no=matching_no).first()
#         rs_records = tbl_rs.objects.filter(rs_no=matching_no) if not cmf else None

#         if not cmf and (not rs_records or not rs_records.exists()):
#             error = f'No records found for "{matching_no}".'
#         else:
#             if cmf:
#                 formula_info = tbl_cmf_formula.objects.filter(cm_no=cmf).first()
#                 parent.update({
#                     'customer': formula_info.customer if formula_info else "",
#                     'colorant_type': cmf.colorant_type or "",
#                     'dosage': formula_info.dosage if formula_info else "",
#                 })
#                 parent['resin_used'] = ", ".join(tbl_resins_selected.objects.filter(cm_no=cmf).values_list('resin_no__abbreviation', flat=True))
#                 parent['process'] = ", ".join(tbl_cmf_process02.objects.filter(cmf_formula_no=formula_info).values_list('process_no__name', flat=True))
#                 mb_qs = tbl_mb_extruder_formula.objects.filter(cm_no=cmf).select_related('code')
#                 dc_qs = tbl_dc_extruder_formula.objects.filter(cm_no=cmf).select_related('code')
#                 color = cmf.in_code_no.color if cmf.in_code_no else (cmf.color_desc or '---')
#             else:
#                 rs_ids = list(rs_records.values_list('id', flat=True))
#                 base_rs = rs_records.first()
#                 parent.update({
#                     'customer': base_rs.customer or "",
#                     'colorant_type': base_rs.colorant_type or "",
#                     'dosage': getattr(base_rs, 'dosage', '') or '',
#                 })
#                 parent['resin_used'] = ", ".join(tbl_resins_selected.objects.filter(rs_no_id__in=rs_ids).values_list('resin_no__abbreviation', flat=True).distinct())
#                 parent['process'] = ", ".join(tbl_cmf_process02.objects.filter(rs_no_id__in=rs_ids).values_list('process_no__name', flat=True).distinct())
#                 mb_qs = tbl_mb_extruder_formula.objects.filter(rs_no_id__in=rs_ids).select_related('code')
#                 dc_qs = tbl_dc_extruder_formula.objects.filter(rs_no_id__in=rs_ids).select_related('code')
#                 color = base_rs.primary_color or base_rs.color_desc or '---'

#             # PROCESS MB
#             for f in mb_qs:
#                 ingredients = [{'material': i.material, 'value': float(i.value or 0)} 
#                                for i in tbl_mb_extruder_formula02.objects.filter(mb=f)]
#                 mb_list.append({
#                     'header': f, 'pk': f.pk, 'ingredients': ingredients,
#                     'sum_con': format(sum(item['value'] for item in ingredients), ".6f"),
#                     'script_id': f'mf-ing-mb-{f.pk}',
#                     'cm_no': matching_no
#                 })

#             # PROCESS DC (Treating each version as a separate record)
#             for f in dc_qs:
#                 # 1. Identify all unique version numbers that have data for this formula
#                 existing_v = tbl_dc_extruder_version.objects.filter(
#                     material__dc=f
#                 ).values_list('version_no', flat=True).distinct().order_by('version_no')

#                 for v_no in existing_v:
#                     # 2. Get ingredients for this specific version iteration
#                     version_rows = tbl_dc_extruder_version.objects.filter(
#                         material__dc=f, 
#                         version_no=v_no
#                     ).select_related('material')

#                     ingredients = [
#                         {'material': v.material.material, 'value': float(v.value or 0)}
#                         for v in version_rows if v.value is not None
#                     ]

#                     if ingredients:
#                         dc_list.append({
#                             'header': f, 
#                             'pk': f.pk, 
#                             'version_no': v_no, # Used in the template to show "Trial #1"
#                             'ingredients': ingredients,
#                             'sum_con': format(sum(item['value'] for item in ingredients), ".6f"),
#                             'script_id': f'mf-ing-dc-{f.pk}-v{v_no}', # Unique ID for JS
#                             'cm_no': matching_no
#                         })

#     return render(request, "modal/master-formula/master_formula_lookup.html", {
#         'matching_no': matching_no, 'error': error, 'color': color, 'parent': parent,
#         'mb_formulas': mb_list, 'dc_formulas': dc_list
#     })

def master_formula_materials_json(request, form_id):
    """API for materials breakdown."""
    formula = tbl_master_formula.objects.filter(pk=form_id).first()
    if not formula: return JsonResponse({'error': 'Not found'}, status=404)
    materials = list(tbl_master_formula_info.objects.filter(form=formula, is_deleted=False)
                     .order_by('sequence_no').values('material_code', 'concentration'))
    return JsonResponse({'form_id': formula.form_id, 'index_no': formula.index_no or '-', 'customer': formula.customer or '', 'materials': materials})