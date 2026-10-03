#print_dc_formula
import os
# import tempfile
# import threading
# import uuid
from decimal import Decimal
from django.shortcuts import render
# import pythoncom
# import win32com.client as win32
# from django.contrib import messages
from django.http import HttpResponse, HttpResponseNotFound, HttpResponseServerError, JsonResponse
# from django.shortcuts import redirect
from django.views.decorators.clickjacking import xframe_options_exempt

from main.utils.log_audit_trail import log_audit
# from main.services.print.print_util import _resize_pdf_to_fixed_size
from main.models import (
    tbl_dc_extruder_formula, tbl_dc_extruder_materials, tbl_dc_extruder_version,
    tbl_cmf_formula, tbl_resins_selected,
)

# _word_lock = threading.Lock()

DC_TEMPLATE_PATH = os.path.join('main', 'templates', 'print_excel', 'dc_formula_template.docx')

DC_PDF_WIDTH_IN = 11.0   # Letter Width (Landscape)
DC_PDF_HEIGHT_IN = 8.5   # Letter Height (Landscape)

MATERIAL_START_ROW = 2   # row 1 is the header row ("MATERIAL", "1", "2", ..., "10")
MATERIAL_MAX_ROWS = 10
MAX_VERSIONS = 10
TOTAL_ROW = MATERIAL_START_ROW + MATERIAL_MAX_ROWS  # row 12 — the totals row you added, borderless except col A
MATERIALS_TABLE_INDEX = 2  # 1-based: table 1 = header info, table 2 = materials


def _fetch_dc_formula_data(formula_id):
    """Pulls the header, its materials/version values, and customer/resin/
    color/application/finished_product/dosage from whichever parent (CMF
    or RS) it belongs to."""
    header = tbl_dc_extruder_formula.objects.select_related('cm_no', 'rs_no', 'code').get(pk=formula_id)

    dc_materials = list(
        tbl_dc_extruder_materials.objects.filter(dc=header).order_by('material_id')[:MATERIAL_MAX_ROWS]
    )
    # Build a {material_id: {version_no: value}} lookup so the fill loop
    # below can address any cell directly without a query per cell.
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
        color = header.cm_no.color_desc

        formula_info = tbl_cmf_formula.objects.filter(cm_no=header.cm_no).first()
        if formula_info:
            customer = formula_info.customer
            application = formula_info.finished_product
            finished_product = formula_info.finished_product
            dosage = formula_info.dosage

        resin = ", ".join(
            tbl_resins_selected.objects.filter(cm_no=header.cm_no).values_list('resin_no__abbreviation', flat=True)
        )

    elif header.rs_no:
        parent_no = header.rs_no.rs_no
        customer = header.rs_no.customer
        color = header.rs_no.color_desc
        application = header.rs_no.finished_product
        finished_product = header.rs_no.finished_product
        dosage = header.rs_no.dosage

        resin = ", ".join(
            tbl_resins_selected.objects.filter(rs_no=header.rs_no).values_list('resin_no__abbreviation', flat=True)
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
    if val is None or val == "":
        return 0
    if isinstance(val, Decimal):
        return float(val)
    try:
        return float(val)
    except (TypeError, ValueError):
        return 0


def _set_bookmark(doc, name, value):
    """
    Writes text into a bookmark's range, then re-adds the bookmark
    (Word deletes it when .Text is set directly). Silently skips
    bookmarks that don't exist in the template rather than erroring,
    so a missing/renamed bookmark doesn't crash the whole export —
    check server logs / the printed PDF if a field looks blank.
    """
    text = "" if value is None else str(value)
    if doc.Bookmarks.Exists(name):
        rng = doc.Bookmarks(name).Range
        rng.Text = text
        doc.Bookmarks.Add(name, rng)
    else:
        print(f"WARNING: bookmark '{name}' not found in DC template.")

def print_dc_formula(request, formula_id):
    """
    Renders the DC Formula as plain HTML/CSS (Letter landscape) for
    native browser print preview — no Word/COM involved.
    """
    try:
        data = _fetch_dc_formula_data(formula_id)
    except tbl_dc_extruder_formula.DoesNotExist:
        return HttpResponseNotFound(f"DC Formula '{formula_id}' was not found.")

    header = data['header']
    dc_materials = data['dc_materials']
    versions_by_material = data['versions_by_material']

    # Build a fixed 10x10 grid: rows = materials, cols = trial versions 1-10
    rows = []
    version_totals = {v: Decimal('0') for v in range(1, MAX_VERSIONS + 1)}

    for i in range(MATERIAL_MAX_ROWS):
        if i < len(dc_materials):
            m = dc_materials[i]
            v_values = versions_by_material.get(m.material_id, {})
            cells = []
            for v_no in range(1, MAX_VERSIONS + 1):
                val = v_values.get(v_no)
                if val is not None and val != 0:
                    cells.append(f"{_to_num(val):.4f}")
                    version_totals[v_no] += Decimal(val)
                else:
                    cells.append("")
            rows.append({'material': m.material or '', 'cells': cells})
        else:
            rows.append({'material': '', 'cells': [''] * MAX_VERSIONS})

    totals_row = [
        f"{_to_num(version_totals[v]):.4f}" if version_totals[v] != 0 else ""
        for v in range(1, MAX_VERSIONS + 1)
    ]

    context = {
        'formula_id': formula_id,
        'code': header.code.product_code if header.code else "",
        'cmf': data['parent_no'],
        'customer': data['customer'],
        'resin': data['resin'],
        'color': data['color'],
        'date_matched': header.date.strftime('%m/%d/%Y') if header.date else "",
        'dosage': f"{_to_num(data['dosage']):.2f}%",
        'sample_size': header.sample_size or "",
        'product_used': data['finished_product'],
        'mixing_time': header.mixing_time or "",
        'application': data['application'],
        'note': header.notes or "",
        'matched_by': header.matched_by or "",
        'weighed_by': header.weighted_by or "",
        'encoded_by': header.encoded_by or "",
        'rows': rows,
        'totals_row': totals_row,
    }
    return render(request, "print-html/dc_formula_print.html", context)


print_dc_formula = xframe_options_exempt(print_dc_formula)

def log_formula_print(request, formula_id):
    try:
        formula = tbl_dc_extruder_formula.objects.get(pk=formula_id)
        desc = f"Printed DC Formula (Code: {formula.code.product_code if formula.code else 'N/A'})"

        log_audit(request, "Printed", desc)
        return JsonResponse({'status': 'success'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)