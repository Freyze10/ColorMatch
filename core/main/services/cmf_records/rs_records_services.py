from django.http import JsonResponse
from django.shortcuts import render
from django.db.models import Q, Value, OuterRef, Subquery
from django.db.models.functions import Concat
from main.models import tbl_rs, tbl_cmf_pending_completed

# Column index order matching DataTables
RS_ORDER_COLUMNS = [
    'id',           # 0 - hidden
    'rs_no',        # 1 - RS No.
    'customer',     # 2 - Customer
    'cm_no__cm_no', # 3 - CMF No.
    'product_code', # 4 - Product Code (subquery)
    'sm_no__name',  # 5 - Salesman
    'approved_by',  # 6 - Approved by
    'is_completed', # 7 - Status (subquery)
]

RS_SEARCH_FIELDS = {
    '0': ['rs_no'],
    '1': ['customer'],
    '2': ['cm_no__cm_no'],
    '3': ['product_code'],
    '4': ['sm_no__name'],
    '5': ['approved_by__first_name', 'approved_by__last_name', 'approved_by__username'],
}
ALL_RS_SEARCH_FIELDS = sorted({f for fields in RS_SEARCH_FIELDS.values() for f in fields})


def rs_records_data(request):
    """DataTables AJAX JSON endpoint."""
    draw = int(request.GET.get('draw', 1))
    start = int(request.GET.get('start', 0))
    length = int(request.GET.get('length', 1000))
    order_col = int(request.GET.get('order[0][column]', 1))
    order_dir = request.GET.get('order[0][dir]', 'desc')

    search_col = request.GET.get('search_col', 'all')
    search_term = (request.GET.get('search_term') or '').strip()

    # Subqueries from tbl_cmf_pending_completed for status and product code
    pending_sub = tbl_cmf_pending_completed.objects.filter(rs_no=OuterRef('pk'))

    qs = tbl_rs.objects.select_related('cm_no', 'sm_no', 'approved_by').annotate(
        product_code=Subquery(pending_sub.values('code__product_code')[:1]),
        is_completed=Subquery(pending_sub.values('is_completed')[:1]),
        approver_name=Concat('approved_by__first_name', Value(' '), 'approved_by__last_name')
    )

    total_count = qs.count()

    # Search filter
    if search_term:
        fields = ALL_RS_SEARCH_FIELDS if search_col == 'all' else RS_SEARCH_FIELDS.get(search_col, [])
        if fields:
            q = Q()
            for f in fields:
                q |= Q(**{f"{f}__icontains": search_term})
            qs = qs.filter(q)

    filtered_count = qs.count()

    # Ordering
    if 0 <= order_col < len(RS_ORDER_COLUMNS):
        order_field = RS_ORDER_COLUMNS[order_col]
    else:
        order_field = 'rs_no'
    if order_dir == 'desc':
        order_field = f"-{order_field}"
    qs = qs.order_by(order_field)

    page_qs = qs[start:start + length]

    data = []
    for rs in page_qs:
        data.append({
            "id": rs.id,
            "rs_no": rs.rs_no or "---",
            "customer": rs.customer or "---",
            "cm_no": rs.cm_no.cm_no if rs.cm_no else "---",
            "product_code": rs.product_code or "---",
            "salesman": rs.sm_no.name if rs.sm_no else "---",
            "approved_by": rs.approver_name.strip() if rs.approver_name and rs.approver_name.strip() else (rs.approved_by.username if rs.approved_by else "---"),
            "status": "Completed" if rs.is_completed else "Pending"
        })

    return JsonResponse({
        "draw": draw,
        "recordsTotal": total_count,
        "recordsFiltered": filtered_count,
        "data": data
    })