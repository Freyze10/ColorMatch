from django.contrib import messages
from django.shortcuts import redirect
from functools import wraps

def role_required(view_func):
    """
    Decorator for views that checks that the user is logged in and has a role assigned,
    redirecting to the pending-role page if necessary.
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        # 1. First, check if they are even logged in
        if not request.user.is_authenticated:
            return redirect('signin')
        
        # 2. Check if the user has a role (role is not None)
        if not request.user.role:
            return redirect('pending_role')
            
        # 3. If they have a role, let them proceed to the view
        return view_func(request, *args, **kwargs)
        
    return _wrapped_view

def access_required(access_name=None, allowed_roles=None, allowed_departments=None):
    """
    Checks that the user's role has an ENABLED tbl_role_permissions entry
    for the given AccessPoint (access_name), e.g. 'Master Formula', 'Formula Records',
    and/or restricts by role/department.
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('signin')
            if not request.user.role:
                return redirect('pending_role')

            user_role = request.user.role.role
            user_dept = request.user.role.department

            if allowed_roles and user_role.upper() not in [r.upper() for r in allowed_roles]:
                messages.error(request, "Access Denied: Restricted Role.")
                return redirect('homepage')

            if allowed_departments and user_dept not in allowed_departments:
                messages.error(request, "Access Denied: Restricted Department.")
                return redirect('homepage')

            if access_name:
                has_access = request.user.role.tbl_role_permissions_set.filter(
                    is_enabled=True,
                    access__access_name=access_name
                ).exists()
                if not has_access:
                    messages.error(request, "Access Denied: You don't have permission for this page.")
                    return redirect('homepage')

            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator