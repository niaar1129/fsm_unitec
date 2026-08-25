"""
admin.py
Interfaz de auditoría (Dashboard B2B) para la gerencia del cliente minero.

IMPORTANTE — léase antes de desplegar a la gerencia del cliente:
Este archivo registra ModelAdmin funcionales, pero el Django Admin por
defecto NO es "solo lectura": cualquier usuario staff con permisos de
change/delete puede editar datos de producción directamente, incluyendo
campos financieros y de auditoría. Si la gerencia del cliente minero va a
usar esta MISMA interfaz (mismo dominio /admin/), se necesita, como mínimo:
  1. Un grupo de permisos "Auditoria_Cliente" con solo view_* en los cinco
     modelos, sin add/change/delete.
  2. Evaluar si conviene un AdminSite separado (ej. /panel-cliente/) en vez
     de mezclar usuarios internos (UNITEC) y externos (cliente minero) en
     /admin/.
No implemento esa capa de permisos aquí porque implica decisiones de
negocio (¿la gerencia solo audita, o también corrige asignaciones?) que
le corresponden al Arquitecto/Producto, no a mí asumirlas.
"""
from django.contrib import admin
from django.db.models import Q
from django.utils import timezone

from .models import (
    Tarea,
    RegistroDowntime,
    Operador,
    ItemEPP,
    AsignacionEPP,
)


# ---------------------------------------------------------------------------
# Filtro custom: "En Riesgo" no es un campo de base de datos, es derivado
# (fecha_limite_proyectada vencida + avance < 100%). Para poder filtrar por
# él en list_filter (no solo mostrarlo en list_display), se necesita un
# SimpleListFilter que traduzca la condición a un queryset real.
# ---------------------------------------------------------------------------
class EnRiesgoListFilter(admin.SimpleListFilter):
    title = 'en riesgo'
    parameter_name = 'en_riesgo'

    def lookups(self, request, model_admin):
        return (
            ('si', 'Sí — vencida y sin completar'),
            ('no', 'No'),
        )

    def queryset(self, request, queryset):
        ahora = timezone.now()
        condicion_riesgo = Q(fecha_limite_proyectada__lt=ahora) & ~Q(
            porcentaje_avance=100
        )
        if self.value() == 'si':
            return queryset.filter(condicion_riesgo)
        if self.value() == 'no':
            return queryset.exclude(condicion_riesgo)
        return queryset


# ---------------------------------------------------------------------------
# RegistroDowntime como TabularInline dentro de Tarea
# ---------------------------------------------------------------------------
class RegistroDowntimeInline(admin.TabularInline):
    model = RegistroDowntime
    extra = 0
    fields = (
        'causa_raiz',
        'detalle_tecnico',
        'duracion_horas_estimada',
        'creado_en_dispositivo',
    )
    readonly_fields = ('sincronizado_en_nube',)
    show_change_link = True  # permite saltar al detalle completo del registro
    ordering = ('-creado_en_dispositivo',)


# ---------------------------------------------------------------------------
# TAREA
# ---------------------------------------------------------------------------
@admin.register(Tarea)
class TareaAdmin(admin.ModelAdmin):
    list_display = (
        'titulo',
        'estado',
        'porcentaje_avance',
        'en_riesgo_display',
        'fecha_limite_proyectada',
    )
    list_filter = ('estado', EnRiesgoListFilter)
    search_fields = ('titulo', 'descripcion')
    date_hierarchy = 'fecha_limite_proyectada'
    readonly_fields = ('id', 'sincronizado_en_nube')
    inlines = [RegistroDowntimeInline]

    @admin.display(description='En Riesgo', boolean=True)
    def en_riesgo_display(self, obj):
        """
        True si la fecha límite ya pasó y la tarea no llegó al 100%.
        Tareas sin fecha_limite_proyectada nunca se marcan en riesgo: no hay
        base para evaluar vencimiento (evita falsos positivos silenciosos).
        """
        if not obj.fecha_limite_proyectada:
            return False
        return (
            obj.fecha_limite_proyectada < timezone.now()
            and obj.porcentaje_avance < 100
        )


# ---------------------------------------------------------------------------
# REGISTRO DE DOWNTIME (además de inline, se registra como entidad propia
# para poder auditar downtimes cross-tarea, ej. "todas las fallas mecánicas
# del mes", sin tener que entrar tarea por tarea).
# ---------------------------------------------------------------------------
@admin.register(RegistroDowntime)
class RegistroDowntimeAdmin(admin.ModelAdmin):
    list_display = ('tarea', 'causa_raiz', 'duracion_horas_estimada', 'creado_en_dispositivo')
    list_filter = ('causa_raiz',)
    search_fields = ('tarea__titulo', 'detalle_tecnico')
    autocomplete_fields = ('tarea',)  # requiere TareaAdmin.search_fields (ya definido arriba)
    readonly_fields = ('id', 'sincronizado_en_nube')
    date_hierarchy = 'creado_en_dispositivo'


# ---------------------------------------------------------------------------
# OPERADOR
# ---------------------------------------------------------------------------
@admin.register(Operador)
class OperadorAdmin(admin.ModelAdmin):
    list_display = ('apellidos', 'nombres', 'dni', 'cargo', 'turno_actual', 'fecha_ingreso_mina')
    list_filter = ('turno_actual', 'cargo')
    search_fields = ('dni', 'nombres', 'apellidos')
    readonly_fields = ('id', 'sincronizado_en_nube')
    ordering = ('apellidos', 'nombres')


# ---------------------------------------------------------------------------
# ITEM EPP (catálogo)
# ---------------------------------------------------------------------------
@admin.register(ItemEPP)
class ItemEPPAdmin(admin.ModelAdmin):
    list_display = ('codigo_inventario', 'descripcion', 'categoria', 'valor_reposicion', 'vida_util_meses')
    list_filter = ('categoria',)
    search_fields = ('codigo_inventario', 'descripcion')
    readonly_fields = ('id', 'sincronizado_en_nube')
    ordering = ('categoria', 'codigo_inventario')


# ---------------------------------------------------------------------------
# ASIGNACIÓN EPP
# ---------------------------------------------------------------------------
@admin.register(AsignacionEPP)
class AsignacionEPPAdmin(admin.ModelAdmin):
    list_display = (
        'operador',
        'item',
        'estado',
        'fecha_entrega',
        'fecha_devolucion_real',
        'monto_penalizacion_aplicado',
    )
    list_filter = ('estado',)
    search_fields = ('operador__dni', 'item__codigo_inventario')
    autocomplete_fields = ('operador', 'item')
    date_hierarchy = 'fecha_entrega'

    # DECISIÓN DE DISEÑO (no pedida explícitamente, la marco para que la
    # revise el Arquitecto): valor_reposicion_congelado y
    # monto_penalizacion_aplicado son read-only en el admin. La razón es que
    # ambos campos deben originarse SIEMPRE en AsignacionEPP.calcular_penalizacion()
    # para respetar el congelamiento de precio ya aprobado; permitir edición
    # manual libre desde /admin/ rompería esa garantía sin dejar rastro de
    # por qué cambió. Si quieren permitir corrección manual auditada, lo
    # correcto es un action/endpoint dedicado que llame a
    # calcular_penalizacion(forzar_recalculo=True) y quede logueado, no un
    # campo de texto libre en el form. Si prefieren que sea editable
    # directamente, quítenlo de esta tupla.
    readonly_fields = (
        'id',
        'sincronizado_en_nube',
        'valor_reposicion_congelado',
        'monto_penalizacion_aplicado',
    )