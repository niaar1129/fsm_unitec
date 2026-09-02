import uuid
from decimal import Decimal
from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User

# ==============================================================================
# CLASES BASE Y AUDITORÍA
# ==============================================================================

class ModeloBaseAuditoria(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    creado_en_dispositivo = models.DateTimeField(default=timezone.now)
    sincronizado_en_nube = models.DateTimeField(auto_now_add=True)

    class Meta:
        abstract = True

class SoftDeleteQuerySet(models.QuerySet):
    def delete(self):
        return super().update(esta_activo=False, eliminado_en=timezone.now())

    def hard_delete(self):
        return super().delete()

class SoftDeleteManager(models.Manager):
    def get_queryset(self):
        return SoftDeleteQuerySet(self.model, using=self._db).filter(esta_activo=True)

class ModeloBaseAuditoriaSoftDelete(ModeloBaseAuditoria):
    esta_activo = models.BooleanField(default=True)
    eliminado_en = models.DateTimeField(null=True, blank=True)

    objects = SoftDeleteManager()
    todos_los_objetos = models.Manager()

    class Meta:
        abstract = True

    def delete(self, *args, **kwargs):
        self.esta_activo = False
        self.eliminado_en = timezone.now()
        self.save(update_fields=['esta_activo', 'eliminado_en'])

    def hard_delete(self, *args, **kwargs):
        super().delete(*args, **kwargs)


# ==============================================================================
# OPERACIONES Y PRODUCTIVIDAD (AVANCE FÍSICO)
# ==============================================================================

class EstadoTarea(models.TextChoices):
    PENDIENTE = 'PENDIENTE', 'Pendiente de Ejecución'
    EN_PROGRESO = 'EN_PROGRESO', 'En Progreso'
    DETENIDA = 'DETENIDA', 'Detenida por Bloqueo'
    FINALIZADA = 'FINALIZADA', 'Finalizada al 100%'

class TipoDowntime(models.TextChoices):
    FALLA_MECANICA = 'FALLA_MECANICA', 'Falla Mecánica (Ej. Compresora)'
    FALTA_MATERIAL = 'FALTA_MATERIAL', 'Falta de Material (Ej. Cemento/Agua)'
    CLIMA_ADVERSO = 'CLIMA_ADVERSO', 'Condición Climática (Ej. Tormenta Eléctrica)'
    CORTE_ENERGIA = 'CORTE_ENERGIA', 'Corte de Energía Programado/Imprevisto'
    OTROS = 'OTROS', 'Otros (Requiere justificación)'

class Tarea(ModeloBaseAuditoria):
    # <-- INYECCIÓN DE LLAVE FORÁNEA (Data Partitioning) -->
    asignado_a = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='tareas_asignadas',
        help_text="Técnico responsable de esta orden en mina."
    )

    titulo = models.CharField(max_length=200)
    descripcion = models.TextField(blank=True)
    estado = models.CharField(max_length=20, choices=EstadoTarea.choices, default=EstadoTarea.PENDIENTE)
    porcentaje_avance = models.PositiveSmallIntegerField(default=0)
    fecha_limite_proyectada = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"[{self.estado}] {self.titulo} - {self.porcentaje_avance}%"

class RegistroDowntime(ModeloBaseAuditoria):
    tarea = models.ForeignKey(Tarea, related_name='tiempos_muertos', on_delete=models.CASCADE)
    causa_raiz = models.CharField(max_length=20, choices=TipoDowntime.choices)
    detalle_tecnico = models.TextField()
    duracion_horas_estimada = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)

    def __str__(self):
        return f"BLOQUEO: {self.causa_raiz} en {self.tarea.titulo}"


# ==============================================================================
# LOGÍSTICA Y RECURSOS HUMANOS
# ==============================================================================

class TurnoGuardia(models.TextChoices):
    DIA = 'DIA', 'Guardia Día'
    NOCHE = 'NOCHE', 'Guardia Noche'

class Operador(ModeloBaseAuditoriaSoftDelete):
    nombres = models.CharField(max_length=150)
    apellidos = models.CharField(max_length=150)
    dni = models.CharField(max_length=8, unique=True)
    cargo = models.CharField(max_length=100)
    turno_actual = models.CharField(max_length=10, choices=TurnoGuardia.choices, default=TurnoGuardia.DIA)
    foto_perfil_uri = models.CharField(max_length=500, blank=True, null=True)
    fecha_ingreso_mina = models.DateField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=['dni'])]

    def __str__(self):
        return f'{self.apellidos}, {self.nombres} ({self.dni})'

class CategoriaEPP(models.TextChoices):
    CASCO = 'CASCO', 'Casco de Seguridad'
    LAMPARA = 'LAMPARA', 'Lámpara Minera'
    CARGADOR = 'CARGADOR', 'Cargador de Lámpara'
    AUTORRESCATADOR = 'AUTORRESCATADOR', 'Autorescatador'
    BOTAS = 'BOTAS', 'Botas de Seguridad'
    ARNES = 'ARNES', 'Arnés de Seguridad'
    OTROS = 'OTROS', 'Otro EPP'

class ItemEPP(ModeloBaseAuditoriaSoftDelete):
    categoria = models.CharField(max_length=20, choices=CategoriaEPP.choices)
    codigo_inventario = models.CharField(max_length=50, unique=True)
    descripcion = models.CharField(max_length=200)
    valor_reposicion = models.DecimalField(max_digits=8, decimal_places=2)
    vida_util_meses = models.PositiveSmallIntegerField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=['categoria', 'codigo_inventario'])]

    def __str__(self):
        return f'[{self.codigo_inventario}] {self.descripcion}'

class EstadoAsignacionEPP(models.TextChoices):
    ENTREGADO = 'ENTREGADO', 'Entregado - en posesión del operador'
    DEVUELTO_OK = 'DEVUELTO_OK', 'Devuelto en buen estado'
    DEVUELTO_DANADO = 'DEVUELTO_DANADO', 'Devuelto con daño (penalización parcial)'
    PERDIDO = 'PERDIDO', 'Perdido / no devuelto (penalización total)'
    EN_REPARACION = 'EN_REPARACION', 'En reparación'

class AsignacionEPP(ModeloBaseAuditoriaSoftDelete):
    operador = models.ForeignKey(Operador, related_name='asignaciones_epp', on_delete=models.PROTECT)
    item = models.ForeignKey(ItemEPP, related_name='asignaciones', on_delete=models.PROTECT)
    estado = models.CharField(max_length=20, choices=EstadoAsignacionEPP.choices, default=EstadoAsignacionEPP.ENTREGADO)
    
    fecha_entrega = models.DateTimeField(default=timezone.now)
    fecha_devolucion_esperada = models.DateTimeField(null=True, blank=True)
    fecha_devolucion_real = models.DateTimeField(null=True, blank=True)
    
    evidencia_entrega_uri = models.CharField(max_length=500, blank=True, null=True)
    evidencia_devolucion_uri = models.CharField(max_length=500, blank=True, null=True)
    
    monto_penalizacion_aplicado = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal('0.00'))
    observaciones = models.TextField(blank=True)
    valor_reposicion_congelado = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['operador', 'estado']),
            models.Index(fields=['item', 'estado']),
        ]

    def __str__(self):
        return f'{self.item.codigo_inventario} -> {self.operador.dni} [{self.estado}]'

    def calcular_penalizacion(self, porcentaje_dano: Decimal = Decimal('0.50'), forzar_recalculo: bool = False) -> Decimal:
        if self.estado not in (EstadoAsignacionEPP.PERDIDO, EstadoAsignacionEPP.DEVUELTO_DANADO):
            self.monto_penalizacion_aplicado = Decimal('0.00')
            self.valor_reposicion_congelado = None
            return self.monto_penalizacion_aplicado

        if self.valor_reposicion_congelado is None or forzar_recalculo:
            self.valor_reposicion_congelado = self.item.valor_reposicion

        base = self.valor_reposicion_congelado

        if self.estado == EstadoAsignacionEPP.PERDIDO:
            self.monto_penalizacion_aplicado = base
        else:
            self.monto_penalizacion_aplicado = (base * porcentaje_dano).quantize(Decimal('0.01'))
        return self.monto_penalizacion_aplicado