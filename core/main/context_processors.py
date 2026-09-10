def sidebar_permissions(request):
    if not request.user.is_authenticated or not getattr(request.user, 'role', None):
        return {'user_permissions': set()}

    enabled = set(
        request.user.role.tbl_role_permissions_set
        .filter(is_enabled=True)
        .values_list('access__access_name', flat=True)
    )
    return {'user_permissions': enabled}