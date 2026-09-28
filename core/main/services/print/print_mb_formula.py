#print_mb_formula
import os
# import tempfile
# import threading
# import uuid
from decimal import Decimal
from django.shortcuts import render
# import pythoncom
# import win32com.client as win32
from django.contrib import messages
from django.http import HttpResponse, HttpResponseNotFound, HttpResponseServerError, JsonResponse
# from django.shortcuts import redirect
from django.views.decorators.clickjacking import xframe_options_exempt

from main.utils.log_audit_trail import log_audit
# from main.services.print.print_util import _resize_pdf_to_fixed_size
from main.models import (
    tbl_mb_extruder_formula, tbl_mb_extruder_formula02,
    tbl_cmf_formula, tbl_resins_selected,
)

# _excel_lock = threading.Lock()

MB_TEMPLATE_PATH = os.path.join('main', 'templates', 'print_excel', 'mb_formula_template.xlsx')

MB_PDF_WIDTH_IN = 8.5
MB_PDF_HEIGHT_IN = 6.5

# Material rows: row 1 -> sheet row 13, one row per material, up to 10.
MATERIAL_START_ROW = 13
MATERIAL_MAX_ROWS = 10

# Custom Excel number formats — quoted literals are display-only suffixes,
# they don't affect the underlying numeric value (e.g. "%" here is just
# text, not a x100 percentage format).
FMT_PERCENT_4DP = '0.0000'
FMT_WEIGHT_7DP_G = '0.0000000"g"'
FMT_DOSAGE_PCT = '0.00"%"'


def _fetch_mb_formula_data(formula_id):
    """Pulls the header, its ingredient rows, and customer/resin/color/
    application/dosage from whichever parent (CMF or RS) it belongs to."""
    header = tbl_mb_extruder_formula.objects.select_related('cm_no', 'rs_no', 'code').get(pk=formula_id)
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
        color = header.cm_no.color_desc

        formula_info = tbl_cmf_formula.objects.filter(cm_no=header.cm_no).first()
        if formula_info:
            customer = formula_info.customer
            application = formula_info.finished_product
            dosage = formula_info.dosage

        resin = ", ".join(
            tbl_resins_selected.objects.filter(cm_no=header.cm_no).values_list('resin_no__abbreviation', flat=True)
        )

    elif header.rs_no:
        parent_no = header.rs_no.rs_no
        customer = header.rs_no.customer
        color = header.rs_no.color_desc
        application = header.rs_no.finished_product
        dosage = getattr(header.rs_no, 'dosage', '')

        resin = ", ".join(
            tbl_resins_selected.objects.filter(rs_no=header.rs_no).values_list('resin_no__abbreviation', flat=True)
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
    """Safely converts None/'' /Decimal/str into a float for COM, defaulting to 0."""
    if val is None or val == "":
        return 0
    if isinstance(val, Decimal):
        return float(val)
    try:
        return float(val)
    except (TypeError, ValueError):
        return 0


# def _fill_and_export_mb_formula_via_excel(template_abs_path, pdf_path, data):
#     header = data['header']
#     ingredients = data['ingredients']

#     pythoncom.CoInitialize()
#     excel = None
#     wb = None
#     try:
#         excel = win32.DispatchEx("Excel.Application")
#         excel.Visible = False
#         excel.DisplayAlerts = False

#         wb = excel.Workbooks.Open(template_abs_path)
#         ws = wb.Worksheets(1)

#         def set_cell(addr, value, number_format=None):
#             rng = ws.Range(addr)
#             rng.Value = value
#             if number_format is not None:
#                 rng.NumberFormat = number_format

#         # --- HEADER (left block) ---
#         set_cell('C6', header.date.strftime('%m/%d/%Y') if header.date else "")
#         set_cell('C7', header.code.product_code if header.code else "")
#         set_cell('C8', data['customer'])
#         set_cell('C9', header.lot_no)
#         set_cell('C10', data['color'])

#         # --- HEADER (right block) ---
#         set_cell('G6', data['parent_no'])
#         set_cell('G7', data['resin'])
#         # Dosage: numeric value, 2 decimals + literal "%" suffix, no
#         # currency formatting and no x100 percentage conversion.
#         set_cell('G8', _to_num(data['dosage']), number_format=FMT_DOSAGE_PCT)
#         set_cell('G9', header.mixing_time)
#         set_cell('G10', data['application'])

#         # --- MATERIALS (row 1 -> sheet row 13, up to 10 rows) ---
#         for i in range(MATERIAL_MAX_ROWS):
#             row_num = MATERIAL_START_ROW + i
#             if i < len(ingredients):
#                 ing = ingredients[i]
#                 set_cell(f'A{row_num}', ing.material)
#                 set_cell(f'C{row_num}', _to_num(ing.value), number_format=FMT_PERCENT_4DP)
#                 set_cell(f'G{row_num}', _to_num(ing.weight), number_format=FMT_WEIGHT_7DP_G)
#             else:
#                 set_cell(f'A{row_num}', "")
#                 set_cell(f'C{row_num}', "", number_format=FMT_PERCENT_4DP)
#                 set_cell(f'G{row_num}', "", number_format=FMT_WEIGHT_7DP_G)

#         # --- TOTALS ---
#         # "Value" total still summed from ingredient rows.
#         total_value = sum((Decimal(ing.value or 0) for ing in ingredients), Decimal('0'))
#         set_cell('C23', _to_num(total_value), number_format=FMT_PERCENT_4DP)

#         # Total Weight comes directly from the saved header field, not
#         # summed from ingredient rows.
#         set_cell('G23', _to_num(header.total_weight), number_format=FMT_WEIGHT_7DP_G)

#         # --- PERSONNEL / NOTES ---
#         set_cell('B24', header.matched_by)
#         set_cell('B25', header.weighted_by)
#         set_cell('D24', header.notes)
#         set_cell('G24', header.encoded_by)

#         # --- PAGE SETUP: zero margins, fit print area to one page ---
#         ps = ws.PageSetup
        
#         ps.LeftMargin = 0
#         ps.RightMargin = 0
#         ps.TopMargin = 0
#         ps.BottomMargin = 0
#         ps.HeaderMargin = 0
#         ps.FooterMargin = 0
#         ps.Zoom = False
#         ps.FitToPagesWide = 1
#         ps.FitToPagesTall = 1

#         # 0 = xlTypePDF
#         ws.ExportAsFixedFormat(0, pdf_path)

#     finally:
#         if wb is not None:
#             wb.Close(SaveChanges=False)
#         if excel is not None:
#             excel.Quit()
#         pythoncom.CoUninitialize()


# def print_mb_formula_preview(request, formula_id):
#     """
#     Fills the ORIGINAL MB Formula Excel template via COM, exports to
#     PDF, resizes to a fixed 8.5in x 6.5in page, and serves it inline
#     for browser preview. All temp files are cleaned up before returning.
#     """
#     try:
#         data = _fetch_mb_formula_data(formula_id)
#     except tbl_mb_extruder_formula.DoesNotExist:
#         messages.error(request, f"Error: MB Formula '{formula_id}' was not found.")
#         return redirect('cmf_entry')
#     except Exception as e:
#         messages.error(request, f"System Error: {str(e)}")
#         return redirect('cmf_entry')

#     template_abs_path = os.path.abspath(MB_TEMPLATE_PATH)
#     if not os.path.exists(template_abs_path):
#         return HttpResponseServerError("Template file not found on server.")

#     with tempfile.TemporaryDirectory() as tmpdir:
#         raw_pdf_path = os.path.join(tmpdir, f"{uuid.uuid4().hex}_raw.pdf")
#         final_pdf_path = os.path.join(tmpdir, f"{uuid.uuid4().hex}_final.pdf")

#         try:
#             with _excel_lock:
#                 _fill_and_export_mb_formula_via_excel(template_abs_path, raw_pdf_path, data)
#             _resize_pdf_to_fixed_size(
#                 raw_pdf_path, final_pdf_path,
#                 width_in=MB_PDF_WIDTH_IN, height_in=MB_PDF_HEIGHT_IN,
#             )
#         except Exception as e:
#             return HttpResponseServerError(f"PDF export failed: {str(e)}")

#         if not os.path.exists(final_pdf_path):
#             return HttpResponseServerError("PDF export failed: no output file produced.")

#         with open(final_pdf_path, 'rb') as f:
#             pdf_bytes = f.read()

#     response = HttpResponse(pdf_bytes, content_type='application/pdf')
#     response['Content-Disposition'] = 'inline'
#     response['X-Frame-Options'] = 'SAMEORIGIN'
#     return response


# print_mb_formula_preview = xframe_options_exempt(print_mb_formula_preview)

def print_mb_formula(request, formula_id):
    """
    Renders the MB Formula as plain HTML/CSS (Letter size) for native
    browser print preview — no Excel/COM involved.
    """
    try:
        data = _fetch_mb_formula_data(formula_id)
    except tbl_mb_extruder_formula.DoesNotExist:
        return HttpResponseNotFound(f"MB Formula '{formula_id}' was not found.")

    header = data['header']
    ingredients = data['ingredients']

    # Pad ingredient rows to a fixed 10 rows so the table always has the
    # same number of visual rows as the original template.
    rows = []
    for i in range(MATERIAL_MAX_ROWS):
        if i < len(ingredients):
            ing = ingredients[i]
            rows.append({
                'material': ing.material or '',
                'value': f"{_to_num(ing.value):.4f}" if ing.value not in (None, '') else '',
                'weight': f"{_to_num(ing.weight):.7f}" if ing.weight not in (None, '') else '',
            })
        else:
            rows.append({'material': '', 'value': '', 'weight': ''})

    total_value = sum((Decimal(ing.value or 0) for ing in ingredients), Decimal('0'))

    context = {
        'date': header.date.strftime('%m/%d/%Y') if header.date else '',
        'cm_form_no': data['parent_no'],
        'product_code': header.code.product_code if header.code else '',
        'resin_used': data['resin'],
        'customer': data['customer'],
        'dosage': f"{_to_num(data['dosage']):.2f}%" if data['dosage'] not in (None, '', 0) else '',
        'lot_number': header.lot_no or '',
        'mixing_time': header.mixing_time or '',
        'color': data['color'],
        'application': data['application'],
        'rows': rows,
        'total_value': f"{_to_num(total_value):.4f}",
        'total_weight': f"{_to_num(header.total_weight):.7f}" if header.total_weight not in (None, '', 0) else '',
        'matched_by': header.matched_by or '',
        'weighed_by': header.weighted_by or '',
        'encoded_by': header.encoded_by or '',
        'note': header.notes or '',
    }
    return render(request, "print-html/mb_formula_print.html", context)

print_mb_formula = xframe_options_exempt(print_mb_formula) 

def log_formula_print(request, formula_id):
    try:
        
        formula = tbl_mb_extruder_formula.objects.get(pk=formula_id)
        desc = f"Printed MB Formula (Lot: {formula.lot_no or 'N/A'})"

        log_audit(request, "Printed", desc)
        return JsonResponse({'status': 'success'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)