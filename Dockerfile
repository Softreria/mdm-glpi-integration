# Dockerfile para MDM-GLPI Integration
FROM python:3.9-slim

# Metadatos
LABEL maintainer="David Hernández <david@softreria.com>"
LABEL description="Integración entre ManageEngine MDM y GLPI"
LABEL version="1.0.0"

# Variables de entorno
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Crear usuario no-root
RUN groupadd -r mdmglpi && useradd -r -g mdmglpi mdmglpi

# Instalar dependencias del sistema
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Crear directorios de trabajo
WORKDIR /app

# Crear directorios necesarios
RUN mkdir -p /app/config /app/logs /app/data && \
    chown -R mdmglpi:mdmglpi /app

# Copiar archivos de dependencias
COPY requirements.txt pyproject.toml ./

# Instalar dependencias de Python
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código fuente
COPY src/ ./src/
COPY config/ ./config/

# Instalar la aplicación
RUN pip install -e .

# Cambiar al usuario no-root
USER mdmglpi

# Exponer puerto para métricas
EXPOSE 8080

# Volúmenes para datos persistentes
VOLUME ["/app/config", "/app/logs", "/app/data"]

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD mdm-glpi-sync health || exit 1

# Comando por defecto
CMD ["mdm-glpi-sync", "run"]