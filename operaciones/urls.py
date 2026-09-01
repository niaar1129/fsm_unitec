"""
operaciones/urls.py
Definición topológica del perímetro de red para el módulo de operaciones.
El prefijo 'api/sync/' es inyectado dinámicamente por el multiplexor raíz (core/urls.py).
"""
from django.urls import path

from .views import SyncTareasView, SincronizacionDescendenteView

app_name = 'operaciones'

urlpatterns = [
    # POST https://unitec-fsm-api.onrender.com/api/sync/tareas/
    # Fase 1: Replicación Ascendente (Push) - Recepción de ráfagas desde el cliente SQLite
    path('tareas/', SyncTareasView.as_view(), name='sync-tareas'),
    
    # GET https://unitec-fsm-api.onrender.com/api/sync/tareas/descarga/
    # Fase 2: Replicación Descendente (Pull) - Emisión del estado global hacia el cliente React Native
    path('tareas/descarga/', SincronizacionDescendenteView.as_view(), name='sync_pull'),
]