from ...models import (
    tbl_cmf_dates, 
    tbl_cmf_pending_completed, 
)
from django.core.cache import cache


def get_rs_records():
    cached_data = cache.get('rs_records_list')
    if cached_data is not None:
        return cached_data

    # Added 'code' to select_related
    status_records = tbl_cmf_pending_completed.objects.filter(
        rs_no__isnull=False
    ).select_related('rs_no', 'code').order_by('-rs_no')
    
    results = []
    for entry in status_records:
        rs = entry.rs_no
        dates = tbl_cmf_dates.objects.filter(rs_no=rs).first()

        results.append({
            "id": rs.id,
            "no": rs.rs_no,
            "customer": rs.customer or "---",
            "primary_color": rs.primary_color or "---",
            "description": rs.color_desc or "---",
            "product": rs.finished_product or "---",
            "required_date": dates.date_required if dates else "---",
            "target_date": dates.due_date_lab.strftime('%m/%d/%y') if (dates and dates.due_date_lab) else "---",
            "type": rs.matching_type or "---",
            "colorant_type": rs.colorant_type or "---",
            # Updated: Access string via the new 'code' ForeignKey
            "code": entry.code.product_code if entry.code else "---",
            "status": "Completed" if entry.is_completed else "Pending",
            "submitted_date": entry.date_submitted.strftime('%m/%d/%y') if entry.date_submitted else "",
            "ar_no": entry.ar_no or "",
            "reason": entry.reason or "",
            "mode": "rs"
        })

    cache.set('rs_records_list', results, 3600)
    return results