from django.shortcuts import render
from django.http import HttpResponse
# Create your views here.

def index(request):
    return HttpResponse("<h1>Hello, World!</h1>")

def v1(request):
    return HttpResponse("<h1>View 1!</h1>")