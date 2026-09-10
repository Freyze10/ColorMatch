from django.contrib.auth import update_session_auth_hash, logout, get_user_model
from django.contrib.sessions.models import Session
from django.contrib import messages
from django.core.mail import send_mail
from django.urls import reverse
from django.utils import timezone
from django.shortcuts import get_object_or_404, redirect, render
from main.models import tbl_password_reset_request, tbl_role_permissions, tbl_access_point

User = get_user_model()


# --- PERMISSION CHECK ---

def has_password_requests_access(user):
    """Checks if the user's role is granted the 'Password Requests' access point."""
    if user.is_superuser:
        return True
    if not user.role:
        return False
    return tbl_role_permissions.objects.filter(
        role=user.role,
        access__access_name="Password Requests",
        is_enabled=True
    ).exists()


# --- PERSONAL INFO ---

def update_personal_info(request):
    """Returns (success: bool, message: str)."""
    user = request.user
    user.first_name = request.POST.get('first_name', user.first_name)
    user.last_name = request.POST.get('last_name', user.last_name)
    user.email = request.POST.get('email', user.email)
    user.save()
    return True, "Personal information updated successfully."


# --- CHANGE PASSWORD (logged-in user) ---

def change_own_password(request):
    """Returns (success: bool, message: str)."""
    current_password = request.POST.get('current_password')
    new_password = request.POST.get('new_password')
    confirm_password = request.POST.get('confirm_password')

    if not request.user.check_password(current_password):
        return False, "Current password is incorrect."

    if new_password != confirm_password:
        return False, "New password and confirmation do not match."

    if len(new_password) < 8:
        return False, "Password must be at least 8 characters."

    request.user.set_password(new_password)
    request.user.save()
    update_session_auth_hash(request, request.user)  # keeps user logged in after password change
    return True, "Password updated successfully."


# --- LOG OUT ALL DEVICES ---

def logout_all_devices(request):
    """
    Deletes every DB-backed session tied to this user, then logs out
    the current session too. Returns nothing; caller handles redirect.
    """
    for session in Session.objects.all():
        data = session.get_decoded()
        if str(data.get('_auth_user_id')) == str(request.user.id):
            session.delete()
    logout(request)


# --- FORGOT PASSWORD FLOW ---

def create_reset_request(email):
    """
    Creates (or reuses) a pending request for the given email.
    Returns (success: bool, message: str).
    """
    user = User.objects.filter(email__iexact=email).first()
    if not user:
        # Don't reveal whether the email exists — generic message either way.
        return True, "If that email is on file, your request has been submitted for review."

    existing_pending = tbl_password_reset_request.objects.filter(user=user, status='pending').first()
    if existing_pending:
        return True, "A request for this account is already pending review."

    tbl_password_reset_request.objects.create(user=user, status='pending')
    return True, "Your password reset request has been submitted for review."


def get_pending_requests():
    return tbl_password_reset_request.objects.filter(status='pending').select_related('user')


def get_recent_decided_requests(limit=20):
    return tbl_password_reset_request.objects.exclude(status='pending').select_related('user', 'decided_by')[:limit]


def approve_request(request_id, admin_user, request):
    """Approves a pending request, generates a token, builds the reset link, attempts email."""
    req_obj = tbl_password_reset_request.objects.filter(pk=request_id, status='pending').first()
    if not req_obj:
        return False, "Request not found or already handled."

    req_obj.status = 'approved'
    req_obj.generate_token()
    req_obj.decided_by = admin_user
    req_obj.decided_at = timezone.now()
    req_obj.save()

    reset_path = reverse('reset_password', args=[req_obj.token])
    reset_link = request.build_absolute_uri(reset_path)
    # --- Signature definition ---
    signature = (
        "\n\n-- \n"
        "I.T Support\n"
        "Masterbatch Philippines, Incorporated\n"
        "Email: mbpi.itsupport@gmail.com"
    )
    email_sent = False
    if req_obj.user.email:
        try:
            # Combining message + signature
            email_body = (
                f"Your password reset has been approved. "
                f"Use this link to set a new password:\n\n{reset_link}\n\n"
                f"This link can only be used once.{signature}"
            )
            sent_count = send_mail(
                subject="Password Reset Approved",
                message=email_body,
                from_email=None,  # uses DEFAULT_FROM_EMAIL
                recipient_list=[req_obj.user.email],
                fail_silently=False,
            )
            print(sent_count)
            email_sent = sent_count > 0
        except Exception as e:
            print("EMAIL SEND FAILED:", e)
            email_sent = False

    if email_sent:
        return True, f"Approved. An email was sent to {req_obj.user.email}."
    return True, f"Approved. Share this link with the user manually: {reset_link}"


def reject_request(request_id, admin_user):
    req_obj = tbl_password_reset_request.objects.filter(pk=request_id, status='pending').first()
    if not req_obj:
        return False, "Request not found or already handled."

    req_obj.status = 'rejected'
    req_obj.decided_by = admin_user
    req_obj.decided_at = timezone.now()
    req_obj.save()
    return True, f"Request from {req_obj.user.username} was rejected."


def get_valid_reset_request(token):
    req_obj = tbl_password_reset_request.objects.filter(token=token).first()
    if req_obj and req_obj.is_valid_for_reset():
        return req_obj
    return None


def complete_reset(req_obj, new_password, confirm_password):
    """Returns (success: bool, message: str)."""
    if new_password != confirm_password:
        return False, "Passwords do not match."

    if len(new_password) < 8:
        return False, "Password must be at least 8 characters."

    user = req_obj.user
    user.set_password(new_password)
    user.save()
    req_obj.status = 'completed'
    req_obj.save()
    return True, "Your password has been reset. You can now log in."

def logout_all_devices(request):
    messages.info(request, "You have been logged out of all devices.")
    return redirect('signin')


def forgot_password(request):
    if request.method == "POST":
        email = request.POST.get('email', '').strip()
        if not email:
            messages.error(request, "Please enter your email address.")
            return redirect('forgot_password')

        success, message = create_reset_request(email)
        if success:
            messages.success(request, message)
        else:
            messages.error(request, message)
        return redirect('forgot_password')

    return render(request, "settings/account/forgot_password.html")


def reset_password(request, token):
    req_obj = get_valid_reset_request(token)

    if not req_obj:
        messages.error(request, "This reset link is invalid or has already been used.")
        return redirect('signin')

    if request.method == "POST":
        new_password = request.POST.get('new_password', '')
        confirm_password = request.POST.get('confirm_password', '')

        success, message = complete_reset(req_obj, new_password, confirm_password)
        if success:
            messages.success(request, message)
            return redirect('signin')
        else:
            messages.error(request, message)
            return redirect('reset_password', token=token)

    return render(request, "settings/account/reset_password.html", {'token': token})