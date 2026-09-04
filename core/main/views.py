from collections import defaultdict
from decimal import Decimal
import base64
from django.core.cache import cache
from django.core.management import call_command
from django.contrib.auth import authenticate, login, logout, get_user_model 
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Max, Min, Value
from django.db.models.functions import Concat
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib import messages
from datetime import date, datetime, timedelta
from django.urls import reverse
from django.utils import timezone

from main.services.save import feedback_save
from main.services.dashboard.dashboard_services import get_dashboard_context
from main.utils.log_audit_trail import log_audit
from main.services.formula import master_formula_services, formulation_services
from main.services.save import mb_formula_save, dc_formula_save, rs_entry_save
from main.decorators import permission_required, role_required
from main.models import (
    tbl_audit_trail, tbl_cmf, tbl_cmf_dates, tbl_cmf_formula, tbl_cmf_pending_completed, 
    tbl_cmf_process02, tbl_cmf_process02, tbl_cmf_scanned, tbl_cmf_specification02, tbl_coding_materials, tbl_dc_extruder_formula, 
    tbl_dc_extruder_materials, tbl_feedback_details, tbl_generated_prod_code, tbl_internal_color_code, tbl_master_formula, tbl_master_formula_encode, tbl_master_formula_info, tbl_mb_extruder_formula, 
    tbl_mb_extruder_formula02, tbl_resin, tbl_cmf_salesman, tbl_resins_selected, 
    tbl_cmf_color_req, tbl_cmf_specification, tbl_cmf_process, tbl_rs, tbl_submitted_option, tbl_submitted_selected
)

from .services.cmf_records import cmf_records_services
from .services.save import cmf_entry_save
from .services.export import cmf_record_export
# Create your views here.
User = get_user_model()

def index(request):
    if request.user.is_authenticated:
        if request.user.role:
            return redirect('dashboard')
        else:
            return redirect('pending_role')
    else:
        return redirect('signin')

def pending_role(request):
    if request.user.is_authenticated and request.user.role:
        return redirect('dashboard')
    return render(request, 'login/pending-role.html')


def signin(request):
    next_url = request.GET.get('next', '') or request.POST.get('next', '')

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')

        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect(next_url or 'dashboard')

        messages.error(request, "Incorrect username or password.")

    return render(request, 'login/signin.html', {'next': next_url})


def signup(request):
    if request.method == 'POST':
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        username = request.POST.get('username', '').strip()
        email = request.POST.get('email', '').strip()
        password = request.POST.get('password', '')
        confirm_password = request.POST.get('confirm_password', '')

        errors = []
        if not all([first_name, last_name, username, email, password]):
            errors.append("All fields are required.")
        if password != confirm_password:
            errors.append("Passwords do not match.")
        if User.objects.filter(username=username).exists():
            errors.append("That username is already taken.")
        if User.objects.filter(email=email).exists():
            errors.append("That email is already registered.")

        if errors:
            for e in errors:
                messages.error(request, e)
            return render(request, 'login/signup.html')

        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
        )
        login(request, user)
        return redirect('dashboard')

    return render(request, 'login/signup.html')


def signout(request):
    logout(request)
    return redirect('signin')

# @role_required # This now handles both login AND role check
@permission_required(allowed_departments=['Laboratory', 'Information Technology'])
def dashboard(request):
    context = get_dashboard_context()
    return render(request, "sidemenu/dashboard/dashboard.html", context)

@role_required
def homepage(request):
    return render(request, "sidemenu/homepage.html")

@role_required
def maintenance(request):
    feature_name = request.GET.get('feature', 'This page')
    return render(request, 'maintenance/maintenance.html', {'feature_name': feature_name})

@role_required
def cmf_records(request):
    all_records = cmf_records_services.get_all_records_combined()
    return render(request, "sidemenu/cmf/cmf_records.html", {
        "records": all_records,
    })

@permission_required(allowed_departments=['Laboratory', 'Information Technology'])
def formula_records(request):
    mb_dates = tbl_mb_extruder_formula.objects.aggregate(Min('date'), Max('date'))
    dc_dates = tbl_dc_extruder_formula.objects.aggregate(Min('date'), Max('date'))
    
    # Logic to find absolute min and absolute max
    all_min = [d for d in [mb_dates['date__min'], dc_dates['date__min']] if d]
    all_max = [d for d in [mb_dates['date__max'], dc_dates['date__max']] if d]
    
    earliest = min(all_min).strftime('%m/%d/%Y') if all_min else ""
    latest = max(all_max).strftime('%m/%d/%Y') if all_max else ""

    return render(request, "sidemenu/cmf/formula_records.html", {
        "default_from": earliest,
        "default_to": latest
    })

@role_required
def cmf_entry(request):
    form_data = {}
    attachments = []
    if request.method == "POST":
        original_cmf_no = request.POST.get('original_cmf_no', '').strip()
        is_new = request.POST.get('is_new', '1')
        try:
            if original_cmf_no and is_new == '0':
                saved_record = cmf_entry_save.update_cmf_complete_entry(request, original_cmf_no)
                messages.success(request, f"Successfully updated CMF No. {saved_record.cm_no}")
            else:
                saved_record = cmf_entry_save.save_cmf_complete_entry(request)
                messages.success(request, f"Successfully saved CMF No. {saved_record.cm_no}")

            cache.delete('cmf_records_list')
            return redirect('cmf_entry')
        except Exception as e:
            messages.error(request, str(e))
            form_data = request.POST

    else:
        cm_no = request.GET.get('no')
        cm_no_override = request.GET.get('new_no')
        if cm_no:
            cmf = tbl_cmf.objects.filter(cm_no=cm_no).first()
            if cmf:
                dates = tbl_cmf_dates.objects.filter(cm_no=cmf).first()
                formula_info = tbl_cmf_formula.objects.filter(cm_no=cmf).first()
                color_req = tbl_cmf_color_req.objects.filter(cm_no=cmf).first()
        
                resin_ids = list(
                    tbl_resins_selected.objects.filter(cm_no=cmf).values_list('resin_no_id', flat=True)
                )
                process_names = list(
                    tbl_cmf_process02.objects.filter(cmf_formula_no=formula_info)
                    .values_list('process_no__name', flat=True)
                ) if formula_info else []
                spec_names = list(
                    tbl_cmf_specification02.objects.filter(cm_no=cmf)
                    .values_list('spec_no__name', flat=True)
                )

                final_formula = tbl_mb_extruder_formula.objects.filter(
                    cm_no=cmf, is_final=True
                ).select_related('code').first()

                if not final_formula:
                    final_formula = tbl_dc_extruder_formula.objects.filter(
                        cm_no=cmf, is_final=True
                    ).select_related('code').first()

                final_prod_code = ""
                if final_formula and final_formula.code:
                    final_prod_code = final_formula.code.product_code

                form_data = {
                    'is_new': '1' if cm_no_override else '0',
                    'cmf_no': cm_no_override if cm_no_override else cmf.cm_no,
                    'customer': formula_info.customer if formula_info else "",

                    # DateField — needs strftime
                    'date_created': dates.form_made.strftime('%m/%d/%Y') if dates and dates.form_made else "",
                    'due_date': dates.due_date_lab.strftime('%m/%d/%Y') if dates and dates.due_date_lab else "",

                    # CharField — stored exactly as Flatpickr formatted it, pass through as-is
                    # (could be "ASAP" for required_date, or "MM/DD/YYYY, MM/DD/YYYY" for date_received)
                    'required_date': dates.date_required if dates else "",
                    'date_received': dates.date_received_lab if dates else "",

                    'matchType': cmf.matching_type,
                    'product_status': cmf.product_status,
                    'est_qty_order': cmf.est_qty_order,
                    'salesman': cmf.sm.name if cmf.sm else "",
                    'finished_product': formula_info.finished_product if formula_info else "",
                    'primary_color': str(cmf.in_code_no_id) if cmf.in_code_no_id else "",
                    'color_description': cmf.color_desc,
                    'colorReq': color_req.name if color_req else "",
                    'qty_resin_test': cmf.qty_resin_testing,
                    'customerResin': 'Y' if cmf.is_resin_provided else ('N' if cmf.is_resin_provided is False else ''),
                    'mi_customer_resin': cmf.mi_c_resin,
                    'sampleColorant': 'Y' if cmf.is_sample_available else ('N' if cmf.is_sample_available is False else ''),
                    'colorantType': cmf.colorant_type if cmf.colorant_type in ('MB', 'DC') else 'Other',
                    'colorantTypeOther': cmf.colorant_type if cmf.colorant_type not in ('MB', 'DC') else '',
                    'dosage': formula_info.dosage if formula_info else "",
                    'processing_temp': cmf.temperature,
                    'color_guide_return': 'Y' if cmf.is_guide_to_return else ('N' if cmf.is_guide_to_return is False else ''),
                    'is_low_cost': 'Y' if cmf.is_low_cost else ('N' if cmf.is_low_cost is False else ''),
                    'remarks': cmf.remarks,
                    'product_code': "" if cm_no_override else final_prod_code,

                    # plain lists — NOT a QueryDict, template must use "in form_data.resin" (not .getlist.resin)
                    'resin': [str(rid) for rid in resin_ids],
                    'process': process_names,
                    'specification': spec_names,
                }
                # show the "View Files" button, and to populate its modal.
                attachments = list(
                    tbl_cmf_scanned.objects.filter(cm=cmf).order_by('-file_id').values(
                        'file_id', 'file_name', 'file_type'
                    )
                )
    allowed_departments = ['Laboratory', 'Information Technology', 'Sales']
    is_allowed = request.user.role.department in allowed_departments or request.user.is_superuser
    context = {
        "customers": cmf_records_services.get_customer_list(), 
        "salesman": cmf_records_services.get_salesman_list(),
        "primary_color": cmf_records_services.get_color_list(),
        "resin": cmf_records_services.get_resin_list(),
        "form_data": form_data,
        "attachments": attachments,
        'is_allowed': is_allowed,
    }
    return render(request, "sidemenu/cmf/cmf_entry.html", context)

@permission_required(allowed_departments=['Laboratory', 'Information Technology', 'Sales'])
def cmf_rs_entry(request):
    form_data = {}

    if request.method == "POST":
        original_rs_no = request.POST.get('original_rs_no', '').strip()
        try:
            if original_rs_no:
                saved_record = rs_entry_save.update_rs_complete_entry(request, original_rs_no)
                messages.success(request, f"Successfully updated RS No. {saved_record.rs_no}")
            else:
                saved_record = rs_entry_save.save_rs_complete_entry(request)
                messages.success(request, f"RS {saved_record.rs_no} saved successfully.")

            return redirect('rs_entry')

        except Exception as e:
            messages.error(request, f"Error: {str(e)}")
            form_data = request.POST

    else:
        record_id = request.GET.get('no')
        if record_id:
            rs_instance = tbl_rs.objects.filter(id=record_id).first()
            if rs_instance:
                form_data = rs_entry_save.build_form_data(rs_instance)
            else:
                messages.error(request, f"RS record with ID {record_id} not found.")
    allowed_departments = ['Laboratory', 'Information Technology', 'Sales']
    is_allowed = request.user.role.department in allowed_departments or request.user.is_superuser

    context = {
        "customers": cmf_records_services.get_customer_list(), 
        "salesman": cmf_records_services.get_salesman_list(),
        "primary_color": cmf_records_services.get_color_list(),
        "resin": cmf_records_services.get_resin_list(),
        "form_data": form_data,
        'is_allowed': is_allowed,
    }
    return render(request, "sidemenu/cmf/rs_entry.html", context)

def _build_dc_formula_list(dc_qs):
    """
    Builds the DC formula list for a detail view: each formula's header
    plus its materials, each material carrying a dict of {version_no: value}
    for every version that was actually entered (missing versions simply
    aren't in the dict, rather than being padded with blanks — detail
    views display what exists, unlike the entry form's fixed 10-slot grid).
    """
    dc_list = []
    for f in dc_qs:
        materials = []
        dc_materials = tbl_dc_extruder_materials.objects.filter(dc=f).order_by('material_id')
        for m in dc_materials:
            versions = {v.version_no: v.value for v in m.versions.all()}
            materials.append({
                'material': m.material,
                'versions': versions,  # e.g. {1: Decimal('12.5'), 3: Decimal('8.0')}
            })
        dc_list.append({'header': f, 'materials': materials})
    return dc_list

@role_required
def cmf_record_detail(request, cm_no):
    # Get the base number by removing the last character (e.g., 'CM24-001A' -> 'CM24-001')
    base_no = cm_no[:-1]

    # Fetch all records that share this base prefix
    cmf_revisions = tbl_cmf.objects.filter(cm_no__startswith=base_no).order_by('-cm_no')

    # This will hold the complete data for every revision found
    revisions_data = []

    for cmf in cmf_revisions:
        # Fetch data specific to this revision
        formula_info = tbl_cmf_formula.objects.filter(cm_no=cmf.cm_no).first()
        pending_info = tbl_cmf_pending_completed.objects.filter(cm_no=cmf.cm_no).select_related('code').first()

        # MB Formulas for this revision
        mb_list = []
        mb_qs = tbl_mb_extruder_formula.objects.filter(cm_no=cmf.cm_no).select_related('code')
        for f in mb_qs:
            ingredients = tbl_mb_extruder_formula02.objects.filter(mb=f)
            mb_list.append({'header': f, 'ingredients': ingredients})

        # DC Formulas for this revision
        dc_qs = tbl_dc_extruder_formula.objects.filter(cm_no=cmf.cm_no).select_related('code')
        dc_list = _build_dc_formula_list(dc_qs)

        revisions_data.append({
            'cmf': cmf,
            'formula_info': formula_info,
            'pending_info': pending_info,
            'mb_formulas': mb_list,
            'dc_formulas': dc_list,
        })

    context = {
        'revisions': revisions_data,
        'base_no': base_no
    }

    return render(request, "modal/cmf-record/cmf_record_detail.html", context)

@role_required
def rs_record_detail(request, rs_id):
    # rs_id is the row's real primary key (unique), since rs_no can now repeat.
    rs_instance = tbl_rs.objects.filter(pk=rs_id).first()
    if not rs_instance:
        return render(request, "modal/cmf-record/rs_record_detail.html", {"revisions": []})

    # Group all RS rows sharing the same rs_no — mirrors CMF's "revisions" concept
    # (which groups by cm_no prefix), since duplicate rs_no values now represent
    # related/re-submitted entries rather than distinct records.
    rs_revisions = tbl_rs.objects.filter(rs_no=rs_instance.rs_no).order_by('-id')

    revisions_data = []
    for rs in rs_revisions:
        pending_info = tbl_cmf_pending_completed.objects.filter(rs_no=rs).select_related('code').first()

        mb_list = []
        mb_qs = tbl_mb_extruder_formula.objects.filter(rs_no=rs).select_related('code')
        for f in mb_qs:
            ingredients = tbl_mb_extruder_formula02.objects.filter(mb=f)
            mb_list.append({'header': f, 'ingredients': ingredients})

        dc_qs = tbl_dc_extruder_formula.objects.filter(rs_no=rs).select_related('code')
        dc_list = _build_dc_formula_list(dc_qs)

        revisions_data.append({
            'rs': rs,
            'pending_info': pending_info,
            'mb_formulas': mb_list,
            'dc_formulas': dc_list,
        })

    context = {
        'revisions': revisions_data,
        'rs_no': rs_instance.rs_no,
    }

    return render(request, "modal/cmf-record/rs_record_detail.html", context)

@permission_required(allowed_departments=['Laboratory', 'Information Technology'])
def cmf_mb_formula(request):
    form_data = {}
    ingredients = []
    colorant_mismatch = False

    if request.method == "POST":
        try:
            saved_record = mb_formula_save.save_mb_complete_formula(request)
            parent_display = saved_record.cm_no.cm_no if saved_record.cm_no else saved_record.rs_no.rs_no
            messages.success(request, f"Successfully saved MB Formula for {parent_display}")
            cache.delete('cmf_records_list')
            return redirect('mb_formula')
        except Exception as e:
            messages.error(request, f"Error saving formula: {str(e)}")
            form_data = request.POST

    else:
        record_no = request.GET.get('no')
        record_type = request.GET.get('type', 'cmf')
        formula_id = request.GET.get('formula_id')

        cmf = None  # only set when record_type == 'cmf'
        rs = None   # only set when record_type == 'rs'

        if record_no and record_type == 'cmf':
            cmf = tbl_cmf.objects.filter(cm_no=record_no).first()
            if cmf:
                colorant_mismatch = cmf.colorant_type != "MB"

                formula_info = tbl_cmf_formula.objects.filter(cm_no=record_no).first()

                resins_list = tbl_resins_selected.objects.filter(
                    cm_no=record_no
                ).values_list('resin_no__abbreviation', flat=True)
                resin_used_str = ", ".join(resins_list)

                processes = tbl_cmf_process02.objects.filter(
                    cmf_formula_no__cm_no=record_no
                ).values_list('process_no__name', flat=True)
                application_str = ", ".join(processes)

                form_data = {
                    'cm_form_no': record_no,
                    'record_id': record_no,
                    'customer': formula_info.customer if formula_info else "",
                    'resin_used': resin_used_str,
                    'dosage': formula_info.dosage if formula_info else "",
                    'finished_product': formula_info.finished_product if formula_info else "",
                    'notes': formula_info.finished_product if formula_info else "",
                    'color': cmf.in_code_no.color if cmf.in_code_no else "",
                    'product': cmf.in_code_no.code if cmf.in_code_no else "",
                    'application': application_str,
                    'record_type': 'cmf',
                }
            else:
                messages.error(request, f"CMF No. {record_no} not found.")

        if record_no and record_type == 'rs':
            rs = tbl_rs.objects.filter(id=record_no).first()
            if rs:
                colorant_mismatch = rs.colorant_type != "MB"

                # Resin — same pattern as CMF, filtered via the rs_no FK on tbl_resins_selected
                resins_list = tbl_resins_selected.objects.filter(
                    rs_no=rs
                ).values_list('resin_no__abbreviation', flat=True)
                resin_used_str = ", ".join(resins_list)

                # Process — same pattern as CMF, but tbl_cmf_process02 links directly via rs_no
                # here rather than through a formula record (RS has no tbl_cmf_formula row)
                processes = tbl_cmf_process02.objects.filter(
                    rs_no=rs
                ).values_list('process_no__name', flat=True)
                application_str = ", ".join(processes)

                # Product code lives on tbl_cmf_pending_completed for RS records
                pending = tbl_cmf_pending_completed.objects.filter(rs_no=rs).select_related('code').first()

                form_data = {
                    'cm_form_no': rs.rs_no,
                    'record_id': rs.pk,
                    'customer': rs.customer or "",
                    'resin_used': resin_used_str,
                    'dosage': rs.dosage or getattr(rs, 'dosage', '') or '',
                    'finished_product': rs.finished_product or "",
                    'color': rs.primary_color or "",
                    'product': pending.code.product_code if pending else "",
                    'application': application_str,
                    'record_type': 'rs',
                }
            else:
                messages.error(request, f"RS record with ID {record_no} not found.")

        # --- Load a SPECIFIC historical MB formula, if one was clicked ---
        # tbl_mb_extruder_formula has both cm_no and rs_no FKs, so the filter
        # needs to match whichever side actually resolved above.
        if formula_id:
            header = None
            if cmf:
                header = tbl_mb_extruder_formula.objects.filter(pk=formula_id, cm_no=cmf).first()
            elif rs:
                header = tbl_mb_extruder_formula.objects.filter(pk=formula_id, rs_no=rs).first()

            if header:
                form_data.update({
                    'formula_id': header.pk,
                    'date': header.date.strftime('%m/%d/%Y') if header.date else "",
                    'product': header.code.product_code if header.code else "",
                    'lot_number': header.lot_no or "",
                    'mixing_time': header.mixing_time or "",
                    'note': header.notes or "",
                    'matched_by': header.matched_by or "",
                    'weighed_by': header.weighted_by or "",
                    'encoded_by': header.encoded_by or "",
                    'total_weight': header.total_weight,
                    'spectro_l': header.L,
                    'spectro_a': header.A,
                    'spectro_b': header.B,
                    'spectro_c': header.C,
                    'spectro_h': header.H,
                    'srgb_hex': header.html or "",
                    'cmyk_c': header.c,
                    'cmyk_m': header.m,
                    'cmyk_y': header.y,
                    'cmyk_k': header.k,
                    'matcher_id': header.matcher.id if header.matcher else "",
                    'is_final': True if header.is_final else False,
                })

                ingredients = list(
                    tbl_mb_extruder_formula02.objects.filter(mb=header)
                    .values('material', 'value', 'weight')
                )
                ingredients = ingredients + [{'material': '', 'value': '', 'weight': ''}] * (10 - len(ingredients))
                ingredients = ingredients[:10]
            else:
                messages.error(request, f"Formula record not found for ID {formula_id}.")
    
    if not ingredients:
        ingredients = [{'material': '', 'value': '', 'weight': ''}] * 10
    user_list  = (
        User.objects.filter(is_active=True)
        .exclude(first_name="")
        .annotate(full_name=Concat('first_name', Value(' '), 'last_name'))
        .values('id', 'full_name')
        .distinct()
        .order_by('full_name')
    )

    # 1. Get CMF numbers
    cmf_nos = list(
        tbl_cmf.objects.filter(colorant_type='MB')
        .exclude(cm_no__isnull=True)
        .exclude(cm_no='')
        .values_list('cm_no', flat=True)
    )
    
    # 2. Get RS numbers where colorant_type is MB
    rs_nos = list(
        tbl_rs.objects.filter(colorant_type='MB')
        .exclude(rs_no__isnull=True)
        .exclude(rs_no='')
        .values_list('rs_no', flat=True)
    )
    
    # 3. Combine, unique (set), and sort descending
    combined_list = sorted(list(set(cmf_nos + rs_nos)), reverse=True)

    context = {
        "form_data": form_data,
        "materials": cmf_records_services.get_raw_material_codes(),
        "users": list(user_list),
        "colorant_mismatch": colorant_mismatch,
        "ingredients": ingredients,
        "cmf_list": combined_list,
    }
    return render(request, "sidemenu/cmf/formula_mb.html", context)

@permission_required(allowed_departments=['Laboratory', 'Information Technology'])
def cmf_dc_formula(request):
    form_data = {}
    material_rows = []
    colorant_mismatch = False

    if request.method == "POST":
        try:
            saved_record = dc_formula_save.save_dc_complete_formula(request)
            parent_display = saved_record.cm_no.cm_no if saved_record.cm_no else saved_record.rs_no.rs_no
            messages.success(request, f"Successfully saved DC Formula for {parent_display}")
            cache.delete('cmf_records_list')
            return redirect('dc_formula')
        except Exception as e:
            messages.error(request, f"Error saving formula: {str(e)}")
            form_data = request.POST

    else:
        record_no = request.GET.get('no')
        record_type = request.GET.get('type', 'cmf')
        formula_id = request.GET.get('formula_id')

        cmf = None  # only set when record_type == 'cmf'
        rs = None   # only set when record_type == 'rs'

        if record_no and record_type == 'cmf':
            cmf = tbl_cmf.objects.filter(cm_no=record_no).first()
            if cmf:
                colorant_mismatch = cmf.colorant_type != "DC"

                formula_info = tbl_cmf_formula.objects.filter(cm_no=record_no).first()

                resins_list = tbl_resins_selected.objects.filter(cm_no=record_no).values_list('resin_no__abbreviation', flat=True)
                resin_str = ", ".join(resins_list)

                processes = tbl_cmf_process02.objects.filter(cmf_formula_no__cm_no=record_no).values_list('process_no__name', flat=True)
                app_str = ", ".join(processes)

                form_data = {
                    'cm_form_no': record_no,
                    'record_id': record_no,
                    'customer': formula_info.customer if formula_info else "",
                    'resin': resin_str,
                    'dosage': formula_info.dosage if formula_info else "",
                    'finished_product': formula_info.finished_product if formula_info else "",
                    'color': cmf.in_code_no.color if cmf.in_code_no else "",
                    'application': app_str,
                    'record_type': 'cmf',
                }
            else:
                messages.error(request, f"CMF No. {record_no} not found.")

        elif record_no and record_type == 'rs':
            rs = tbl_rs.objects.filter(pk=record_no).first()
            if rs:
                colorant_mismatch = rs.colorant_type != "DC"

                # Resin — same pattern as CMF, filtered via the rs_no FK on tbl_resins_selected
                resins_list = tbl_resins_selected.objects.filter(rs_no=rs).values_list('resin_no__abbreviation', flat=True)
                resin_str = ", ".join(resins_list)

                # Process — tbl_cmf_process02 links directly via rs_no for RS records
                # (no tbl_cmf_formula row to go through, unlike CMF)
                processes = tbl_cmf_process02.objects.filter(rs_no=rs).values_list('process_no__name', flat=True)
                app_str = ", ".join(processes)
                # Product code lives on tbl_cmf_pending_completed for RS records
                pending = tbl_cmf_pending_completed.objects.filter(rs_no=rs).select_related('code').first()

                form_data = {
                    'cm_form_no': rs.rs_no,
                    'record_id': rs.pk,
                    'customer': rs.customer or "",
                    'resin': resin_str,
                    'dosage': getattr(rs, 'dosage', '') or '',
                    'finished_product': rs.finished_product or "",
                    'color': rs.primary_color or "",
                    'product_code': pending.code.product_code if pending else "",
                    'application': app_str,
                    'record_type': 'rs',
                }
            else:
                messages.error(request, f"RS record with ID {record_no} not found.")

        # --- Load a SPECIFIC historical DC formula, if one was clicked ---
        # tbl_dc_extruder_formula has both cm_no and rs_no FKs, so the filter
        # needs to match whichever side actually resolved above.
        if formula_id:
            header = None
            if cmf:
                header = tbl_dc_extruder_formula.objects.filter(pk=formula_id, cm_no=cmf).first()
            elif rs:
                header = tbl_dc_extruder_formula.objects.filter(pk=formula_id, rs_no=rs).first()

            if header:
                form_data.update({
                    'formula_id': header.pk,
                    'date_matched': header.date.strftime('%m/%d/%Y') if header.date else "",
                    'product_code': header.code.product_code if header.code else "",
                    'material_code_id': header.material_code_id or "",
                    'sample_size': header.sample_size or "",
                    'mixing_time': header.mixing_time or "",
                    'note': header.notes or "",
                    'matched_by': header.matched_by or "",
                    'weighed_by': header.weighted_by or "",
                    'encoded_by': header.encoded_by or "",
                    'total_weight': header.total_weight,
                    'spectro_l': header.L,
                    'spectro_a': header.A,
                    'spectro_b': header.B,
                    'spectro_c': header.C,
                    'spectro_h': header.H,
                    'srgb_hex': header.html or "",
                    'cmyk_c': header.c,
                    'cmyk_m': header.m,
                    'cmyk_y': header.y,
                    'cmyk_k': header.k,
                    'matcher_id': header.matcher.id if header.matcher else "",
                })

                # Build the material_rows grid: one row per material, each
                # holding a 10-slot list of version values (None where
                # that material has no entry for that particular version).
                dc_materials = list(
                    tbl_dc_extruder_materials.objects.filter(dc=header).order_by('material_id')
                )
                versions_by_material = {
                    m.material_id: {v.version_no: v.value for v in m.versions.all()}
                    for m in dc_materials
                }

                material_rows = []
                for m in dc_materials:
                    version_map = versions_by_material.get(m.material_id, {})
                    material_rows.append({
                        'material': m.material,
                        'versions': [version_map.get(v) for v in range(1, 11)],
                    })

                # Pad to 10 rows for the fixed-size grid.
                while len(material_rows) < 10:
                    material_rows.append({'material': '', 'versions': [None] * 10})
                material_rows = material_rows[:10]
            else:
                messages.error(request, f"Formula record not found for ID {formula_id}.")

    if not material_rows:
        material_rows = [{'material': '', 'versions': [None] * 10} for _ in range(10)]

    user_list  = (
        User.objects.filter(is_active=True)
        .exclude(first_name="")
        .annotate(full_name=Concat('first_name', Value(' '), 'last_name'))
        .values('id', 'full_name')
        .distinct()
        .order_by('full_name')
    )

    # 1. Get CMF numbers
    cmf_nos = list(
        tbl_cmf.objects.filter(colorant_type='DC')
        .exclude(cm_no__isnull=True)
        .exclude(cm_no='')
        .values_list('cm_no', flat=True)
    )
    
    # 2. Get RS numbers where colorant_type is DC
    rs_nos = list(
        tbl_rs.objects.filter(colorant_type='DC')
        .exclude(rs_no__isnull=True)
        .exclude(rs_no='')
        .values_list('rs_no', flat=True)
    )
    
    # 3. Combine, unique (set), and sort descending
    combined_list = sorted(list(set(cmf_nos + rs_nos)), reverse=True)
    coding_materials = tbl_coding_materials.objects.filter(is_deleted=False).order_by('name')
    context = {
        "form_data": form_data,
        "materials": cmf_records_services.get_raw_material_codes(),
        "users": list(user_list),
        "colorant_mismatch": colorant_mismatch,
        "material_rows": material_rows,
        "cmf_list": combined_list,
        "coding_materials": coding_materials,
    }
    return render(request, "sidemenu/cmf/formula_dc.html", context)

@permission_required(allowed_departments=['Laboratory', 'Information Technology'])
def cmf_pending_completed(request):
    form_data = {}
    record_no = request.POST.get('record_no') or request.GET.get('no')
    record_type = request.POST.get('record_type') or request.GET.get('type', 'cmf')

    # --- HELPERS ---
    def format_val(val):
        """Standardizes values for audit comparison."""
        if val is True: return "Completed"
        if val is False: return "Pending"
        if val is None or val == "" or val == "None": return "---"
        if isinstance(val, (date, datetime)):
            return val.strftime('%m/%d/%Y')
        if isinstance(val, (Decimal, float)):
            return format(float(val), ".2f")
        return str(val).strip()
    def parse_date(d_str):
        if not d_str: return None
        try: return datetime.strptime(d_str.strip(), '%m/%d/%Y').date()
        except ValueError: return None

    def get_prod_code_obj(code_str):
        if not code_str or not code_str.strip(): return None
        obj, _ = tbl_generated_prod_code.objects.get_or_create(product_code=code_str.strip())
        return obj

    if request.method == "POST":
        try:
            data = request.POST
            diff_logs = []
            tracking_instance = None
            feedback_instance = None
            parent_display = ""

            # 1. Identify Parent and Get/Create Instances
            if record_type == 'cmf':
                cmf_obj = tbl_cmf.objects.filter(cm_no=record_no).first()
                if not cmf_obj: raise Exception(f"CMF {record_no} not found.")
                tracking_instance, _ = tbl_cmf_pending_completed.objects.get_or_create(cm_no=cmf_obj)
                feedback_instance, _ = tbl_feedback_details.objects.get_or_create(cm_no=cmf_obj)
                parent_display = f"CMF: {record_no}"
            else:
                rs_obj = tbl_rs.objects.filter(pk=record_no).first()
                if not rs_obj: raise Exception(f"RS record not found.")
                tracking_instance, _ = tbl_cmf_pending_completed.objects.get_or_create(rs_no=rs_obj)
                feedback_instance, _ = tbl_feedback_details.objects.get_or_create(rs_no=rs_obj)
                parent_display = f"RS: {rs_obj.rs_no}"

            # 2. Update Map for Tracking Table
            update_map = {
                'status': (tracking_instance, 'is_completed', 'Status', lambda x: x == 'Completed'),
                'pending_reason': (tracking_instance, 'reason', 'Reason', str),
                'product_code': (tracking_instance, 'code', 'Product Code', get_prod_code_obj),
                'lot_no': (tracking_instance, 'lot_no', 'Lot Number', str),
                'code_description': (tracking_instance, 'code_details', 'Code Details', str),
                'date_submitted': (tracking_instance, 'date_submitted', 'Date Submitted', parse_date),
                'ar_no': (tracking_instance, 'ar_no', 'AR No.', str),
                'ar_date': (tracking_instance, 'ar_date', 'AR Date', parse_date),
            }

            # 3. Update Map for Feedback Table
            feedback_map = {
                'qty_given': (feedback_instance, 'quantity_given', 'Qty Given', lambda x: Decimal(x) if x else None),
                'set_pc': (feedback_instance, 'pieces', 'Sets/Pcs', lambda x: int(x) if x else None),
            }

            with transaction.atomic():
                # Process Tracking Diffs
                for post_key, (inst, attr, label, transform) in update_map.items():
                    current_val = getattr(inst, attr)
                    new_val = transform(data.get(post_key, ''))
                    
                    curr_str = format_val(current_val.product_code if attr == 'code' and current_val else current_val)
                    new_str = format_val(new_val.product_code if attr == 'code' and new_val else new_val)

                    if curr_str != new_str:
                        diff_logs.append(f"{label} ({curr_str} -> {new_str})")
                        setattr(inst, attr, new_val)

                # Process Feedback Diffs
                for post_key, (inst, attr, label, transform) in feedback_map.items():
                    current_val = getattr(inst, attr)
                    new_val = transform(data.get(post_key, ''))
                    
                    curr_str, new_str = format_val(current_val), format_val(new_val)
                    if curr_str != new_str:
                        diff_logs.append(f"{label} ({curr_str} -> {new_str})")
                        setattr(inst, attr, new_val)

                # Sync Code FK to Feedback
                if feedback_instance.code != tracking_instance.code:
                    feedback_instance.code = tracking_instance.code

                if diff_logs:
                    tracking_instance.save()
                    feedback_instance.save()

                # --- 4. Sync Submitted Options (Sample/Chips/Price) ---
                # tracking_instance needs a pk before we can attach selections to it.
                if tracking_instance.pk is None:
                    tracking_instance.save()

                submitted_ids = set(int(i) for i in data.getlist('submitted_options') if i.isdigit())
                existing_ids = set(
                    tbl_submitted_selected.objects
                    .filter(completed_id=tracking_instance)
                    .values_list('option_id', flat=True)
                )

                if submitted_ids != existing_ids:
                    to_add = submitted_ids - existing_ids
                    to_remove = existing_ids - submitted_ids

                    if to_remove:
                        tbl_submitted_selected.objects.filter(
                            completed_id=tracking_instance, option_id__in=to_remove
                        ).delete()

                    if to_add:
                        # option_id is a literal field name ending in "_id", so Django
                        # requires an actual related object here — a raw pk int is rejected.
                        option_objs = tbl_submitted_option.objects.filter(option_id__in=to_add)
                        for option_obj in option_objs:
                            tbl_submitted_selected.objects.get_or_create(
                                completed_id=tracking_instance, option_id=option_obj
                            )

                    old_names = list(
                        tbl_submitted_option.objects.filter(option_id__in=existing_ids).values_list('name', flat=True)
                    )
                    new_names = list(
                        tbl_submitted_option.objects.filter(option_id__in=submitted_ids).values_list('name', flat=True)
                    )
                    diff_logs.append(
                        f"Submitted ({', '.join(old_names) or '---'} -> {', '.join(new_names) or '---'})"
                    )

                if diff_logs:
                    log_audit(request, "Updated", f"Updated Status for {parent_display}. Changes: {', '.join(diff_logs)}")
                    messages.success(request, f"Successfully updated tracking for {parent_display}")
                    cache.delete('cmf_records_list')
                    cache.delete('rs_records_list')
                else:
                    messages.info(request, "No changes detected.")

                return redirect(f"{request.path}?no={record_no}&type={record_type}")

        except Exception as e:
            messages.error(request, f"Error updating record: {str(e)}")

    # --- GET LOGIC ---
    all_options = list(tbl_submitted_option.objects.all())

    if record_no:
        if record_type == 'cmf':
            cmf = tbl_cmf.objects.filter(cm_no=record_no).first()
            if cmf:
                dates = tbl_cmf_dates.objects.filter(cm_no=cmf).first()
                formula_info = tbl_cmf_formula.objects.filter(cm_no=cmf).first()
                tracking = tbl_cmf_pending_completed.objects.filter(cm_no=cmf).select_related('code').first()
                feedback = tbl_feedback_details.objects.filter(cm_no=cmf).first()
                
                is_dc = (cmf.colorant_type or "").upper() == 'DC'
                final_formula = tbl_mb_extruder_formula.objects.filter(cm_no=cmf, is_final=True).select_related('code').first()
                if not final_formula:
                    final_formula = tbl_dc_extruder_formula.objects.filter(cm_no=cmf, is_final=True).select_related('code').first()
                    if final_formula: is_dc = True

                final_prod_code = final_formula.code.product_code if final_formula and final_formula.code else (tracking.code.product_code if tracking and tracking.code else "")
                
                selected_lot = "N/A" if is_dc else (tracking.lot_no if tracking and tracking.lot_no else (final_formula.lot_no if final_formula else ""))
                lot_options = ["N/A"] if is_dc else []
                if not is_dc and final_formula and final_formula.code:
                    mb_lots = tbl_mb_extruder_formula.objects.filter(cm_no=cmf, code=final_formula.code).values_list('lot_no', flat=True)
                    lot_options = sorted(list(set(filter(None, mb_lots))), reverse=True)

                selected_option_ids = list(
                    tbl_submitted_selected.objects.filter(completed_id=tracking).values_list('option_id', flat=True)
                ) if tracking else []

                form_data = {
                    'cmf_no': cmf.cm_no,
                    'customer': formula_info.customer if formula_info else "",
                    'date_created': format_val(dates.form_made) if dates else "",
                    'due_date': format_val(dates.due_date_lab) if dates else "",
                    'required_date': dates.date_required if dates else "",
                    'date_received': dates.date_received_lab if dates else "",
                    'finished_product': formula_info.finished_product if formula_info else "",
                    'color_description': cmf.color_desc,
                    'matchType': cmf.matching_type.upper() if cmf.matching_type else "",
                    'colorantType': cmf.colorant_type.upper() if cmf.colorant_type else "",
                    'salesman': cmf.sm.name if cmf.sm else "",
                    'status': 'Completed' if (tracking and tracking.is_completed) else 'Pending',
                    'pending_reason': tracking.reason if tracking else "",
                    'product_code': final_prod_code,
                    'lot_no': selected_lot,
                    'lot_options': lot_options,
                    'is_dc': is_dc,
                    'qty_given': feedback.quantity_given if feedback else "",
                    'set_pc': feedback.pieces if feedback else "",
                    'code_description': tracking.code_details if tracking else "",
                    'date_submitted': format_val(tracking.date_submitted) if tracking else "",
                    'ar_no': tracking.ar_no if tracking else "",
                    'ar_date': format_val(tracking.ar_date) if tracking else "",
                    'submitted_options': all_options,
                    'selected_option_ids': selected_option_ids,
                    'record_no': cmf.cm_no,
                    'record_type': 'cmf',
                }

        elif record_type == 'rs':
            rs = tbl_rs.objects.filter(id=record_no).first()
            if rs:
                tracking = tbl_cmf_pending_completed.objects.filter(rs_no=rs).select_related('code').first()
                feedback = tbl_feedback_details.objects.filter(rs_no=rs).first()
                dates = tbl_cmf_dates.objects.filter(rs_no=rs).first()
                resins_list = tbl_resins_selected.objects.filter(rs_no=rs).values_list('resin_no__abbreviation', flat=True)
                processes = tbl_cmf_process02.objects.filter(rs_no=rs).values_list('process_no__name', flat=True)

                is_dc = (rs.colorant_type or "").upper() == 'DC'
                final_prod_code = tracking.code.product_code if tracking and tracking.code else ""

                selected_lot = "N/A" if is_dc else (tracking.lot_no if tracking else "")
                lot_options = ["N/A"] if is_dc else []
                if not is_dc and tracking and tracking.code:
                    mb_lots = tbl_mb_extruder_formula.objects.filter(rs_no=rs, code=tracking.code).values_list('lot_no', flat=True)
                    lot_options = sorted(list(set(filter(None, mb_lots))), reverse=True)

                selected_option_ids = list(
                    tbl_submitted_selected.objects.filter(completed_id=tracking).values_list('option_id', flat=True)
                ) if tracking else []
                
                form_data = {
                    'rs_no': rs.rs_no,
                    'customer': rs.customer or "",
                    'quantity_kg': rs.quantity_required or "",
                    'date_created': format_val(dates.form_made) if dates else "",
                    'due_date': format_val(dates.due_date_lab) if dates else "",
                    'required_date': dates.date_required if dates else "",
                    'date_received': dates.date_received_lab if dates else "",
                    'finished_product': rs.finished_product or "",
                    'color_description': rs.color_desc or "",
                    'matchType': rs.matching_type.upper() if rs.matching_type else "",
                    'colorantType': rs.colorant_type.upper() if rs.colorant_type else "",
                    'salesman': rs.sm_no.name if rs.sm_no else "",
                    'status': 'Completed' if (tracking and tracking.is_completed) else 'Pending',
                    'resin': ", ".join(resins_list),
                    'application': ", ".join(processes),
                    'pending_reason': tracking.reason if tracking else "",
                    'product_code': final_prod_code,
                    'lot_no': selected_lot,
                    'lot_options': lot_options,
                    'is_dc': is_dc,
                    'qty_given': feedback.quantity_given if feedback else "",
                    'set_pc': feedback.pieces if feedback else "",
                    'code_description': tracking.code_details if tracking else "",
                    'date_submitted': format_val(tracking.date_submitted) if tracking else "",
                    'ar_no': tracking.ar_no if tracking else "",
                    'ar_date': format_val(tracking.ar_date) if tracking else "",
                    'submitted_options': all_options,
                    'selected_option_ids': selected_option_ids,
                    'record_no': rs.id,
                    'record_type': 'rs',
                }
    else:
        form_data['submitted_options'] = all_options
        form_data['selected_option_ids'] = []

    return render(request, "sidemenu/cmf/pending_completed.html", {"form_data": form_data})

@permission_required(allowed_departments=['Laboratory', 'Information Technology'])
def master_formula(request):
    form_id = request.GET.get('form_id')
    
    if request.method == "POST":
        success, result = master_formula_services.save_master_formula(request)
        if success:
            messages.success(request, f"Master Formula #{result} saved successfully.")
            return redirect(f"/master-formula/?form_id={result}")
        else:
            messages.error(request, f"Error saving formula: {result}")

    # GET logic
    if form_id and not master_formula_services.get_master_formula_details(form_id):
        messages.error(request, f"Master Formula #{form_id} not found.")

    context = master_formula_services.get_master_formula_context(form_id, request)
    return render(request, "sidemenu/formula/master_formula.html", context)

@role_required
def formulation(request):
    form_id = request.GET.get('form_id')
    
    if request.method == "POST":
        success, result = formulation_services.save_formulation(request)
        if success:
            messages.success(request, f"Formulation #{result} saved successfully.")
            return redirect(f"/formulation/?form_id={result}")
        else:
            messages.error(request, f"Error saving formulation: {result}")

    # GET logic
    if form_id and not formulation_services.get_formulation_details(form_id):
        messages.error(request, f"Formulation #{form_id} not found.")

    context = formulation_services.get_formulation_context(form_id, request)
    return render(request, "sidemenu/formula/formulation.html", context)

@role_required
def feedback(request):
    feedback_no = request.GET.get('feedback_no') or request.POST.get('feedback_no')

    # --- 1. POST LOGIC (SAVE/UPDATE) ---
    if request.method == "POST":
        success, message = feedback_save.save_feedback_entry(request, feedback_no)
        if success:
            messages.success(request, message)
        else:
            messages.error(request, message)
        return redirect(f"{request.path}?feedback_no={feedback_no}")

    # --- 2. GET LOGIC (LOAD SINGLE RECORD) ---
    form_data = {}
    if feedback_no:
        form_data = feedback_save.get_feedback_form_data(feedback_no)
        if not form_data:
            messages.error(request, f"Feedback record with ID {feedback_no} not found.")

    # --- 3. LOAD RECORDS LIST ---
    records_list = feedback_save.get_feedback_records()

    context = {
        'feedback_records': records_list,
        'record_count': len(records_list),
        'form_data': form_data,
    }
    return render(request, "sidemenu/feedback/feedback.html", context)

@permission_required(allowed_roles=['ADMIN', 'HEAD'])
def audit_trail(request):
    # 1. Get total record count
    record_count = tbl_audit_trail.objects.count()
    
    # 2. Get the date of the earliest record (to default 'dateFrom')
    min_timestamp = tbl_audit_trail.objects.aggregate(Min('timestamp'))['timestamp__min']
    
    # Fallback to today if no records exist
    if min_timestamp:
        default_from = min_timestamp.date().strftime('%Y-%m-%d')
    else:
        default_from = timezone.now().date().strftime('%Y-%m-%d')
        
    # 3. Get today's date for 'dateTo' and for the 'max' limit
    today = timezone.now().date().strftime('%Y-%m-%d')

    context = {
        "record_count": record_count,
        "default_from": default_from,
        "default_to": today,
    }
    return render(request, "sidemenu/audit_trail.html", context)

@role_required
def settings(request):
    # maintenance message for page
    return redirect(f"{reverse('maintenance')}?feature=Settings")
    # return render(request, 'settings/settings.html')




# EXPORT 
def cmf_records_export_preview(request):
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    include_rs = request.GET.get('include_rs') == '1'
    include_completed = request.GET.get('completed', '1') == '1'
    include_pending = request.GET.get('pending', '1') == '1'

    pending_rows, completed_rows = cmf_record_export.get_export_data(
        date_from, date_to, include_completed, include_pending, include_rs
    )

    file_bytes = cmf_record_export.build_export_workbook(pending_rows, completed_rows, include_pending, include_completed)
    file_b64 = base64.b64encode(file_bytes).decode('ascii')
    filename = f"cmf_records_export_{date_from.replace('/', '-')}_to_{date_to.replace('/', '-')}.xlsx"

    context = {
        'date_from': date_from,
        'date_to': date_to,
        'include_rs': include_rs,
        'include_completed': include_completed,
        'include_pending': include_pending,
        'pending_rows': pending_rows,
        'completed_rows': completed_rows,
        'export_file_b64': file_b64,
        'export_filename': filename,
    }
    return render(request, "sidemenu/export/cmf_report_preview.html", context)





# legacy sync
def trigger_legacy_sync(request):
    # Get the 'only' parameter from the URL if provided (optional)
    sync_type = request.GET.get('type') 
    
    try:
        if sync_type:
            # Equivalent to: python manage.py sync_dbf --only <sync_type>
            call_command('sync_dbf', only=sync_type)
        else:
            # Equivalent to: python manage.py sync_dbf
            call_command('sync_dbf')
            
        messages.success(request, f"Legacy {sync_type or 'all'} data synced successfully!")
    except Exception as e:
        messages.error(request, f"Sync failed: {str(e)}")
        
    # Redirect back to the page you came from
    return redirect(request.META.get('HTTP_REFERER', 'cmf_records'))