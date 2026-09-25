from datetime import datetime
from django.db.models import Q, Max, OuterRef, Subquery
from django.views.decorators.http import require_POST
from django.db import transaction
from django.core.cache import cache
from django.http import JsonResponse
from main.utils.log_audit_trail import log_audit
from ...models import (
    tbl_cmf, tbl_cmf_formula, tbl_cmf_dates, 
    tbl_cmf_pending_completed, tbl_cmf_salesman, tbl_customer, tbl_dc_extruder_formula, tbl_dc_extruder_materials, tbl_dc_extruder_version, tbl_generated_prod_code, tbl_internal_color_code, tbl_mb_extruder_formula, tbl_mb_extruder_formula02, tbl_resin, tbl_rm_incoming, tbl_rs
)

def get_salesman_list():
    data = cache.get('salesman_list')
    if not data:
        # If not there, get from DB and save for 1 day
        data = list(tbl_cmf_salesman.objects.all().order_by('name'))
        cache.set('salesman_list', data, 86400)
    return data

def get_color_list():
    data = cache.get('color_list')
    if not data:
        data = list(tbl_internal_color_code.objects.all().order_by('color'))
        cache.set('color_list', data, 86400)
    return data

def get_resin_list():
    data = cache.get('resin_list')
    if not data:
        data = list(tbl_resin.objects.filter(is_deleted=False).order_by('abbreviation'))
        cache.set('resin_list', data, 86400)
    return data

def get_color_code_list():
    data = cache.get('code_list')
    if not data:
        data = list(tbl_generated_prod_code.objects.all().order_by('code_no'))
        cache.set('code_list', data, 86400)
    return data

def get_customer_list():
    """
    Fetches the list of unique customer names from tbl_customer.
    Uses caching to avoid hitting the database on every page load.
    """
    data = cache.get('customer_list')
    if not data:
        # Fetch just the names as a list of strings, sorted alphabetically
        data = list(
            tbl_customer.objects.values_list('customer', flat=True)
            .order_by('customer')
        )
        # Cache for 24 hours (86400 seconds)
        cache.set('customer_list', data, 86400)
    return data

# def get_cmf_records():
#     cached_data = cache.get('cmf_records_list')
#     if cached_data is not None:
#         return cached_data

#     # Added 'code' to select_related for efficiency
#     status_records = tbl_cmf_pending_completed.objects.filter(
#         cm_no__isnull=False
#     ).select_related('cm_no', 'code').order_by('-cm_no')
    
#     results = []
#     for entry in status_records:
#         cmf = entry.cm_no
#         formula = tbl_cmf_formula.objects.filter(cm_no=cmf.cm_no).first()
#         dates = tbl_cmf_dates.objects.filter(cm_no=cmf.cm_no).first()

#         results.append({
#             "id": cmf.cm_no,
#             "no": cmf.cm_no,
#             "customer": formula.customer if formula else "---",
#             "primary_color": cmf.in_code_no.color if cmf.in_code_no else "---",
#             "description": cmf.color_desc or "---",
#             "product": formula.finished_product if formula else "---",
#             "required_date": dates.date_required if dates else "---",
#             "target_date": dates.due_date_lab.strftime('%m/%d/%y') if (dates and dates.due_date_lab) else "---",
#             "type": cmf.matching_type or "---",
#             "colorant_type": cmf.colorant_type or "---",
#             # Updated: Access string via the new 'code' ForeignKey
#             "code": entry.code.product_code if entry.code else "---",
#             "status": "Completed" if entry.is_completed else "Pending",
#             "submitted_date": entry.date_submitted.strftime('%m/%d/%y') if entry.date_submitted else "",
#             "ar_no": entry.ar_no or "",
#             "reason": entry.reason or "",
#             "mode": "cmf"
#         })

#     final_results = sorted(results, key=lambda x: x['no'], reverse=True)
#     cache.set('cmf_records_list', final_results, 3600)
#     return final_results

def get_raw_material_codes():
    """
    Fetches all unique material codes from tbl_rm_incoming.
    Uses caching to avoid heavy database hits.
    """
    cache_key = 'raw_material_codes'
    materials = cache.get(cache_key)

    if materials is None:
        # We use values_list with flat=True to get a simple list of strings
        # We use distinct() to avoid duplicates and order_by for easier searching in UI
        materials = list(
            tbl_rm_incoming.objects.values_list('material_code', flat=True)
            .distinct()
            .order_by('material_code')
        )
        
        # Cache the result for 1 hour (3600 seconds)
        cache.set(cache_key, materials, 3600)

    return materials

# def get_all_records_combined():
#     """
#     Returns all CMF and RS records loaded once for instant JS filtering.
#     """
#     # return get_cmf_records() + get_rs_records()
#     return get_cmf_records()


@require_POST
def toggle_final_formula(request, formula_type, formula_id):
    model = tbl_mb_extruder_formula if formula_type == 'mb' else tbl_dc_extruder_formula
    
    # Optimization: select_related parent objects so audit log doesn't trigger extra DB hits
    header = model.objects.filter(pk=formula_id).select_related('code', 'cm_no', 'rs_no').first()

    if not header:
        return JsonResponse({'success': False, 'error': 'Formula record not found.'}, status=404)

    with transaction.atomic():
        if header.is_final:
            # 1. REMOVE FINAL STATUS
            header.is_final = False
            header.save(update_fields=['is_final'])
            is_final_now = False
            new_status_code = None
        else:
            # 2. SET AS FINAL
            # Unset any other formula marked final for the SAME parent record
            if header.cm_no_id:
                model.objects.filter(cm_no=header.cm_no).exclude(pk=header.pk).update(is_final=False)
            elif header.rs_no_id:
                model.objects.filter(rs_no=header.rs_no).exclude(pk=header.pk).update(is_final=False)

            header.is_final = True
            header.save(update_fields=['is_final'])
            is_final_now = True
            new_status_code = header.code

        # --- UPDATE PENDING/COMPLETED STATUS RECORD ---
        # We perform the update directly on the queryset. 
        # No need to fetch 'status_record' into a variable first.
        if header.cm_no_id:
            tbl_cmf_pending_completed.objects.filter(cm_no=header.cm_no).update(code=new_status_code)
        elif header.rs_no_id:
            tbl_cmf_pending_completed.objects.filter(rs_no=header.rs_no).update(code=new_status_code)

        # --- PREPARE AUDIT MESSAGE ---
        # Determine formula identifier (Lot for MB, Product Code for DC)
        if formula_type == 'mb':
            formula_id_display = f"Lot: {header.lot_no or 'N/A'}"
        else:
            formula_id_display = f"Code: {header.code.product_code if header.code else 'N/A'}"

        # Determine parent identifier (CMF No or RS No)
        parent_display = header.cm_no.cm_no if header.cm_no else (header.rs_no.rs_no if header.rs_no else "Unknown")

        action = "Marked" if is_final_now else "Unmarked"
        audit_msg = f"{action} {formula_type.upper()} formula ({formula_id_display}) as Final for {parent_display}."

        log_audit(request, "Updated", audit_msg)

    # Clear caches
    cache.delete('cmf_records_list')
    cache.delete('rs_records_list')
    
    return JsonResponse({'success': True, 'is_final': is_final_now})



# Formula Records Retrieval for CMF and RS

# Mapped 1-to-1 with DataTables column indices
SEARCHABLE_COLUMNS = {
    1: 'date_display',
    2: 'cmf_no',
    3: 'customer',
    4: 'product_code',
    5: 'lot_no',
    6: 'color',
    7: 'dosage_display',
}

SORTABLE_COLUMNS = {
    1: 'date',
    2: 'cmf_no',
    3: 'customer',
    4: 'product_code',
    5: 'lot_no',
    6: 'color',
    7: 'dosage',
}


def get_all_formula_records():
    # 1. Preload customer and dosage from tbl_cmf_formula in 1 query for instant O(1) lookup
    formula_map = {}
    for f in tbl_cmf_formula.objects.all().only('cm_no', 'customer', 'dosage'):
        if f.cm_no_id:
            formula_map[str(f.cm_no_id)] = f

    mb_qs = tbl_mb_extruder_formula.objects.select_related('code', 'cm_no')
    dc_qs = tbl_dc_extruder_formula.objects.select_related('code', 'cm_no')

    combined_results = []

    # MB Formulas
    for f in mb_qs:
        cm_obj = f.cm_no
        cmf_no = cm_obj.cm_no if cm_obj else "N/A"
        color = cm_obj.color_desc if (cm_obj and cm_obj.color_desc) else "---"
        
        f_info = formula_map.get(str(cm_obj.cm_no)) if cm_obj else None
        customer = f_info.customer if f_info and f_info.customer else "---"
        raw_dosage = f_info.dosage if f_info else None
        dosage_display = f"{float(raw_dosage):g}%" if raw_dosage is not None else "---"

        combined_results.append({
            "id": f.mb_no,
            "type": "MB",
            "date": f.date,
            "cmf_no": cmf_no,
            "record_type": "cmf",
            "record_no": cmf_no if cmf_no != "N/A" else "",
            "customer": customer,
            "product_code": f.code.product_code if f.code else "---",
            "lot_no": f.lot_no or "N/A",
            "color": color,
            "dosage": float(raw_dosage) if raw_dosage is not None else None,
            "dosage_display": dosage_display,
            "html": f.html or "#ffffff"
        })

    # DC Formulas
    for f in dc_qs:
        cm_obj = f.cm_no
        cmf_no = cm_obj.cm_no if cm_obj else "N/A"
        color = cm_obj.color_desc if (cm_obj and cm_obj.color_desc) else "---"

        f_info = formula_map.get(str(cm_obj.cm_no)) if cm_obj else None
        customer = f_info.customer if f_info and f_info.customer else "---"
        raw_dosage = f_info.dosage if f_info else None
        dosage_display = f"{float(raw_dosage):g}%" if raw_dosage is not None else "---"

        combined_results.append({
            "id": f.dc_no,
            "type": "DC",
            "date": f.date,
            "cmf_no": cmf_no,
            "record_type": "cmf",
            "record_no": cmf_no if cmf_no != "N/A" else "",
            "customer": customer,
            "product_code": f.code.product_code if f.code else "---",
            "lot_no": "N/A",
            "color": color,
            "dosage": float(raw_dosage) if raw_dosage is not None else None,
            "dosage_display": dosage_display,
            "html": f.html or "#ffffff"
        })

    return combined_results


def formula_records_data(request):
    draw = int(request.GET.get('draw', 1))
    start = int(request.GET.get('start', 0))
    length = int(request.GET.get('length', 100))
    global_search = request.GET.get('search[value]', '').strip()

    all_records = get_all_formula_records()
    total_unfiltered = len(all_records)

    for item in all_records:
        item['date_display'] = item['date'].strftime('%m/%d/%Y') if item['date'] else "---"

    # --- Per-column search ---
    active_column_filters = {}
    for idx, field in SEARCHABLE_COLUMNS.items():
        val = request.GET.get(f'columns[{idx}][search][value]', '').strip()
        if val:
            active_column_filters[field] = val.lower()

    if active_column_filters:
        filtered = [
            item for item in all_records
            if all(query in str(item.get(field, '')).lower() for field, query in active_column_filters.items())
        ]
    elif global_search:
        query = global_search.lower()
        filtered = [
            item for item in all_records
            if any(query in str(item.get(field, '')).lower() for field in SEARCHABLE_COLUMNS.values())
        ]
    else:
        filtered = all_records

    # --- Sorting: read DataTables' order[0][column] / order[0][dir] ---
    order_col_index = request.GET.get('order[0][column]')
    order_dir = request.GET.get('order[0][dir]', 'asc')

    sort_field = None
    if order_col_index is not None:
        sort_field = SORTABLE_COLUMNS.get(int(order_col_index))

    if sort_field:
        filtered.sort(
            key=lambda item: (item.get(sort_field) is None, item.get(sort_field) or ''),
            reverse=(order_dir == 'desc')
        )
    else:
        # Fallback: original default (date desc), for the very first
        # load or if an unmapped column index somehow comes through.
        filtered.sort(
            key=lambda x: x['date'] if x['date'] else datetime.min.date(),
            reverse=True
        )

    total_filtered = len(filtered)
    paginated_list = filtered[start: start + length]

    return JsonResponse({
        "draw": draw,
        "recordsTotal": total_unfiltered,
        "recordsFiltered": total_filtered,
        "data": paginated_list
    })


def get_formula_materials(request, formula_type, formula_id):
    """
    Fetches ingredients for the breakdown panel. 
    For DC, it pulls the latest trial (highest version_no).
    """
    results = []

    if formula_type.upper() == 'MB':
        # MB formula items
        results = list(
            tbl_mb_extruder_formula02.objects
            .filter(mb_id=formula_id)
            .values('material', 'value', 'weight')
        )
    
    else:
        # DC LOGIC: Find latest trial/version
        # 1. Identify the highest version number for this DC formula
        max_v = tbl_dc_extruder_version.objects.filter(
            material__dc_id=formula_id
        ).aggregate(Max('version_no'))['version_no__max']

        if max_v is not None:
            # 2. Pull materials and values for that latest version
            version_data = tbl_dc_extruder_version.objects.filter(
                material__dc_id=formula_id, 
                version_no=max_v
            ).select_related('material').order_by('id')

            for v in version_data:
                val = float(v.value or 0)
                results.append({
                    'material': v.material.material if v.material else '---',
                    'value': val,
                    'weight': val  # Pass val to weight so JS parseFloat(m.weight) displays the true value
                })

    return JsonResponse({'materials': results})


#
# new cmf records

# DataTables sends the column POSITION it's ordering/searching by (0-based,
# left to right as drawn in <thead>). These lists are indexed by that
# position and must stay in the same order as the <th> elements in the
# template.
ORDER_COLUMNS = [
    'cm_no__cm_no',                # 0 - id (hidden)
    'cm_no__cm_no',                # 1 - CMF No.
    'customer',                    # 2 - Customer (annotated)
    'cm_no__in_code_no__color',    # 3 - Primary Color
    'cm_no__color_desc',           # 4 - Color Description
    'finished_product',            # 5 - Finished Product (annotated)
    'date_required',               # 6 - Required Date (annotated)
    'due_date_lab',                # 7 - Target Date (annotated)
    'cm_no__matching_type',        # 8 - Matching Type
    'cm_no__colorant_type',        # 9 - Colorant
    'code__product_code',          # 10 - Product Code
    'is_completed',                # 11 - Status
    'date_submitted',              # 12 - Submitted Date
    'ar_no',                       # 13 - AR No.
    'reason',                      # 14 - Reason
]
 
# Maps the search-field dropdown's <option value="..."> (unchanged from
# the template) to the ORM path(s) to search when that option is picked.
SEARCH_FIELDS = {
    '0': ['cm_no__cm_no'],
    '1': ['customer'],
    '2': ['cm_no__in_code_no__color'],
    '3': ['cm_no__color_desc'],
    '4': ['finished_product'],
    '5': ['date_required'],
    '6': ['due_date_lab'],
    '7': ['cm_no__matching_type'],
    '8': ['code__product_code'],
    '10': ['date_submitted'],
    '11': ['ar_no'],
    '12': ['reason'],
    '13': ['cm_no__colorant_type'],
    # '9' (Status) is deliberately absent — status is a boolean driven by
    # the Completed/Pending checkboxes, not free text. See special-case
    # handling below.
}
ALL_SEARCH_FIELDS = sorted({f for fields in SEARCH_FIELDS.values() for f in fields})
 
 
def _base_queryset():
    """The efficient replacement for the old per-row .first() lookups."""
    formula_sub = tbl_cmf_formula.objects.filter(cm_no=OuterRef('cm_no__cm_no'))
    dates_sub = tbl_cmf_dates.objects.filter(cm_no=OuterRef('cm_no__cm_no'))
 
    return tbl_cmf_pending_completed.objects.filter(
        cm_no__isnull=False
    ).select_related('cm_no', 'code', 'cm_no__in_code_no').annotate(
        customer=Subquery(formula_sub.values('customer')[:1]),
        finished_product=Subquery(formula_sub.values('finished_product')[:1]),
        date_required=Subquery(dates_sub.values('date_required')[:1]),
        due_date_lab=Subquery(dates_sub.values('due_date_lab')[:1]),
    )
 
 
def get_cmf_records_page(*, show_completed, show_pending, search_col,
                          search_term, order_col, order_dir, start, length):
    """
    Returns (total_count, filtered_count, page) where `page` is a list of
    dicts in the same shape the old get_cmf_records() produced (minus the
    'mode' key, since this is CMF-only now).
    """
    qs = _base_queryset()
    total_count = qs.count()
 
    # --- Status filter (Completed / Pending checkboxes) ---
    if show_completed and not show_pending:
        qs = qs.filter(is_completed=True)
    elif show_pending and not show_completed:
        qs = qs.filter(is_completed=False)
    elif not show_completed and not show_pending:
        qs = qs.none()
 
    # --- Free-text search ---
    search_term = (search_term or '').strip()
    if search_term:
        if search_col == '9':
            # Status column: match against the word, not a boolean icontains.
            lowered = search_term.lower()
            if 'complet' in lowered:
                qs = qs.filter(is_completed=True)
            elif 'pend' in lowered:
                qs = qs.filter(is_completed=False)
            else:
                qs = qs.none()
        else:
            fields = ALL_SEARCH_FIELDS if search_col == 'all' else SEARCH_FIELDS.get(search_col, [])
            if fields:
                q = Q()
                for f in fields:
                    q |= Q(**{f'{f}__icontains': search_term})
                qs = qs.filter(q)
 
    filtered_count = qs.count()
 
    # --- Ordering ---
    if 0 <= order_col < len(ORDER_COLUMNS):
        order_field = ORDER_COLUMNS[order_col]
    else:
        order_field = 'cm_no__cm_no'
    if order_dir == 'desc':
        order_field = f'-{order_field}'
    qs = qs.order_by(order_field)
 
    page_qs = qs[start:start + length]
 
    page = []
    for entry in page_qs:
        cmf = entry.cm_no
        page.append({
            "id": cmf.cm_no,
            "no": cmf.cm_no,
            "customer": entry.customer or "---",
            "primary_color": cmf.in_code_no.color if cmf.in_code_no else "---",
            "description": cmf.color_desc or "---",
            "product": entry.finished_product or "---",
            "required_date": entry.date_required or "---",
            "target_date": entry.due_date_lab.strftime('%m/%d/%y') if entry.due_date_lab else "---",
            "type": cmf.matching_type or "---",
            "colorant_type": cmf.colorant_type or "---",
            "code": entry.code.product_code if entry.code else "---",
            "status": "Completed" if entry.is_completed else "Pending",
            "submitted_date": entry.date_submitted.strftime('%m/%d/%y') if entry.date_submitted else "",
            "ar_no": entry.ar_no or "",
            "reason": entry.reason or "",
        })
 
    return total_count, filtered_count, page


def cmf_records_data(request):
    draw = int(request.GET.get('draw', 1))
    start = int(request.GET.get('start', 0))
    length = int(request.GET.get('length', 25))
    order_col = int(request.GET.get('order[0][column]', 1))
    order_dir = request.GET.get('order[0][dir]', 'desc')
 
    show_completed = request.GET.get('status_completed', 'true') == 'true'
    show_pending = request.GET.get('status_pending', 'true') == 'true'
    search_col = request.GET.get('search_col', 'all')
    search_term = request.GET.get('search_term', '')
 
    total_count, filtered_count, page = get_cmf_records_page(
        show_completed=show_completed,
        show_pending=show_pending,
        search_col=search_col,
        search_term=search_term,
        order_col=order_col,
        order_dir=order_dir,
        start=start,
        length=length,
    )
 
    return JsonResponse({
        "draw": draw,
        "recordsTotal": total_count,
        "recordsFiltered": filtered_count,
        "data": page,
    })