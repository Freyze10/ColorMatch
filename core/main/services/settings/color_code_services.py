from django.db import transaction
from main.models import tbl_internal_color_code
from main.utils.log_audit_trail import log_audit

def get_color_codes_for_user(user):
    """Admins/Superusers see all active entries; regular users see active entries + their own pending ones if needed, or all active entries."""
    return tbl_internal_color_code.objects.filter(is_deleted=False).order_by('-in_code_no')

def create_color_code(request):
    data = request.POST
    color = data.get('color', '').strip()
    code = data.get('code', '').strip()

    if not color or not code:
        return False, "Color and Code fields are required."

    with transaction.atomic():
        # Non-superusers default to 'pending', superusers can default directly to 'approved' if desired, 
        # or everything starts as pending for review. Let's start non-admin requests as 'pending'.
        status = 'approved' if (request.user.is_superuser or getattr(request.user.role, 'role', '') == 'Admin') else 'pending'

        obj = tbl_internal_color_code.objects.create(
            color=color,
            code=code,
            status=status
        )
        
        log_audit(request, "Created", f"Requested primary color code entry: {code} - {color} (Status: {status})")
    return True, "Primary color code submitted successfully."

def update_color_code(request, code_id):
    data = request.POST
    new_color = data.get('color', '').strip()
    new_code = data.get('code', '').strip()

    if not new_color or not new_code:
        return False, "Color and Code fields are required."

    with transaction.atomic():
        obj = tbl_internal_color_code.objects.filter(pk=code_id, is_deleted=False).first()
        if not obj:
            return False, "Color code record not found."

        # 🛑 Enforce rule: Only allow modification if status is pending
        if obj.status != 'pending':
            return False, "This color code can no longer be modified because it is no longer pending."

        old_color, old_code = obj.color, obj.code
        
        obj.color = new_color
        obj.code = new_code
        obj.save(update_fields=['color', 'code'])

        log_audit(request, "Updated", f"Modified pending color code entry from ({old_code} - {old_color}) to ({new_code} - {new_color})")

    return True, "Color code updated successfully."

def soft_delete_color_code(request, code_id):
    # 🛑 Restrict deletion strictly to Superusers / Admins
    if not (request.user.is_superuser or getattr(request.user.role, 'role', '') == 'Admin'):
        return False, "Permission denied: Only administrators can delete color codes."

    with transaction.atomic():
        obj = tbl_internal_color_code.objects.filter(pk=code_id, is_deleted=False).first()
        if not obj:
            return False, "Color code record not found."

        obj.is_deleted = True
        obj.save(update_fields=['is_deleted'])

        log_audit(request, "Deleted", f"Soft-deleted primary color code entry: {obj.code} - {obj.color}")
    return True, "Color code deleted successfully."