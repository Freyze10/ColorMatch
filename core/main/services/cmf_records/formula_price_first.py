# formula_price_first
import io
import os
import threading
import re
import json
from django.core.cache import cache
from django.db import transaction
import win32com.client as win32
import tempfile
import uuid
import pythoncom
from decimal import Decimal
from datetime import datetime, date
from django.db.models import Max
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from main.utils.log_audit_trail import log_audit
from main.models import (
    tbl_cmf, tbl_cmf_formula, tbl_cmf_pending_completed, tbl_dc_extruder_formula, 
    tbl_dc_extruder_materials, tbl_dc_extruder_version, tbl_feedback_details, 
    tbl_mb_extruder_formula, tbl_mb_extruder_formula02, 
    tbl_resins_selected, tbl_submitted_option, tbl_submitted_selected
)

def _build_price_first_row_list(items):
    """
    Shared helper to build the list of dictionaries for both 
    the Modal Preview and the Bulk Export.
    Decoupled: all parent data routes through header.cm_no.
    """
    results = []
    for item in items:
        f_id = item['id']
        f_type = item['type']
        
        # 1. Fetch formula without the deleted rs_no foreign key
        if f_type == 'MB':
            header = tbl_mb_extruder_formula.objects.select_related('code', 'cm_no').get(pk=f_id)
            qs = tbl_mb_extruder_formula02.objects.filter(mb=header).order_by('id')
            ingredients_list = [{'material': ing.material, 'value': float(ing.value or 0)} for ing in qs]
        else:
            header = tbl_dc_extruder_formula.objects.select_related('code', 'cm_no').get(pk=f_id)
            max_v = tbl_dc_extruder_version.objects.filter(material__dc=header).aggregate(Max('version_no'))['version_no__max']
            ingredients_list = []
            if max_v is not None:
                version_data = tbl_dc_extruder_version.objects.filter(material__dc=header, version_no=max_v).select_related('material')
                ingredients_list = [{'material': v.material.material, 'value': float(v.value or 0)} for v in version_data]

        customer, dosage, end_product, salesman, matching_type = "", 0, "", "", ""
        
        # 2. Requisition & Specs come strictly from cm_no
        if header.cm_no:
            formula_info = tbl_cmf_formula.objects.filter(cm_no=header.cm_no).first()
            if formula_info:
                customer = formula_info.customer or ""
                dosage = formula_info.dosage or 0
                end_product = formula_info.finished_product or ""
            salesman = header.cm_no.sm.name if (header.cm_no.sm and hasattr(header.cm_no.sm, 'name')) else ""
            matching_type = header.cm_no.matching_type or ""

        # 3. Resin formatting (filtered purely by cm_no)
        resins_list = list(tbl_resins_selected.objects.filter(
            cm_no=header.cm_no
        ).values_list('resin_no__abbreviation', flat=True)) if header.cm_no else []
        
        if not resins_list:
            resin_str = ""
        elif len(resins_list) == 1:
            resin_str = resins_list[0]
        else:
            resin_str = ", ".join(resins_list[:-1]) + " and " + resins_list[-1]

        # 4. Rematch logic
        others_val = "new matching"
        if matching_type == 'rematch' and header.cm_no:
            curr_cm = header.cm_no.cm_no
            match = re.match(r"([A-Z0-9]+)([a-z]+)", curr_cm)
            if match:
                base_code = match.group(1)
                prev_cmf = tbl_cmf.objects.filter(cm_no__startswith=base_code).exclude(cm_no=curr_cm).order_by('-cm_no').first()
                if prev_cmf:
                    pc_check = tbl_mb_extruder_formula.objects.filter(cm_no=prev_cmf, is_final=True).select_related('code').first() or \
                               tbl_dc_extruder_formula.objects.filter(cm_no=prev_cmf, is_final=True).select_related('code').first()
                    others_val = f"rematch of {pc_check.code.product_code if pc_check and pc_check.code else 'Unknown'}"
        elif matching_type == 'request':
            others_val = "request"

        total_conc = sum([i['value'] for i in ingredients_list])
        
        for ing in ingredients_list:
            results.append({
                'date': header.date.strftime('%B %d, %Y') if header.date else "no data",
                'customer': customer or "---",
                'classification': f_type.lower(),
                'prod_code': header.code.product_code if header.code else "no data",
                'resin': resin_str,
                'mat_code': ing['material'] or "---",
                'mat_conc': f"{ing['value']:.6f}",
                'end_product': end_product or "---",
                'total': f"{total_conc:.2f}",
                'others': others_val,
                'dosage': f"{float(dosage or 0):.2f}",
                'salesman_name': salesman or "---",
                'cmf_no': header.cm_no.cm_no if header.cm_no else "none",
                'html': (header.html or "no data").replace('#', ''),
                'c': int(header.c) if header.c is not None else "no data",
                'm': int(header.m) if header.m is not None else "no data",
                'y': int(header.y) if header.y is not None else "no data",
                'k': int(header.k) if header.k is not None else "no data",
                'remarks': '' # Blank for bulk export
            })
    return results

def get_price_first_data(request):
    """View for the Modal Preview."""
    try:
        items = json.loads(request.GET.get('items', '[]'))
        data = _build_price_first_row_list(items)
        return JsonResponse({'data': data})
    except Exception as e:
        return HttpResponseBadRequest(str(e))

def export_formula_by_date(request):
    """View for the Bulk Export button (Direct download)."""
    date_from_str = request.GET.get('from')
    date_to_str = request.GET.get('to')

    try:
        date_from = datetime.strptime(date_from_str, '%m/%d/%Y').date()
        date_to = datetime.strptime(date_to_str, '%m/%d/%Y').date()
        
        mb_ids = tbl_mb_extruder_formula.objects.filter(date__range=[date_from, date_to]).values_list('mb_no', flat=True)
        dc_ids = tbl_dc_extruder_formula.objects.filter(date__range=[date_from, date_to]).values_list('dc_no', flat=True)
        
        items = [{'type': 'MB', 'id': i} for i in mb_ids] + [{'type': 'DC', 'id': i} for i in dc_ids]
        
        if not items:
            return HttpResponseBadRequest("No records found in this date range.")

        row_dicts = _build_price_first_row_list(items)
        
        template_abs_path = os.path.abspath(FORMULA_TEMPLATE_PATH)
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "Formula_Export.xlsx")
            with _excel_lock:
                _fill_formula_sheet_via_excel(template_abs_path, output_path, row_dicts)
            
            with open(output_path, 'rb') as f:
                file_bytes = f.read()

        response = HttpResponse(file_bytes, content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = f'attachment; filename="Formula_Export_{date_from_str.replace("/","-")}_to_{date_to_str.replace("/","-")}.xlsx"'
        return response

    except Exception as e:
        return HttpResponseBadRequest(f"Export failed: {str(e)}")


_excel_lock = threading.Lock()
FORMULA_TEMPLATE_PATH = os.path.join('main', 'templates', 'print_excel', 'Formula.xlsx')
FORMULA_TEMPLATE_PASSWORD = "maranatha101"

COLUMN_ORDER = [
    'date', 'customer', 'classification', 'prod_code', 'resin', 'mat_code',
    'mat_conc', 'end_product', 'total', 'others', 'dosage', 'salesman_name',
    'cmf_no', 'html', 'c', 'm', 'y', 'k', 'remarks'
]

DATA_START_ROW = 2


def _fill_formula_sheet_via_excel(template_abs_path, output_path, rows):
    pythoncom.CoInitialize()
    excel = None
    wb = None
    try:
        excel = win32.DispatchEx("Excel.Application")
        excel.Visible = False
        excel.DisplayAlerts = False

        wb = excel.Workbooks.Open(
            template_abs_path,
            0,
            False,
            None,
            FORMULA_TEMPLATE_PASSWORD,
        )
        ws = wb.Worksheets("Formula")
        last_row = DATA_START_ROW
        for r_idx, row in enumerate(rows):
            excel_row = DATA_START_ROW + r_idx
            last_row = excel_row
            for c_idx, field in enumerate(COLUMN_ORDER):
                col_letter = chr(ord('A') + c_idx)
                ws.Range(f"{col_letter}{excel_row}").Value = row.get(field, "")

        if rows:
            last_col_letter = chr(ord('A') + len(COLUMN_ORDER) - 1)
            data_range = f"A{DATA_START_ROW}:{last_col_letter}{last_row}"
            ws.Range(data_range).Font.Bold = True
            ws.Rows(1).Font.Bold = True
            
        ws.Columns.AutoFit()

        wb.SaveAs(
            output_path,
            51,
            FORMULA_TEMPLATE_PASSWORD,
        )

    finally:
        if wb is not None:
            wb.Close(SaveChanges=False)
        if excel is not None:
            excel.Quit()
        pythoncom.CoUninitialize()


def download_price_first_excel(request):
    if request.method != 'POST':
        return HttpResponseBadRequest("POST required.")

    try:
        payload = json.loads(request.body)
        rows = payload.get('rows', [])
        # True if confirmed by user; False if user chose not to update records
        mark_completed = bool(payload.get('mark_completed', False))

    except (json.JSONDecodeError, TypeError):
        return HttpResponseBadRequest("Invalid JSON body.")

    if not rows:
        return HttpResponseBadRequest("No rows to export.")

    row_dicts = []
    for row in rows:
        row_dicts.append({field: (row[i] if i < len(row) else "") for i, field in enumerate(COLUMN_ORDER)})

    # Only update tracking if the user confirmed in the prompt
    if mark_completed:
        cmf_numbers = set()
        for r in row_dicts:
            c_no = r.get('cmf_no', '').strip()
            if c_no and c_no.lower() not in ('none', 'n/a', 'no data', ''):
                cmf_numbers.add(c_no)

        try:
            _auto_complete_cmf_price_first(cmf_numbers, request)
        except Exception:
            pass
        
    template_abs_path = os.path.abspath(FORMULA_TEMPLATE_PATH)
    if not os.path.exists(template_abs_path):
        return HttpResponseBadRequest("Formula.xlsx template not found on server.")

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = os.path.join(tmpdir, f"{uuid.uuid4().hex}.xlsx")

        try:
            with _excel_lock:
                _fill_formula_sheet_via_excel(template_abs_path, output_path, row_dicts)
        except Exception as e:
            return HttpResponseBadRequest(f"Excel export failed: {str(e)}")

        if not os.path.exists(output_path):
            return HttpResponseBadRequest("Excel export failed: no output file produced.")

        with open(output_path, 'rb') as f:
            file_bytes = f.read()

    response = HttpResponse(
        file_bytes,
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename="Formula.xlsx"'
    return response



def _auto_complete_cmf_price_first(cmf_numbers, request=None):
    """
    Automates pending/completed tracking for CMFs exported via Price First:
    - Status: Completed
    - Reason: 'Done'
    - Submitted: 'Price'
    - Lot No: 'N/A'
    - Qty Given, Set Pc, AR No: None (SQL NULL)
    - Date Submitted & AR Date: today's date
    """
    if not cmf_numbers:
        return

    today = date.today()
    price_option = tbl_submitted_option.objects.filter(name__iexact='price').first()

    for cm_no_str in cmf_numbers:
        cmf_obj = tbl_cmf.objects.filter(cm_no=cm_no_str).first()
        if not cmf_obj:
            continue

        with transaction.atomic():
            # 1. Resolve product code from final formula
            final_formula = (
                tbl_mb_extruder_formula.objects.filter(cm_no=cmf_obj, is_final=True).select_related('code').first() or
                tbl_dc_extruder_formula.objects.filter(cm_no=cmf_obj, is_final=True).select_related('code').first()
            )
            prod_code_obj = final_formula.code if final_formula and final_formula.code else None

            # 2. Tracking instance
            tracking, _ = tbl_cmf_pending_completed.objects.get_or_create(cm_no=cmf_obj)
            tracking.is_completed = True
            tracking.reason = 'Done'
            tracking.lot_no = 'N/A'
            tracking.ar_no = None
            tracking.date_submitted = today
            tracking.ar_date = today
            if prod_code_obj and not tracking.code:
                tracking.code = prod_code_obj
            tracking.save()

            # 3. Feedback instance (null for qty_given & pieces)
            feedback, _ = tbl_feedback_details.objects.get_or_create(cm_no=cmf_obj)
            feedback.quantity_given = None
            feedback.pieces = None
            if tracking.code:
                feedback.code = tracking.code
            feedback.save()

            # 4. Submitted options: Strictly 'Price'
            if price_option:
                tbl_submitted_selected.objects.filter(completed_id=tracking).exclude(option_id=price_option).delete()
                tbl_submitted_selected.objects.get_or_create(
                    completed_id=tracking,
                    option_id=price_option
                )

            # Optional audit logging
            if log_audit and request and hasattr(request, 'user') and request.user.is_authenticated:
                log_audit(
                    request,
                    "Updated",
                    f"Auto-completed tracking for CMF: {cmf_obj.cm_no} via Price First Excel export."
                )

    cache.delete('cmf_records_list')
    cache.delete('feedback_records_list')
