"""
operaciones/views.py
Endpoints de sincronización Offline-First (Bidireccional). 

1. SyncTareasView (Push): Recibe una ráfaga (lista JSON) de Tareas con 
   RegistroDowntime anidado desde la app móvil del técnico, y la procesa a 
   través de TareaSerializer (resolución Last-Write-Wins).

2. SincronizacionDescendenteView (Pull): Emite el estado global autoritativo 
   desde PostgreSQL hacia el cliente móvil para la fase de reconciliación local.

Requiere que TareaSerializer y Tarea (model) estén disponibles.
"""
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.parsers import JSONParser
from rest_framework.permissions import IsAuthenticated

from .models import Tarea
from .serializers import TareaSerializer


class SyncTareasView(APIView):
    permission_classes = [IsAuthenticated] # <-- Candado criptográfico inyectado
    """
    POST /api/sync/tareas/

    Payload esperado: una LISTA JSON de objetos Tarea (incluso si se
    sincroniza una sola tarea, debe ir dentro de un array). Cada Tarea puede
    traer 'tiempos_muertos' anidados. Ejemplo de un elemento del array:

        {
          "id": "5c1f6e2a-....-....-....-............",
          "titulo": "Perforación frente 4A",
          "estado": "EN_PROGRESO",
          "porcentaje_avance": 40,
          "fecha_limite_proyectada": "2026-09-01T00:00:00+00:00",
          "creado_en_dispositivo": "2026-08-21T14:32:10+00:00",
          "tiempos_muertos": [
            {
              "id": "9a2e7c11-....-....-....-............",
              "causa_raiz": "FALLA_MECANICA",
              "detalle_tecnico": "Compresora fuera de servicio",
              "duracion_horas_estimada": "1.50",
              "creado_en_dispositivo": "2026-08-21T14:35:00+00:00"
            }
          ]
        }

    Respuestas:
      200 OK          -> ráfaga válida en formato; el upsert se aplicó. Ojo:
                         que un registro individual haya sido "descartado"
                         por Last-Write-Wins (porque el servidor ya tenía una
                         versión más reciente) NO es un error HTTP — es
                         comportamiento normal del protocolo de sync. El
                         200 confirma que el batch fue procesado, no que
                         todos los registros cambiaron.
      400 Bad Request -> la ráfaga no es una lista, o algún elemento no pasó
                         validación de campo / reglas de negocio del
                         serializer (choices inválidos, porcentaje_avance
                         fuera de rango, falta creado_en_dispositivo, etc.).
    """
    parser_classes = [JSONParser]

    def post(self, request, *args, **kwargs):
        if not isinstance(request.data, list):
            return Response(
                {
                    'detail': (
                        'El payload debe ser una lista JSON de Tareas, '
                        'incluso para sincronizar una sola.'
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = TareaSerializer(data=request.data, many=True)

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        tareas_procesadas = serializer.save()

        return Response(
            TareaSerializer(tareas_procesadas, many=True).data,
            status=status.HTTP_200_OK,
        )


class SincronizacionDescendenteView(APIView):
    """
    GET /api/sync/tareas/descarga/

    Endpoint de Lectura (Pull): Retorna el estado global de las tareas
    autoritativas. Se ejecuta desde el cliente móvil inmediatamente después
    de un Push exitoso para garantizar consistencia eventual bidireccional.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        # Extracción global de registros.
        # Iteraciones futuras requerirán segmentación por 'cuadrilla_id'
        # o 'asignado_a' para limitar el ancho de banda y mitigar carga en redes lentas.
        tareas = Tarea.objects.all()
        serializer = TareaSerializer(tareas, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)