# Capa 1: Entorno de ejecución base (Imagen Alpine/Slim para reducir peso y vulnerabilidades)
FROM python:3.12-slim

# Capa 2: Variables de entorno del sistema (Deshabilita caché y buffering de I/O)
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Capa 3: Directorio de trabajo
WORKDIR /app

# Capa 4: Dependencias del sistema operativo (Requeridas para compilar psycopg2 y criptografía)
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libpq-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Capa 5: Gestión de dependencias Python
COPY requirements.txt /app/
RUN pip install --upgrade pip \
    && pip install -r requirements.txt

# Capa 6: Transferencia del código fuente
COPY . /app/

# Capa 7: Exposición del puerto de red
EXPOSE 8000

# Capa 8: Comando de ejecución WSGI concurrente (Gunicorn)
# Sustituye "fsm_unitec.wsgi" por el nombre real de tu módulo WSGI si difiere.
CMD ["sh", "-c", "python manage.py collectstatic --noinput && python manage.py migrate && python manage.py createsuperuser --noinput --username admin --email admin@unitec.com || true && gunicorn --bind 0.0.0.0:8000 --workers 3 core.wsgi:application"]