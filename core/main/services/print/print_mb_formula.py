import os
from decimal import Decimal
from django.shortcuts import render
from django.contrib import messages
from django.http import HttpResponse, HttpResponseNotFound, HttpResponseServerError, JsonResponse
from django.views.decorators.clickjacking import xframe_options_exempt

from main.utils.log_audit_trail import log_audit
from main.models import (
    tbl_mb_extruder_formula, tbl_mb_extruder_formula02,
    tbl_cmf_formula, tbl_resins_selected, tbl_formula_resin_selected
)

# Material rows: one row per material, up to 10.
MATERIAL_MAX_ROWS = 10


def _fetch_mb_formula_data(formula_id):
    """
    Pulls the header, its ingredient rows, and related CMF details
    strictly for CMF (all RS references decoupled).
    """
    header = tbl_mb_extruder_formula.objects.select_related('cm_no', 'code').get(pk=formula_id)
    ingredients = list(
        tbl_mb_extruder_formula02.objects.filter(mb=header).order_by('id')[:MATERIAL_MAX_ROWS]
    )

    customer = ""
    color = ""
    resin = ""
    application = ""
    dosage = ""
    parent_no = ""

    if header.cm_no:
        parent_no = header.cm_no.cm_no
        color = header.cm_no.color_desc or ""

        formula_info = tbl_cmf_formula.objects.filter(cm_no=header.cm_no).first()
        if formula_info:
            customer = formula_info.customer or ""
            application = formula_info.finished_product or ""
            dosage = formula_info.dosage

        # 1. First check if a formula-specific resin was saved
        saved_resins = list(
            tbl_formula_resin_selected.objects.filter(mb_no=header)
            .select_related('formula_resin_id')
            .values_list('formula_resin_id__resin', flat=True)
        )

        if saved_resins:
            resin = ", ".join(saved_resins)
        else:
            # 2. Fallback to CMF resin selection
            resin = ", ".join(
                tbl_resins_selected.objects.filter(cm_no=header.cm_no)
                .values_list('resin_no__abbreviation', flat=True)
            )

    return {
        'header': header,
        'ingredients': ingredients,
        'customer': customer,
        'color': color,
        'resin': resin,
        'application': application,
        'dosage': dosage,
        'parent_no': parent_no,
    }


def _to_num(val):
    """Safely converts None/''/Decimal/str into float, defaulting to 0."""
    if val is None or val == "" or str(val).strip().upper() in ('NONE', 'NA', 'N/A'):
        return 0
    if isinstance(val, Decimal):
        return float(val)
    try:
        return float(str(val).replace('%', '').strip())
    except (TypeError, ValueError):
        return 0


@xframe_options_exempt
def print_mb_formula(request, formula_id):
    """
    Renders the MB Formula as plain HTML/CSS (Letter size) for native
    browser print preview.
    """
    try:
        data = _fetch_mb_formula_data(formula_id)
    except tbl_mb_extruder_formula.DoesNotExist:
        return HttpResponseNotFound(f"MB Formula '{formula_id}' was not found.")

    header = data['header']
    ingredients = data['ingredients']

    # Pad ingredient rows to a fixed 10 rows
    rows = []
    for i in range(MATERIAL_MAX_ROWS):
        if i < len(ingredients):
            ing = ingredients[i]
            val_num = _to_num(ing.value)
            wgt_num = _to_num(ing.weight)

            # 🛑 8 DECIMAL PLACES FOR VALUE AND WEIGHT
            rows.append({
                'material': ing.material or '',
                'value': f"{val_num:.8f}" if ing.value not in (None, '') else '',
                'weight': f"{wgt_num:.8f}" if ing.weight not in (None, '') else '',
            })
        else:
            rows.append({'material': '', 'value': '', 'weight': ''})

    total_value = sum((Decimal(str(ing.value or 0)) for ing in ingredients), Decimal('0'))
    total_wgt = _to_num(header.total_weight)

    # 🛑 6 DECIMAL PLACES FOR DOSAGE
    dosage_val = data['dosage']
    if dosage_val not in (None, '', 0, '0'):
        formatted_dosage = f"{_to_num(dosage_val):.6f}%"
    else:
        formatted_dosage = ''

    context = {
        'date': header.date.strftime('%m/%d/%Y') if header.date else '',
        'cm_form_no': data['parent_no'],
        'product_code': header.code.product_code if header.code else '',
        'resin_used': data['resin'],
        'customer': data['customer'],
        'dosage': formatted_dosage,                                # 6 decimal places
        'lot_number': header.lot_no or '',
        'mixing_time': header.mixing_time or '',
        'color': data['color'],
        'application': data['application'],
        'rows': rows,
        'total_value': f"{_to_num(total_value):.8f}",              # 8 decimal places
        'total_weight': f"{total_wgt:.8f}" if total_wgt > 0 else '', # 8 decimal places
        'matched_by': header.matched_by or '',
        'weighed_by': header.weighted_by or '',
        'encoded_by': header.encoded_by or '',
        'note': header.notes or '',
    }
    return render(request, "print-html/mb_formula_print.html", context)


def log_formula_print(request, formula_id):
    try:
        formula = tbl_mb_extruder_formula.objects.get(pk=formula_id)
        desc = f"Printed MB Formula (Lot: {formula.lot_no or 'N/A'})"

        log_audit(request, "Printed", desc)
        return JsonResponse({'status': 'success'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)