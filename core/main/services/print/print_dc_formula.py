import os
from decimal import Decimal
from django.shortcuts import render
from django.http import HttpResponseNotFound, JsonResponse
from django.views.decorators.clickjacking import xframe_options_exempt

from main.utils.log_audit_trail import log_audit
from main.models import (
    tbl_dc_extruder_formula, tbl_dc_extruder_materials, tbl_dc_extruder_version,
    tbl_cmf_formula, tbl_resins_selected, tbl_formula_resin_selected
)

MATERIAL_MAX_ROWS = 10
MAX_VERSIONS = 10


def _fetch_dc_formula_data(formula_id):
    """
    Pulls the header, its materials/version values, and related CMF details
    strictly for CMF (all RS references decoupled).
    """
    header = tbl_dc_extruder_formula.objects.select_related('cm_no', 'code').get(pk=formula_id)

    dc_materials = list(
        tbl_dc_extruder_materials.objects.filter(dc=header).order_by('material_id')[:MATERIAL_MAX_ROWS]
    )

    # Build {material_id: {version_no: value}} lookup
    versions_by_material = {
        m.material_id: {v.version_no: v.value for v in m.versions.all()}
        for m in dc_materials
    }

    customer = ""
    color = ""
    resin = ""
    application = ""
    finished_product = ""
    parent_no = ""
    dosage = ""

    if header.cm_no:
        parent_no = header.cm_no.cm_no
        color = header.cm_no.color_desc or ""

        formula_info = tbl_cmf_formula.objects.filter(cm_no=header.cm_no).first()
        if formula_info:
            customer = formula_info.customer or ""
            application = formula_info.finished_product or ""
            finished_product = formula_info.finished_product or ""
            dosage = formula_info.dosage

        # 1. First check if a formula-specific resin was saved
        saved_resins = list(
            tbl_formula_resin_selected.objects.filter(dc_no=header)
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
        'dc_materials': dc_materials,
        'versions_by_material': versions_by_material,
        'customer': customer,
        'color': color,
        'dosage': dosage,
        'resin': resin,
        'application': application,
        'finished_product': finished_product,
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
def print_dc_formula(request, formula_id):
    """
    Renders the DC Formula as plain HTML/CSS (Letter landscape) for
    native browser print preview.
    """
    try:
        data = _fetch_dc_formula_data(formula_id)
    except tbl_dc_extruder_formula.DoesNotExist:
        return HttpResponseNotFound(f"DC Formula '{formula_id}' was not found.")

    header = data['header']
    dc_materials = data['dc_materials']
    versions_by_material = data['versions_by_material']

    # Fixed 10x10 grid: rows = materials, cols = trial versions 1-10
    rows = []
    version_totals = {v: Decimal('0') for v in range(1, MAX_VERSIONS + 1)}

    for i in range(MATERIAL_MAX_ROWS):
        if i < len(dc_materials):
            m = dc_materials[i]
            v_values = versions_by_material.get(m.material_id, {})
            cells = []
            for v_no in range(1, MAX_VERSIONS + 1):
                val = v_values.get(v_no)
                if val is not None and str(val).strip() != "" and _to_num(val) != 0:
                    # 🛑 8 DECIMAL PLACES FOR CELL VALUES
                    cells.append(f"{_to_num(val):.8f}")
                    version_totals[v_no] += Decimal(str(val))
                else:
                    cells.append("")
            rows.append({'material': m.material or '', 'cells': cells})
        else:
            rows.append({'material': '', 'cells': [''] * MAX_VERSIONS})

    # 🛑 8 DECIMAL PLACES FOR TOTALS ROW
    totals_row = [
        f"{_to_num(version_totals[v]):.8f}" if version_totals[v] != 0 else ""
        for v in range(1, MAX_VERSIONS + 1)
    ]

    # 🛑 6 DECIMAL PLACES FOR DOSAGE
    dosage_val = data['dosage']
    if dosage_val not in (None, '', 0, '0') and str(dosage_val).strip().upper() not in ('NONE', 'NA', 'N/A'):
        formatted_dosage = f"{_to_num(dosage_val):.6f}%"
    elif str(dosage_val).strip().upper() in ('NA', 'N/A'):
        formatted_dosage = "NA"
    else:
        formatted_dosage = ""

    context = {
        'formula_id': formula_id,
        'code': header.code.product_code if header.code else "",
        'cmf': data['parent_no'],
        'customer': data['customer'],
        'resin': data['resin'],
        'color': data['color'],
        'date_matched': header.date.strftime('%m/%d/%Y') if header.date else "",
        'dosage': formatted_dosage,                                # 6 decimal places
        'sample_size': header.sample_size or "",
        'product_used': data['finished_product'],
        'mixing_time': header.mixing_time or "",
        'application': data['application'],
        'note': header.notes or "",
        'matched_by': header.matched_by or "",
        'weighed_by': header.weighted_by or "",
        'encoded_by': header.encoded_by or "",
        'rows': rows,                                              # 8 decimal places
        'totals_row': totals_row,                                  # 8 decimal places
    }
    return render(request, "print-html/dc_formula_print.html", context)


def log_formula_print(request, formula_id):
    try:
        formula = tbl_dc_extruder_formula.objects.get(pk=formula_id)
        desc = f"Printed DC Formula (Code: {formula.code.product_code if formula.code else 'N/A'})"

        log_audit(request, "Printed", desc)
        return JsonResponse({'status': 'success'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)