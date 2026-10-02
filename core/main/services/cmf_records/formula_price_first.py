import io
import os
import re
import json
import tempfile
import uuid
from decimal import Decimal
from datetime import datetime, date

# Cross-platform Excel libraries
import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill
import msoffcrypto

from django.db import transaction
from django.db.models import Max
from django.core.cache import cache
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse

from main.utils.log_audit_trail import log_audit
from main.models import (
    tbl_cmf, tbl_cmf_formula, tbl_dc_extruder_formula, 
    tbl_dc_extruder_materials, tbl_dc_extruder_version, 
    tbl_mb_extruder_formula, tbl_mb_extruder_formula02, 
    tbl_resins_selected,
    tbl_cmf_pending_completed,
    tbl_feedback_details,
    tbl_submitted_option,
    tbl_submitted_selected
)

# Configuration
FORMULA_TEMPLATE_PATH = os.path.join('main', 'templates', 'print_excel', 'Formula.xlsx')
FORMULA_TEMPLATE_PASSWORD = "maranatha101"

COLUMN_ORDER = [
    'date', 'customer', 'classification', 'prod_code', 'resin', 'mat_code',
    'mat_conc', 'end_product', 'total', 'others', 'dosage', 'salesman_name',
    'cmf_no', 'html', 'c', 'm', 'y', 'k', 'remarks'
]
DATA_START_ROW = 2 


def _autofit_columns(ws):
    for col in ws.columns:
        max_length = 0
        column = col[0].column_letter
        for cell in col:
            try:
                if cell.value:
                    length = len(str(cell.value))
                    if length > max_length: 
                        max_length = length
            except Exception: 
                pass
        ws.column_dimensions[column].width = max_length + 3


def _fill_formula_sheet_logic(template_abs_path, rows):
    # --- 1. DECRYPT TEMPLATE ---
    decrypted_tmp = io.BytesIO()
    with open(template_abs_path, "rb") as f:
        office_file = msoffcrypto.OfficeFile(f)
        office_file.load_key(password=FORMULA_TEMPLATE_PASSWORD)
        office_file.decrypt(decrypted_tmp)

    # --- 2. LOAD & STYLE WORKBOOK ---
    wb = openpyxl.load_workbook(decrypted_tmp)
    ws = wb["Formula"] if "Formula" in wb.sheetnames else wb.active
    
    header_font = Font(name='Arial', size=14, bold=True)
    content_font = Font(name='Arial', size=12, bold=True)
    
    align_center = Alignment(horizontal='center', vertical='center')
    align_left = Alignment(horizontal='left', vertical='center')
    align_right = Alignment(horizontal='right', vertical='center')

    COLUMN_ALIGNMENTS = {
        'date': align_left,
        'customer': align_left,
        'classification': align_center,
        'prod_code': align_left,
        'resin': align_left,
        'mat_code': align_center,
        'mat_conc': align_right,
        'end_product': align_left,
        'total': align_right,
        'others': align_left,
        'dosage': align_center,
        'salesman_name': align_left,
        'cmf_no': align_center,
        'html': align_center,
        'c': align_center,
        'm': align_center,
        'y': align_center,
        'k': align_center,
        'remarks': align_left,
    }

    # Apply Header Styling (Row 1)
    for cell in ws[1]:
        cell.font = header_font
        cell.alignment = align_center

    # --- 3. FILL CONTENT ROWS ---
    for r_idx, row_data in enumerate(rows):
        excel_row = DATA_START_ROW + r_idx
        for c_idx, field in enumerate(COLUMN_ORDER):
            cell = ws.cell(row=excel_row, column=c_idx + 1)
            val = row_data.get(field, "")
            
            if val in ("no data", "None", "", None):
                cell.value = str(val or "")
            else:
                try:
                    cell.value = float(val)
                except (ValueError, TypeError):
                    cell.value = str(val)
            
            cell.font = content_font
            cell.alignment = COLUMN_ALIGNMENTS.get(field, align_left)

    _autofit_columns(ws)

    # --- 4. SAVE UNPROTECTED TO BUFFER ---
    unprotected_buffer = io.BytesIO()
    wb.save(unprotected_buffer)
    unprotected_buffer.seek(0)

    # --- 5. RE-ENCRYPT FOR OUTPUT ---
    encrypted_buffer = io.BytesIO()
    file_to_encrypt = msoffcrypto.OfficeFile(unprotected_buffer)
    file_to_encrypt.encrypt(FORMULA_TEMPLATE_PASSWORD, encrypted_buffer)
    
    return encrypted_buffer.getvalue()


def _auto_complete_cmf_price_first(cmf_numbers, request=None):
    """
    Automates pending/completed tracking for CMFs exported via Price First:
    - If ALREADY completed: Keeps existing tracking, dates, and lots untouched,
      and strictly ensures 'Price' is added to the submitted options.
    - If NOT completed: Performs full auto-completion (Status=Completed, Reason='Done',
      Lot='N/A', Qty/Set/AR=None, Dates=today, Submitted='Price').
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
            tracking, created = tbl_cmf_pending_completed.objects.get_or_create(cm_no=cmf_obj)

            # SCENARIO 1: CMF is ALREADY completed -> Only add 'Price' to submitted options
            if not created and tracking.is_completed:
                if price_option:
                    tbl_submitted_selected.objects.get_or_create(
                        completed_id=tracking,
                        option_id=price_option
                    )
                
                if log_audit and request and hasattr(request, 'user') and request.user.is_authenticated:
                    log_audit(
                        request,
                        "Exported",
                        f"Updated: Add 'Price' to submitted options for already-completed CMF: {cmf_obj.cm_no} (Price First Export)."
                    )

            # SCENARIO 2: CMF is NOT completed yet -> Perform full auto-completion
            else:
                final_formula = (
                    tbl_mb_extruder_formula.objects.filter(cm_no=cmf_obj, is_final=True).select_related('code').first() or
                    tbl_dc_extruder_formula.objects.filter(cm_no=cmf_obj, is_final=True).select_related('code').first()
                )
                prod_code_obj = final_formula.code if final_formula and final_formula.code else None

                tracking.is_completed = True
                tracking.reason = 'Completed'
                tracking.lot_no = 'N/A'
                tracking.ar_no = None
                tracking.date_submitted = today
                tracking.ar_date = today
                if prod_code_obj and not tracking.code:
                    tracking.code = prod_code_obj
                tracking.save()

                feedback, _ = tbl_feedback_details.objects.get_or_create(cm_no=cmf_obj)
                feedback.quantity_given = None
                feedback.pieces = None
                if tracking.code:
                    feedback.code = tracking.code
                feedback.save()

                if price_option:
                    tbl_submitted_selected.objects.filter(completed_id=tracking).exclude(option_id=price_option).delete()
                    tbl_submitted_selected.objects.get_or_create(
                        completed_id=tracking,
                        option_id=price_option
                    )

                if log_audit and request and hasattr(request, 'user') and request.user.is_authenticated:
                    log_audit(
                        request,
                        "Exported",
                        f"Updated: Auto-completed tracking for CMF: {cmf_obj.cm_no} via Price First Excel export."
                    )

    cache.delete('cmf_records_list')
    cache.delete('feedback_records_list')


def _build_price_first_row_list(items):
    """
    Shared helper to build the list of data dictionaries from models.
    Decoupled: all parent specs route strictly through cm_no.
    """
    results = []
    for item in items:
        f_id = item['id']
        f_type = item['type']
        
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
        
        if header.cm_no:
            formula_info = tbl_cmf_formula.objects.filter(cm_no=header.cm_no).first()
            if formula_info:
                customer = formula_info.customer or ""
                dosage = formula_info.dosage or 0
                end_product = formula_info.finished_product or ""
            salesman = header.cm_no.sm.name if (header.cm_no.sm and hasattr(header.cm_no.sm, 'name')) else ""
            matching_type = header.cm_no.matching_type or ""

        resins_list = list(tbl_resins_selected.objects.filter(
            cm_no=header.cm_no
        ).values_list('resin_no__abbreviation', flat=True)) if header.cm_no else []
        
        if not resins_list:
            resin_str = ""
        elif len(resins_list) == 1:
            resin_str = resins_list[0]
        else:
            resin_str = ", ".join(resins_list[:-1]) + " and " + resins_list[-1]

        others_val = "new matching"
        if matching_type == 'rematch' and header.cm_no:
            curr_cm = header.cm_no.cm_no
            match = re.match(r"([A-Z0-9]+)([a-z]+)", curr_cm)
            if match:
                base_code = match.group(1)
                prev_cmf = tbl_cmf.objects.filter(cm_no__startswith=base_code).exclude(cm_no=curr_cm).order_by('-cm_no').first()
                if prev_cmf:
                    pc_check = (
                        tbl_mb_extruder_formula.objects.filter(cm_no=prev_cmf, is_final=True).select_related('code').first() or
                        tbl_dc_extruder_formula.objects.filter(cm_no=prev_cmf, is_final=True).select_related('code').first()
                    )
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
                'remarks': ''
            })
    return results


def get_price_first_data(request):
    try:
        items = json.loads(request.GET.get('items', '[]'))
        data = _build_price_first_row_list(items)
        return JsonResponse({'data': data})
    except Exception as e:
        return HttpResponseBadRequest(str(e))

def download_price_first_excel(request):
    if request.method != 'POST':
        return HttpResponseBadRequest("POST required.")
        
    try:
        payload = json.loads(request.body)
        rows = payload.get('rows', [])
        # True if confirmed by user; False if user chose not to update records
        mark_completed = bool(payload.get('mark_completed', False))
    except Exception:
        return HttpResponseBadRequest("Invalid JSON.")
        
    if not rows:
        return HttpResponseBadRequest("No rows.")

    row_dicts = []
    for row in rows:
        row_dicts.append({field: (row[i] if i < len(row) else "") for i, field in enumerate(COLUMN_ORDER)})

    # Extract unique CMF numbers
    cmf_numbers = set()
    for r in row_dicts:
        c_no = r.get('cmf_no', '').strip()
        if c_no and c_no.lower() not in ('none', 'n/a', 'no data', ''):
            cmf_numbers.add(c_no)

    cmf_display = f"CMF(s): {', '.join(sorted(cmf_numbers))}" if cmf_numbers else "Price First formulas"

    # User confirmed to update tracking & completed status
    if mark_completed:
        try:
            _auto_complete_cmf_price_first(cmf_numbers, request)
        except Exception:
            pass
    else:
        # User exported WITHOUT updating tracking status -> Log audit trail
        if log_audit and hasattr(request, 'user') and request.user.is_authenticated:
            log_audit(
                request,
                "Exported",
                f"Using Price First {cmf_display} without updating tracking status."
            )

    # Produce the encrypted Excel download via openpyxl + msoffcrypto
    template_abs_path = os.path.abspath(FORMULA_TEMPLATE_PATH)
    try:
        file_bytes = _fill_formula_sheet_logic(template_abs_path, row_dicts)
    except Exception as e:
        return HttpResponseBadRequest(f"Excel export failed: {str(e)}")

    response = HttpResponse(file_bytes, content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename="Formula.xlsx"'
    return response

# ==============================================================================
# 2. DEDICATED EXPORT FORMULA BY DATE (NEW CUSTOM EXCEL BUILDER)
# ==============================================================================

EXPORT_PASSWORD = "maranatha101"

# Exact column key sequence as requested
DATE_EXPORT_COLUMN_ORDER = [
    'date', 'customer', 'classification', 'prod_code', 'color', 'lot_no', 'resin',
    'mat_code', 'mat_conc', 'total', 'dosage', 'qty_produced', 'end_product',
    'others', 'salesman_name', 'cmf_no', 'html', 'c', 'm', 'y', 'k', 'remarks'
]

# Exact headers matching DATE_EXPORT_COLUMN_ORDER
DATE_EXPORT_HEADERS = [
    "Date", "Customer", "Classification", "Product Code", "Color", "Lot Number", "Resin",
    "Material Code", "Concentration", "Total Conc", "Dosage", "Qty Produced", "End Product",
    "Others", "Salesman", "CMF No.", "HTML", "C", "M", "Y", "K", "Remarks"
]


def _autofit_columns_content(ws):
    """Dynamically adjusts column widths based on the longest cell content."""
    for col in ws.columns:
        max_len = 0
        col_letter = col[0].column_letter
        for cell in col:
            if cell.value is not None:
                val_str = str(cell.value)
                
                # Check formatted decimal lengths
                num_fmt = getattr(cell, 'number_format', '')
                if isinstance(cell.value, (int, float)):
                    if num_fmt == '0.00':
                        val_str = f"{cell.value:.2f}"
                    elif num_fmt == '0.0000':
                        val_str = f"{cell.value:.4f}"
                
                for line in val_str.split('\n'):
                    line_len = len(line)
                    # Header row (size 14 bold) requires extra visual spacing
                    if cell.row == 1:
                        line_len = int(line_len * 1.3) + 2
                    if line_len > max_len:
                        max_len = line_len
        ws.column_dimensions[col_letter].width = max(max_len + 4, 12)


def _build_date_export_row_list(items):
    """
    Dedicated builder for Date Range Export:
    - Date formatted to MM/DD/YYYY
    - Color from cmf.color_desc
    - Qty Produced from header.total_weight
    - Remarks from header.notes (default: 'no data')
    """
    results = []
    for item in items:
        f_id = item['id']
        f_type = item['type']
        
        if f_type == 'MB':
            header = tbl_mb_extruder_formula.objects.select_related('code', 'cm_no').get(pk=f_id)
            qs = tbl_mb_extruder_formula02.objects.filter(mb=header).order_by('id')
            ingredients_list = [{'material': ing.material, 'value': float(ing.value or 0)} for ing in qs]
            lot_no_val = getattr(header, 'lot_no', '') or ''
        else:
            header = tbl_dc_extruder_formula.objects.select_related('code', 'cm_no').get(pk=f_id)
            max_v = tbl_dc_extruder_version.objects.filter(material__dc=header).aggregate(Max('version_no'))['version_no__max']
            ingredients_list = []
            if max_v is not None:
                version_data = tbl_dc_extruder_version.objects.filter(material__dc=header, version_no=max_v).select_related('material')
                ingredients_list = [{'material': v.material.material, 'value': float(v.value or 0)} for v in version_data]
            lot_no_val = getattr(header, 'lot_no', '') or ''

        # Fallback for lot number if not set directly on formula
        if not lot_no_val and header.cm_no:
            pending_record = tbl_cmf_pending_completed.objects.filter(cm_no=header.cm_no).first()
            if pending_record and pending_record.lot_no:
                lot_no_val = pending_record.lot_no

        if not lot_no_val:
            lot_no_val = "N/A"

        # Explicitly evaluate is_final
        is_final_raw = getattr(header, 'is_final', False)
        is_final_val = bool(is_final_raw) and str(is_final_raw).lower() not in ('0', 'false', 'none', '')

        customer, dosage, end_product, salesman, matching_type, color_desc = "", 0, "", "", "", "---"
        
        if header.cm_no:
            color_desc = header.cm_no.color_desc or "---"
            formula_info = tbl_cmf_formula.objects.filter(cm_no=header.cm_no).first()
            if formula_info:
                customer = formula_info.customer or ""
                dosage = formula_info.dosage or 0
                end_product = formula_info.finished_product or ""
            salesman = header.cm_no.sm.name if (header.cm_no.sm and hasattr(header.cm_no.sm, 'name')) else ""
            matching_type = header.cm_no.matching_type or ""

        # Prioritize dosage recorded directly on formula header if available
        if hasattr(header, 'dosage') and header.dosage is not None:
            dosage = header.dosage

        # Qty Produced from total_weight
        qty_produced = getattr(header, 'total_weight', None) or 0

        # Remarks from formula notes (defaults to 'no data' if empty)
        raw_notes = getattr(header, 'notes', '') or ''
        remarks_val = raw_notes.strip() if raw_notes.strip() else "no data"

        # Resins
        resins_list = list(tbl_resins_selected.objects.filter(
            cm_no=header.cm_no
        ).values_list('resin_no__abbreviation', flat=True)) if header.cm_no else []
        
        if not resins_list:
            resin_str = ""
        elif len(resins_list) == 1:
            resin_str = resins_list[0]
        else:
            resin_str = ", ".join(resins_list[:-1]) + " and " + resins_list[-1]

        # Others
        others_val = "new matching"
        if matching_type == 'rematch' and header.cm_no:
            curr_cm = header.cm_no.cm_no
            match = re.match(r"([A-Z0-9]+)([a-z]+)", curr_cm)
            if match:
                base_code = match.group(1)
                prev_cmf = tbl_cmf.objects.filter(cm_no__startswith=base_code).exclude(cm_no=curr_cm).order_by('-cm_no').first()
                if prev_cmf:
                    pc_check = (
                        tbl_mb_extruder_formula.objects.filter(cm_no=prev_cmf, is_final=True).select_related('code').first() or
                        tbl_dc_extruder_formula.objects.filter(cm_no=prev_cmf, is_final=True).select_related('code').first()
                    )
                    others_val = f"rematch of {pc_check.code.product_code if pc_check and pc_check.code else 'Unknown'}"
        elif matching_type == 'request':
            others_val = "request"

        total_conc = sum([i['value'] for i in ingredients_list])
        
        for ing in ingredients_list:
            results.append({
                'date': header.date.strftime('%m/%d/%Y') if header.date else "no data",  # 🛑 MM/DD/YYYY
                'customer': customer or "---",
                'classification': f_type.lower(),
                'prod_code': header.code.product_code if header.code else "no data",
                'color': color_desc,                                                    # 🛑 Color
                'lot_no': lot_no_val,
                'is_final': is_final_val,
                'resin': resin_str,
                'mat_code': ing['material'] or "---",
                'mat_conc': ing['value'],                                                # 4 decimals
                'total': total_conc,                                                     # 2 decimals (Total Conc)
                'dosage': dosage,                                                        # 2 decimals
                'qty_produced': qty_produced,                                            # 🛑 Qty Produced
                'end_product': end_product or "---",
                'others': others_val,
                'salesman_name': salesman or "---",
                'cmf_no': header.cm_no.cm_no if header.cm_no else "none",
                'html': (header.html or "no data").replace('#', ''),
                'c': int(header.c) if header.c is not None else "no data",
                'm': int(header.m) if header.m is not None else "no data",
                'y': int(header.y) if header.y is not None else "no data",
                'k': int(header.k) if header.k is not None else "no data",
                'remarks': remarks_val                                                   # 🛑 From notes
            })
    return results


def _build_fresh_formula_excel(rows):
    """
    Generates a new Excel file for Date Range Export:
    - Headers: Arial 14pt Bold with light-gray fill.
    - Encrypted using password 'maranatha101'.
    - Concentration (mat_conc) formatted to 4 decimals (0.0000).
    - Dosage, Total Conc, and Qty Produced formatted to 2 decimals (0.00).
    - Rows marked as is_final=True highlighted in soft light green (#D1E7DD).
    - Columns auto-fitted based on cell content.
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Formula"
    
    ws.views.sheetView[0].showGridLines = True

    header_font = Font(name='Arial', size=14, bold=True)
    content_font = Font(name='Arial', size=11, bold=True)
    header_fill = PatternFill(start_color="F2F2F2", end_color="F2F2F2", fill_type="solid")
    
    # Soft light green highlight for Final Formulas (#D1E7DD)
    final_formula_fill = PatternFill(start_color="D1E7DD", end_color="D1E7DD", fill_type="solid")

    align_center = Alignment(horizontal='center', vertical='center')
    align_left = Alignment(horizontal='left', vertical='center')
    align_right = Alignment(horizontal='right', vertical='center')

    column_alignments = {
        'date': align_left,
        'customer': align_left,
        'classification': align_center,
        'prod_code': align_left,
        'color': align_left,
        'lot_no': align_center,
        'resin': align_left,
        'mat_code': align_center,
        'mat_conc': align_right,       # 4 decimals
        'total': align_right,          # 2 decimals (Total Conc)
        'dosage': align_right,         # 2 decimals
        'qty_produced': align_right,   # 2 decimals
        'end_product': align_left,
        'others': align_left,
        'salesman_name': align_left,
        'cmf_no': align_center,
        'html': align_center,
        'c': align_center,
        'm': align_center,
        'y': align_center,
        'k': align_center,
        'remarks': align_left,
    }

    # 1. Write Header Row (Row 1, 14pt Bold)
    for col_idx, header_title in enumerate(DATE_EXPORT_HEADERS, 1):
        cell = ws.cell(row=1, column=col_idx, value=header_title)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = align_center

    # 2. Write Data Rows
    for r_idx, row_data in enumerate(rows):
        excel_row = DATA_START_ROW + r_idx
        is_final_row = bool(row_data.get('is_final', False))

        for c_idx, field in enumerate(DATE_EXPORT_COLUMN_ORDER):
            cell = ws.cell(row=excel_row, column=c_idx + 1)
            val = row_data.get(field, "")

            # 🛑 2 DECIMAL PLACES: Dosage, Total Conc, Qty Produced
            if field in ('dosage', 'total', 'qty_produced'):
                try:
                    cell.value = round(float(val), 2)
                    cell.number_format = '0.00'
                except (ValueError, TypeError):
                    cell.value = str(val or "0.00")

            # 🛑 4 DECIMAL PLACES: Concentration (mat_conc)
            elif field == 'mat_conc':
                try:
                    cell.value = round(float(val), 4)
                    cell.number_format = '0.0000'
                except (ValueError, TypeError):
                    cell.value = str(val or "0.0000")

            elif val in ("no data", "None", "", None):
                cell.value = str(val or "")
            else:
                try:
                    cell.value = float(val)
                except (ValueError, TypeError):
                    cell.value = str(val)

            cell.font = content_font
            cell.alignment = column_alignments.get(field, align_left)

            # 🛑 Light green highlight for Final Formulas
            if is_final_row:
                cell.fill = final_formula_fill

    # 3. Dynamically adjust column widths based on contents
    _autofit_columns_content(ws)

    # 4. Save unprotected workbook to in-memory buffer
    unprotected_buffer = io.BytesIO()
    wb.save(unprotected_buffer)
    unprotected_buffer.seek(0)

    # 5. Encrypt with password 'maranatha101'
    encrypted_buffer = io.BytesIO()
    file_to_encrypt = msoffcrypto.OfficeFile(unprotected_buffer)
    file_to_encrypt.encrypt(EXPORT_PASSWORD, encrypted_buffer)
    encrypted_buffer.seek(0)

    return encrypted_buffer.getvalue()


def export_formula_by_date(request):
    """
    Exports formulas within a date range into a password-encrypted Excel file ('maranatha101').
    """
    date_from_str = request.GET.get('from')
    date_to_str = request.GET.get('to')
    
    if not date_from_str or not date_to_str:
        return HttpResponseBadRequest("Both 'from' and 'to' date parameters are required.")

    try:
        date_from = datetime.strptime(date_from_str, '%m/%d/%Y').date()
        date_to = datetime.strptime(date_to_str, '%m/%d/%Y').date()
        
        mb_ids = list(tbl_mb_extruder_formula.objects.filter(date__range=[date_from, date_to]).values_list('mb_no', flat=True))
        dc_ids = list(tbl_dc_extruder_formula.objects.filter(date__range=[date_from, date_to]).values_list('dc_no', flat=True))
        
        items = [{'type': 'MB', 'id': i} for i in mb_ids] + [{'type': 'DC', 'id': i} for i in dc_ids]
        
        if not items:
            return HttpResponseBadRequest("No formula records found in the selected date range.")
            
        row_dicts = _build_date_export_row_list(items)
        file_bytes = _build_fresh_formula_excel(row_dicts)

        if log_audit and hasattr(request, 'user') and request.user.is_authenticated:
            log_audit(
                request,
                "Exported",
                f"Bulk exported formulas from {date_from_str} to {date_to_str} ({len(items)} records)."
            )
        
        filename = f"Formula_Export_{date_from_str.replace('/', '-')}_to_{date_to_str.replace('/', '-')}.xlsx"
        
        response = HttpResponse(
            file_bytes, 
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response

    except ValueError:
        return HttpResponseBadRequest("Invalid date format. Expected MM/DD/YYYY.")
    except Exception as e:
        return HttpResponseBadRequest(f"Export failed: {str(e)}")