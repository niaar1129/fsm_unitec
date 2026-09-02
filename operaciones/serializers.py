from django.db import transaction
from rest_framework import serializers

# 1. IMPORTACIÓN ESTRICTA DE LA BASE DE DATOS
from .models import Tarea, RegistroDowntime

def _upsert_last_write_wins(model_cls, record_id, defaults):
    """Upsert idempotente con resolución Last-Write-Wins"""
    incoming_ts = defaults.get('creado_en_dispositivo')

    try:
        existente = model_cls.objects.get(id=record_id)
    except model_cls.DoesNotExist:
        nuevo = model_cls.objects.create(id=record_id, **defaults)
        return nuevo, True

    if incoming_ts is not None and existente.creado_en_dispositivo > incoming_ts:
        return existente, False

    for attr, value in defaults.items():
        setattr(existente, attr, value)
    existente.save()
    return existente, True


class RegistroDowntimeSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField() 
    creado_en_dispositivo = serializers.DateTimeField(required=True)

    class Meta:
        model = RegistroDowntime  # <-- CORRECCIÓN: Conectado a la tabla real
        fields = [
            'id',
            'causa_raiz',
            'detalle_tecnico',
            'duracion_horas_estimada',
            'creado_en_dispositivo',
            'sincronizado_en_nube',
        ]
        read_only_fields = ['sincronizado_en_nube']

    def validate_duracion_horas_estimada(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError('La duración estimada no puede ser negativa.')
        return value


class TareaSyncListSerializer(serializers.ListSerializer):
    @transaction.atomic
    def create(self, validated_data):
        return [self.child.create(item) for item in validated_data]


class TareaSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField()
    creado_en_dispositivo = serializers.DateTimeField(required=True)
    tiempos_muertos = RegistroDowntimeSerializer(many=True, required=False)
    # Exponemos el campo de solo lectura para auditoría
    asignado_a = serializers.StringRelatedField(read_only=True)

    class Meta:
        model = Tarea  # <-- CORRECCIÓN: Conectado a la tabla real
        list_serializer_class = TareaSyncListSerializer
        fields = [
            'id',
            'titulo',
            'descripcion',
            'estado',
            'porcentaje_avance',
            'fecha_limite_proyectada',
            'creado_en_dispositivo',
            'sincronizado_en_nube',
            'tiempos_muertos',
            'asignado_a', # <-- Campo inyectado en la API
        ]
        read_only_fields = ['sincronizado_en_nube', 'asignado_a']

    def validate_porcentaje_avance(self, value):
        if not (0 <= value <= 100):
            raise serializers.ValidationError('El avance debe estar entre 0 y 100.')
        return value

    def validate(self, attrs):
        estado = attrs.get('estado')
        avance = attrs.get('porcentaje_avance')
        if estado == 'FINALIZADA' and avance is not None and avance < 100:
            raise serializers.ValidationError('Una tarea FINALIZADA debe tener porcentaje = 100.')
        if estado == 'PENDIENTE' and avance:
            raise serializers.ValidationError('Una tarea PENDIENTE no debería registrar avance > 0.')
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        tiempos_data = validated_data.pop('tiempos_muertos', [])
        tarea_id = validated_data.pop('id')

        # Interceptamos el usuario del contexto de la petición HTTP (JWT)
        user = self.context['request'].user
        validated_data['asignado_a'] = user

        tarea, _aplicado = _upsert_last_write_wins(Tarea, tarea_id, validated_data)

        for downtime_data in tiempos_data:
            downtime_id = downtime_data.pop('id')
            downtime_data['tarea'] = tarea
            _upsert_last_write_wins(RegistroDowntime, downtime_id, downtime_data)

        return tarea

    @transaction.atomic
    def update(self, instance, validated_data):
        tiempos_data = validated_data.pop('tiempos_muertos', [])
        validated_data.pop('id', None)
        incoming_ts = validated_data.get('creado_en_dispositivo')

        # Si la tarea se está actualizando (Upsert), forzamos que quede asignada 
        # al técnico que está enviando la actualización, previniendo robo de autoría.
        user = self.context['request'].user
        validated_data['asignado_a'] = user

        if incoming_ts is not None and instance.creado_en_dispositivo > incoming_ts:
            pass 
        else:
            for attr, value in validated_data.items():
                setattr(instance, attr, value)
            instance.save()

        for downtime_data in tiempos_data:
            downtime_id = downtime_data.pop('id')
            downtime_data['tarea'] = instance
            _upsert_last_write_wins(RegistroDowntime, downtime_id, downtime_data)

        return instance