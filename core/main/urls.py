from django.urls import path

from .services.settings import settings_services

from .services.export import export_audit_trail, export_feedback, export_formulation, export_master_formula
from .services.save import cmf_entry_save

from .services.print import print_cmf, print_mb_formula, print_dc_formula
from .services.audit import audit_services
from .services.formula import master_formula_services, formulation_services

from . import views
from .services.cmf_records import cmf_records_services, previous_cmf_record, formula_price_first, mb_dc_formulation_services
from .services.export import cmf_record_export

urlpatterns = [
    path('', views.index, name='index'),
    path('pending-role/', views.pending_role, name='pending_role'),
    path('login/signin/', views.signin, name='signin'),
    path('login/signup/', views.signup, name='signup'),
    path('login/signout/', views.signout, name='signout'),
    path('homepage/', views.homepage, name='homepage'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('cmf/records/', views.cmf_records, name='cmf_records'),
    path('cmf/formula-records/', views.formula_records, name='formula_records'),
    path('cmf/entry/', views.cmf_entry, name='cmf_entry'),
    path('cmf/rs-entry/', views.cmf_rs_entry, name='rs_entry'),
    path('cmf/mb-formula/', views.cmf_mb_formula, name='mb_formula'),
    path('cmf/dc-formula/', views.cmf_dc_formula, name='dc_formula'),
    path('cmf/pending-completed/', views.cmf_pending_completed, name='pending_completed'),
    path('master-formula/', views.master_formula, name='master_formula'),
    path('formulation/', views.formulation, name='formulation'),
    path('feedback/', views.feedback, name='feedback'),
    path('audit-trail/', views.audit_trail, name='audit_trail'),
    path('legacy/sync/', views.trigger_legacy_sync, name='trigger_legacy_sync'),
    path('maintenance/', views.maintenance, name='maintenance'),
    path('settings/', views.settings, name='settings'),
    path('settings/logout-all/', settings_services.logout_all_devices, name='logout_all_devices'),
    path('forgot-password/', settings_services.forgot_password, name='forgot_password'),
    path('settings/password-requests/', views.admin_password_requests, name='admin_password_requests'),
    path('permission-access/', views.permission_access, name='permission_access'),


    # export
    path('cmf/records/export/', views.cmf_records_export_preview, name='cmf_records_export_preview'),
    # ajax
    path('cmf/mb-dc-formula/', mb_dc_formulation_services.get_formulation_details, name='mb_dc_lookup_details'),
    path('cmf/formula-records/data/', cmf_records_services.formula_records_data, name='formula_records_data'),
    path('cmf/formula-records/price-first/', formula_price_first.get_price_first_data, name='get_price_first_data'),
    path('cmf/formula-records/price-first/download/', formula_price_first.download_price_first_excel, name='download_price_first_excel'),
    path('formula-records/export-all/', formula_price_first.export_formula_by_date, name='export_formula_all'),
    path('master-formula/lookup/', master_formula_services.master_formula_lookup, name='master_formula_lookup'),
    path('check-previous-matching/', previous_cmf_record.check_previous_matching, name='check_previous_matching'),
    path('formulation/data/', formulation_services.get_formulation_records_json, name='formulation_data'),
    path('master-formula/data/', master_formula_services.get_master_formula_records_json, name='master_formula_data'),
    path('audit-trail/data/', audit_services.get_audit_trail_data, name='audit_trail_data'),
    path('master-formula/export/', export_master_formula.export_master_formula_excel, name='export_master_formula_excel'),
    path('formulation/export/', export_formulation.export_formulation_excel, name='export_formulation_excel'),
    path('feedback/export/', export_feedback.export_feedback_excel, name='export_feedback_excel'),
    path('audit-trail/export/', export_audit_trail.export_audit_trail_excel, name='export_audit_trail_csv'),
    path('permission-access/toggle/', views.toggle_permission, name='toggle_permission'),
    
    # with parameters
    path('cmf/records/<str:cm_no>/', views.cmf_record_detail, name='cmf_record_detail'),
    path('cmf/log-export-download/',cmf_record_export.log_cmf_export_action, name='log_cmf_export_download'),
    path('cmf/attachment/<int:attachment_id>/download/', cmf_entry_save.download_cmf_attachment, name='download_cmf_attachment'),
    path('cmf/formula-records/materials/<str:formula_type>/<int:formula_id>/', cmf_records_services.get_formula_materials, name='get_formula_materials'),
    path('cmf/formula/<str:formula_type>/<int:formula_id>/toggle-final/', cmf_records_services.toggle_final_formula, name='toggle_final_formula'),
    path('cmf/rs-records/<int:rs_id>/', views.rs_record_detail, name='rs_record_detail'),
    path('cmf/print/<str:cm_no>/', print_cmf.print_cmf, name='print_cmf'), # for flexible print (uses html css for print)
    # path('cmf/print/<str:cm_no>/preview', print_cmf.print_cmf_preview, name='cmf_print_preview'),
    path('mb-formula/print/<int:formula_id>/', print_mb_formula.print_mb_formula, name='print_mb_formula'), # for flexible print (uses html css for print)
    path('dc-formula/print/<int:formula_id>/', print_dc_formula.print_dc_formula, name='print_dc_formula'),
    # path('mb-formula/print/<str:formula_id>/preview', print_mb_formula.print_mb_formula_preview, name='mb_formula_print'), used Com/ms office for editing the template
    # path('dc-formula/print/<str:formula_id>/preview', print_dc_formula.print_dc_formula_preview, name='dc_formula_print'),
    path('cmf/log-print/<str:cm_no>/', print_cmf.log_cmf_print, name='log_cmf_print'),
    path('master-formula/print/<int:form_id>/', master_formula_services.print_master_formula, name='print_master_formula'),
    path('master-formula/log-print/<int:form_id>/', master_formula_services.log_master_formula_print, name='log_master_formula_print'),
    path('master-formula/<int:form_id>/materials/', master_formula_services.master_formula_materials_json, name='master_formula_materials_json'),
    path('formulation/<int:form_id>/materials/', formulation_services.formulation_materials_json, name='formulation_materials_json'),
    path('mb-formula/log-print/<int:formula_id>/', print_mb_formula.log_formula_print, name='log_mb_formula_print'),
    path('dc-formula/log-print/<int:formula_id>/', print_dc_formula.log_formula_print, name='log_dc_formula_print'),
    path('reset-password/<str:token>/', settings_services.reset_password, name='reset_password'),
]