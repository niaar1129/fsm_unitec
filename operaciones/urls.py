"""
operaciones/urls.py
"""
from django.urls import path

from .views import SyncTareasView

app_name = 'operaciones'

urlpatterns = [
    # POST http://127.0.0.1:8000/api/sync/tareas/
    path('tareas/', SyncTareasView.as_view(), name='sync-tareas'),
]