from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('other/', views.otherPage, name='other'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('cmf/records/', views.cmf_records, name='cmf_records'),
    path('cmf/entry/', views.cmf_entry, name='cmf_entry'),
]