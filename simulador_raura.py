"""
simulador_raura.py
Simulador de red intermitente de Mina Raura para probar el motor
Offline-First del backend Django/DRF.

Este script NO es parte del proyecto Django. Actúa como si fuera el celular
del técnico en campo: genera UUIDs del lado del cliente (tal como exige la
arquitectura), arma una ráfaga JSON con dos Tareas (una con un
RegistroDowntime anidado por falla mecánica) y la envía por POST al
endpoint de sincronización.

Requisitos:
    pip install requests

Uso:
    python simulador_raura.py
"""
import json
import uuid
import datetime

import requests

URL_SYNC = 'http://127.0.0.1:8000/api/sync/tareas/'


def timestamp_iso_ahora(offset_minutos: int = 0) -> str:
    """
    Genera un timestamp ISO 8601 en UTC. El offset en minutos permite
    simular eventos que ocurrieron un poco antes o después entre sí dentro
    del mismo batch (útil para probar más adelante el orden de llegada y
    la resolución Last-Write-Wins con timestamps deliberadamente
    desordenados).
    """
    momento = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(
        minutes=offset_minutos
    )
    return momento.isoformat()


def construir_payload_raura() -> list:
    """
    Arma la ráfaga de sincronización:
      - Tarea A: EN_PROGRESO, sin downtime.
      - Tarea B: DETENIDA, con un RegistroDowntime anidado (falla mecánica
        de compresora), simulando la interrupción real en socavón.
    Los tres UUID (2 tareas + 1 downtime) se generan aquí, del lado
    cliente, nunca en el servidor.
    """
    tarea_a_id = str(uuid.uuid4())
    tarea_b_id = str(uuid.uuid4())
    downtime_id = str(uuid.uuid4())

    payload = [
        {
            'id': tarea_a_id,
            'titulo': 'Perforación frente 4A - Nivel 320',
            'descripcion': 'Avance de perforación según malla de disparo.',
            'estado': 'EN_PROGRESO',
            'porcentaje_avance': 45,
            'fecha_limite_proyectada': timestamp_iso_ahora(offset_minutos=60 * 24 * 3),
            'creado_en_dispositivo': timestamp_iso_ahora(),
            'tiempos_muertos': [],
        },
        {
            'id': tarea_b_id,
            'titulo': 'Acarreo de mineral - Rampa 12',
            'descripcion': 'Transporte de mineral roto hacia superficie.',
            'estado': 'DETENIDA',
            'porcentaje_avance': 20,
            'fecha_limite_proyectada': timestamp_iso_ahora(offset_minutos=60 * 24 * 2),
            'creado_en_dispositivo': timestamp_iso_ahora(),
            'tiempos_muertos': [
                {
                    'id': downtime_id,
                    'causa_raiz': 'FALLA_MECANICA',
                    'detalle_tecnico': (
                        'Compresora principal fuera de servicio, presión '
                        'insuficiente para continuar el ciclo de acarreo.'
                    ),
                    'duracion_horas_estimada': '1.50',
                    'creado_en_dispositivo': timestamp_iso_ahora(offset_minutos=5),
                }
            ],
        },
    ]
    return payload


def enviar_rafaga(payload: list) -> None:
    print(f'Enviando ráfaga de {len(payload)} tarea(s) a {URL_SYNC}\n')
    print('--- Payload enviado ---')
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    print('\n--- Respuesta del servidor ---')

    try:
        respuesta = requests.post(URL_SYNC, json=payload, timeout=10)
    except requests.exceptions.ConnectionError:
        print(
            f'ERROR: no se pudo conectar a {URL_SYNC}. '
            '¿Está corriendo `python manage.py runserver`?'
        )
        return
    except requests.exceptions.Timeout:
        print('ERROR: timeout esperando respuesta del servidor '
              '(simula corte de señal en la mina).')
        return

    print(f'Status HTTP: {respuesta.status_code}')
    try:
        print(json.dumps(respuesta.json(), indent=2, ensure_ascii=False))
    except ValueError:
        print('El servidor no devolvió JSON válido. Respuesta cruda:')
        print(respuesta.text)


if __name__ == '__main__':
    payload_generado = construir_payload_raura()
    enviar_rafaga(payload_generado)