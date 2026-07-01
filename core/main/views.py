from urllib import request

from django.shortcuts import render
from django.http import HttpResponse
# Create your views here.

def index(request):
    return render(request, "base.html")

def dashboard(request):
    return render(request, "dashboard/dashboard.html")

def otherPage(request):
    return render(request, "other.html")

def cmf_records(request):
    records = [
        {
            "cmf_no": "CMF-24-001",
            "customer": "Masterbatch PH",
            "primary_color": "Red",
            "description": "Gloss",
            "product": "Cap",
            "required_date": "10/25/24",
            "target_date": "10/30/24",
            "type": "New",
            "code": "PC-001",
            "status": "Completed"
        },
        {
            "cmf_no": "CMF-24-002",
            "customer": "Generic Co.",
            "primary_color": "Blue",
            "description": "Matte",
            "product": "Tray",
            "required_date": "11/01/24",
            "target_date": "11/05/24",
            "type": "Re-Match",
            "code": "PC-002",
            "status": "Pending"
        },
    ]
    return render(request, "cmf/cmf_records.html",  {'records': records})

def cmf_entry(request):
    return render(request, "cmf/cmf_entry.html")

def cmf_rs_entry(request):
    return render(request, "cmf/rs_entry.html")

def cmf_mb_formula(request):
    return render(request, "cmf/formula_mb.html")

def cmf_dc_formula(request):
    return render(request, "cmf/formula_dc.html")

def cmf_pending_completed(request):
    return render(request, "cmf/pending_completed.html")