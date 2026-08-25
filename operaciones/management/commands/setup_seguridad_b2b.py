"""
operaciones/management/commands/setup_seguridad_b2b.py

Crea (o re-sincroniza) el grupo "Auditoria_Cliente_Minero" con permisos de
SOLO LECTURA sobre las 5 entidades del Dashboard B2B.

Diseño deliberado: usa `grupo.permissions.set(...)` en vez de `.add(...)`.
`.set()` REEMPLAZA la lista completa de permisos del grupo, así que correr
este comando de nuevo (en el próximo deploy, por ejemplo) deja el grupo con
EXACTAMENTE los 5 permisos view_* — incluso si alguien, por error, le
asignó a mano un add_/change_/delete_ desde el admin en el medio. Con
`.add()` eso no se habría corregido solo; con `.set()` sí, cada vez que se
ejecute. Por eso el comando es seguro de correr repetidamente (idempotente).

Requisito previo: los permisos view_/add_/change_/delete_ los genera Django
automáticamente durante `migrate` (señal post_migrate). Si corres este
comando ANTES de haber migrado los modelos de 'operaciones', va a fallar
explícitamente con CommandError en vez de crear un grupo a medias.
"""
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand, CommandError

NOMBRE_GRUPO = 'Auditoria_Cliente_Minero'
APP_LABEL = 'operaciones'

# Nombre del modelo tal como Django lo registra internamente (siempre en
# minúsculas y sin guiones bajos, independientemente de cómo se llame la
# clase en models.py).
MODELOS_A_AUDITAR = [
    'tarea',
    'registrodowntime',
    'operador',
    'itemepp',
    'asignacionepp',
]


class Command(BaseCommand):
    help = (
        'Crea/actualiza el grupo "Auditoria_Cliente_Minero" con permisos '
        'de SOLO LECTURA (view_*) sobre Tarea, RegistroDowntime, Operador, '
        'ItemEPP y AsignacionEPP. Idempotente: puede correrse en cada '
        'deploy sin duplicar el grupo ni acumular permisos de escritura.'
    )

    def handle(self, *args, **options):
        grupo, creado = Group.objects.get_or_create(name=NOMBRE_GRUPO)

        if creado:
            self.stdout.write(
                self.style.SUCCESS(f'Grupo "{NOMBRE_GRUPO}" creado.')
            )
        else:
            self.stdout.write(
                self.style.WARNING(
                    f'Grupo "{NOMBRE_GRUPO}" ya existía; '
                    're-sincronizando sus permisos desde cero.'
                )
            )

        permisos_view = []
        modelos_no_encontrados = []

        for nombre_modelo in MODELOS_A_AUDITAR:
            try:
                content_type = ContentType.objects.get(
                    app_label=APP_LABEL, model=nombre_modelo
                )
            except ContentType.DoesNotExist:
                modelos_no_encontrados.append(nombre_modelo)
                continue

            codename = f'view_{nombre_modelo}'
            try:
                permiso = Permission.objects.get(
                    content_type=content_type, codename=codename
                )
            except Permission.DoesNotExist:
                raise CommandError(
                    f'No se encontró el permiso "{codename}" para '
                    f'"{APP_LABEL}.{nombre_modelo}". ¿Corriste `migrate` '
                    'después de crear estos modelos? Django genera los '
                    'permisos view_/add_/change_/delete_ automáticamente '
                    'en la migración, no hay que crearlos a mano.'
                )

            permisos_view.append(permiso)
            self.stdout.write(f'  -> permiso localizado: {APP_LABEL}.{codename}')

        if modelos_no_encontrados:
            raise CommandError(
                f'No existen modelos registrados en la app "{APP_LABEL}" '
                f'para: {", ".join(modelos_no_encontrados)}. Verifica que '
                'estén en operaciones/models.py y que hayas corrido '
                '`python manage.py migrate`.'
            )

        # Reemplaza TODA la lista de permisos del grupo por estos 5.
        # Esto es lo que garantiza el requisito 3 (cero add/change/delete),
        # no una omisión sino una limpieza activa en cada corrida.
        grupo.permissions.set(permisos_view)

        self.stdout.write(
            self.style.SUCCESS(
                f'Grupo "{NOMBRE_GRUPO}" ahora tiene EXACTAMENTE '
                f'{len(permisos_view)} permisos, todos view_*, sobre: '
                f'{", ".join(MODELOS_A_AUDITAR)}.'
            )
        )

        # Verificación post-condición explícita: en vez de asumir que
        # .set() hizo lo esperado, se relee de la base de datos y se
        # confirma que no quedó colgando ningún permiso de escritura.
        codenames_finales = set(
            grupo.permissions.values_list('codename', flat=True)
        )
        permisos_peligrosos = {
            c for c in codenames_finales
            if c.startswith(('add_', 'change_', 'delete_'))
        }

        if permisos_peligrosos:
            raise CommandError(
                'Verificación de seguridad FALLÓ: el grupo quedó con '
                f'permisos de escritura inesperados: {permisos_peligrosos}. '
                'No se debe otorgar acceso al cliente minero hasta '
                'resolver esto.'
            )

        self.stdout.write(
            self.style.SUCCESS(
                'Verificación de seguridad OK: cero permisos de '
                'add/change/delete en el grupo "Auditoria_Cliente_Minero".'
            )
        )
        self.stdout.write(
            self.style.SUCCESS(
                'Listo. Asigna usuarios del cliente minero a este grupo '
                'desde el admin (Users -> seleccionar usuario -> Groups) '
                'o vía script; este comando no crea usuarios, solo el '
                'grupo y sus permisos.'
            )
        )