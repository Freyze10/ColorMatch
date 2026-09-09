from django.db.models import Q
from django.http import JsonResponse
from django.utils import timezone
from main.models import tbl_audit_trail

def get_audit_trail_data(request):
    draw = int(request.GET.get('draw', 1))
    start = int(request.GET.get('start', 0))
    length = int(request.GET.get('length', 100))
    search_value = request.GET.get('search[value]', '').strip()
    
    # Custom Filters from UI
    dept_filter = request.GET.get('department', 'all')
    col_choice = request.GET.get('column_choice', 'all') # New: From filterCol dropdown
    date_from = request.GET.get('date_from', '').strip()
    date_to = request.GET.get('date_to', '').strip()

    # 1. Base Queryset
    queryset = tbl_audit_trail.objects.select_related('user', 'user__role').all()

    # 2. Apply Department Filter
    if dept_filter != 'all':
        queryset = queryset.filter(user__role__department=dept_filter)

    # 3. Apply Date Range
    if date_from:
        queryset = queryset.filter(timestamp__date__gte=date_from)
    if date_to:
        queryset = queryset.filter(timestamp__date__lte=date_to)

    # 4. Refined Search (Global vs Column Specific)
    if search_value:
        if col_choice == 'Username':
            queryset = queryset.filter(user__username__icontains=search_value)
        elif col_choice == 'Full Name':
            queryset = queryset.filter(Q(user__first_name__icontains=search_value) | Q(user__last_name__icontains=search_value))
        elif col_choice == 'Action':
            queryset = queryset.filter(action_type__icontains=search_value)
        elif col_choice == 'Email':
            queryset = queryset.filter(user__email__icontains=search_value)
        else:
            # "All Columns" Search
            queryset = queryset.filter(
                Q(user__username__icontains=search_value) |
                Q(user__first_name__icontains=search_value) |
                Q(user__last_name__icontains=search_value) |
                Q(action_type__icontains=search_value) |
                Q(details__icontains=search_value) |
                Q(user__email__icontains=search_value)
            )

    # 5. Metadata for DataTables
    total_records = tbl_audit_trail.objects.count()
    filtered_records = queryset.count()

    # 6. Pagination & Final List
    queryset = queryset.order_by('-timestamp')[start:start + length]

    data = []
    for log in queryset:
        fname = log.user.first_name if log.user else ""
        lname = log.user.last_name if log.user else ""
        full_name = f"{lname}, {fname}" if lname else "---"
        # timezone.localtime() handles the conversion using your TIME_ZONE setting
        local_ts = timezone.localtime(log.timestamp)

        data.append({
            "timestamp": local_ts.strftime('%m/%d/%Y %I:%M %p'),
            "username": log.user.username if log.user else "System",
            "full_name": full_name,
            "action_type": log.action_type,
            "details": log.details,
            "email": log.user.email if log.user else "---",
            "department": log.user.role.department if log.user and log.user.role else "---",
        })

    return JsonResponse({
        "draw": draw,
        "recordsTotal": total_records,
        "recordsFiltered": filtered_records,
        "data": data,
    })