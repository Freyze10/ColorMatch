from django.core.cache import cache
from django.db import transaction
from main.models import tbl_internal_color_code, tbl_primary_color
from main.utils.log_audit_trail import log_audit


def _is_admin(user):
    return user.is_superuser or getattr(user.role, 'role', '') == 'Admin'


# =====================================================================
# READ
# =====================================================================

def get_primary_colors():
    """Primary colors for the dropdown (only those whose internal color is still active)."""
    return (tbl_primary_color.objects
            .filter(in_code__is_deleted=False)
            .select_related('in_code')
            .order_by('in_code__color'))


def get_color_codes_for_user(user):
    """
    All active entries, each tagged with what kind of entry it is (used by the table):
      c.kind = 'primary'          -> an approved primary color
               'sub'              -> a sub color (c.parent_name = its primary color)
               'primary_request'  -> a requested primary color, not approved yet (or rejected)
               'other'            -> anything else (e.g. NA, which is not a primary color)
    """
    codes = list(
        tbl_internal_color_code.objects
        .filter(is_deleted=False)
        .select_related('primary_color__in_code')
        .order_by('-in_code_no')
    )
    for c in codes:
        c.parent_name = ''
        if c.primary_color_id is None:
            c.kind = 'primary_request' if c.status in ('pending', 'rejected') else 'other'
        elif c.primary_color.in_code_id == c.in_code_no:
            c.kind = 'primary'      # a primary color is listed under itself
        else:
            c.kind = 'sub'
            c.parent_name = c.primary_color.in_code.color
    return codes


# =====================================================================
# HELPERS
# =====================================================================

def _code_taken_by_primary(code, exclude_id=None):
    """True if another primary color (approved, or still requested) already uses this code."""
    approved = tbl_primary_color.objects.filter(
        in_code__is_deleted=False, in_code__code__iexact=code)
    requested = tbl_internal_color_code.objects.filter(
        is_deleted=False, status='pending', primary_color__isnull=True, code__iexact=code)
    if exclude_id:
        approved = approved.exclude(in_code_id=exclude_id)
        requested = requested.exclude(pk=exclude_id)
    return approved.exists() or requested.exists()


def _promote_to_primary(obj):
    """Make an internal color a primary color: add it to tbl_primary_color and list it under itself."""
    primary, _ = tbl_primary_color.objects.get_or_create(in_code=obj)
    obj.primary_color = primary
    obj.save(update_fields=['primary_color'])
    return primary


# =====================================================================
# WRITE
# =====================================================================

def create_color_code(request):
    """
    Two kinds of request, chosen by the hidden `request_type` field:
      sub     -> color name + a primary color from the dropdown; the code is COPIED from that primary
      primary -> color name + its own new code; becomes a primary color once approved

    Admins skip the approval step (saved as approved straight away).
    """
    data = request.POST
    request_type = data.get('request_type', '')
    color = data.get('color', '').strip()

    if not color:
        return False, "Color name is required."

    is_admin = _is_admin(request.user)
    status = 'approved' if is_admin else 'pending'

    with transaction.atomic():
        if request_type == 'sub':
            pid = data.get('primary_color_id', '').strip()
            primary = get_primary_colors().filter(pk=pid).first() if pid.isdigit() else None
            if not primary:
                return False, "Please select a primary color."

            obj = tbl_internal_color_code.objects.create(
                color=color,
                code=primary.in_code.code,   # copied from the primary color
                primary_color=primary,
                status=status,
            )
            log_audit(request, "Created",
                      f"Requested sub color: {color} under {primary.in_code.color} "
                      f"(code {obj.code}, Status: {status})")
            message = "Sub color added." if is_admin else "Sub color submitted for approval."

        elif request_type == 'primary':
            code = data.get('code', '').strip().upper()
            if not code:
                return False, "Code is required for a new primary color."
            if _code_taken_by_primary(code):
                return False, f"Code '{code}' is already used by another primary color."

            obj = tbl_internal_color_code.objects.create(color=color, code=code, status=status)
            if is_admin:
                _promote_to_primary(obj)   # admins: becomes a primary color immediately
            log_audit(request, "Created",
                      f"Requested primary color: {code} - {color} (Status: {status})")
            message = "Primary color added." if is_admin else "Primary color submitted for approval."

        else:
            return False, "Invalid request type."

    cache.delete('color_list')
    cache.delete('color_list_primary')
    return True, message


def update_color_code_status(request, code_id, new_status):
    if not _is_admin(request.user):
        return False, "Permission denied."

    with transaction.atomic():
        obj = (tbl_internal_color_code.objects
               .select_related('primary_color__in_code')
               .filter(pk=code_id, is_deleted=False).first())
        if not obj:
            return False, "Color code record not found."

        if new_status == 'approved':
            if obj.primary_color_id is None:
                # A requested PRIMARY color: re-check the code is still free, then add it to tbl_primary_color
                clash = (tbl_primary_color.objects
                         .filter(in_code__is_deleted=False, in_code__code__iexact=obj.code)
                         .exclude(in_code_id=obj.pk).exists())
                if clash:
                    return False, f"Code '{obj.code}' is already used by another primary color."
                _promote_to_primary(obj)
            elif obj.primary_color.in_code.is_deleted:
                return False, "Its primary color has been deleted. Reject this request instead."

        old_status = obj.status
        obj.status = new_status
        obj.save(update_fields=['status'])

        log_audit(request, "Updated", f"Color code {obj.code} status changed from {old_status} to {new_status}")
    # Refresh cache
    cache.delete('color_list')
    cache.delete('color_list_primary')
    return True, f"Color code successfully {new_status}."


def update_color_code(request, code_id):
    data = request.POST
    new_color = data.get('color', '').strip()

    if not new_color:
        return False, "Color name is required."

    with transaction.atomic():
        obj = tbl_internal_color_code.objects.filter(pk=code_id, is_deleted=False).first()
        if not obj:
            return False, "Color code record not found."

        # 🛑 Enforce rule: Only allow modification if status is pending
        if obj.status != 'pending':
            return False, "This color code can no longer be modified because it is no longer pending."

        old_color, old_code = obj.color, obj.code

        if obj.primary_color_id:
            # Pending SUB color: the code always follows the chosen primary color
            pid = data.get('primary_color_id', '').strip()
            primary = get_primary_colors().filter(pk=pid).first() if pid.isdigit() else None
            if not primary:
                return False, "Please select a primary color."
            obj.color = new_color
            obj.code = primary.in_code.code
            obj.primary_color = primary
            obj.save(update_fields=['color', 'code', 'primary_color'])
        else:
            # Pending PRIMARY request: the user edits the code itself
            new_code = data.get('code', '').strip().upper()
            if not new_code:
                return False, "Code is required."
            if _code_taken_by_primary(new_code, exclude_id=obj.pk):
                return False, f"Code '{new_code}' is already used by another primary color."
            obj.color = new_color
            obj.code = new_code
            obj.save(update_fields=['color', 'code'])

        log_audit(request, "Updated", f"Modified pending color code entry from ({old_code} - {old_color}) to ({obj.code} - {obj.color})")

    # Refresh cache
    cache.delete('color_list')
    cache.delete('color_list_primary')
    return True, "Color code updated successfully."


def soft_delete_color_code(request, code_id):
    with transaction.atomic():
        obj = tbl_internal_color_code.objects.filter(pk=code_id, is_deleted=False).first()
        if not obj:
            return False, "Color code record not found."

        # A primary color can't be deleted while sub colors still sit under it
        has_subs = (tbl_internal_color_code.objects
                    .filter(primary_color__in_code=obj, is_deleted=False)
                    .exclude(pk=obj.pk).exists())
        if has_subs:
            return False, "This primary color still has sub colors. Delete those first."

        obj.is_deleted = True
        obj.save(update_fields=['is_deleted'])

        log_audit(request, "Deleted", f"Soft-deleted internal color code entry: {obj.code} - {obj.color}")
    # Refresh cache
    cache.delete('color_list')
    cache.delete('color_list_primary')
    return True, "Color code deleted successfully."