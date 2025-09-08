# Guía de Despliegue

Esta guía cubre diferentes opciones de despliegue para la integración MDM-GLPI en entornos de producción.

## 🐳 Docker (Recomendado)

### Dockerfile

```dockerfile
FROM python:3.9-slim

# Instalar dependencias del sistema
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Crear usuario no-root
RUN useradd --create-home --shell /bin/bash mdmglpi

# Establecer directorio de trabajo
WORKDIR /app

# Copiar requirements y instalar dependencias
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código fuente
COPY src/ ./src/
COPY cli.py .
COPY config.example.yaml ./config.yaml

# Crear directorios necesarios
RUN mkdir -p /app/data /app/logs && \
    chown -R mdmglpi:mdmglpi /app

# Cambiar a usuario no-root
USER mdmglpi

# Exponer puerto
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python cli.py health || exit 1

# Comando por defecto
CMD ["python", "cli.py", "run"]
```

### Docker Compose

```yaml
# docker-compose.yml
version: '3.8'

services:
  mdm-glpi-integration:
    build: .
    container_name: mdm-glpi-integration
    restart: unless-stopped
    ports:
      - "8080:8080"
    environment:
      - MDM_GLPI_DATABASE__URL=postgresql://mdmglpi:password@postgres:5432/mdmglpi
      - MDM_GLPI_MDM__API_KEY=${MDM_API_KEY}
      - MDM_GLPI_GLPI__APP_TOKEN=${GLPI_APP_TOKEN}
      - MDM_GLPI_GLPI__USER_TOKEN=${GLPI_USER_TOKEN}
    volumes:
      - ./config.yaml:/app/config.yaml:ro
      - ./data:/app/data
      - ./logs:/app/logs
    depends_on:
      - postgres
    networks:
      - mdm-glpi-network

  postgres:
    image: postgres:15-alpine
    container_name: mdm-glpi-postgres
    restart: unless-stopped
    environment:
      - POSTGRES_DB=mdmglpi
      - POSTGRES_USER=mdmglpi
      - POSTGRES_PASSWORD=password
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./init.sql:/docker-entrypoint-initdb.d/init.sql:ro
    networks:
      - mdm-glpi-network

  prometheus:
    image: prom/prometheus:latest
    container_name: mdm-glpi-prometheus
    restart: unless-stopped
    ports:
      - "9090:9090"
    volumes:
      - ./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml:ro
      - prometheus_data:/prometheus
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
      - '--web.console.libraries=/etc/prometheus/console_libraries'
      - '--web.console.templates=/etc/prometheus/consoles'
    networks:
      - mdm-glpi-network

  grafana:
    image: grafana/grafana:latest
    container_name: mdm-glpi-grafana
    restart: unless-stopped
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
    volumes:
      - grafana_data:/var/lib/grafana
      - ./monitoring/grafana/dashboards:/etc/grafana/provisioning/dashboards:ro
      - ./monitoring/grafana/datasources:/etc/grafana/provisioning/datasources:ro
    networks:
      - mdm-glpi-network

volumes:
  postgres_data:
  prometheus_data:
  grafana_data:

networks:
  mdm-glpi-network:
    driver: bridge
```

### Variables de Entorno (.env)

```bash
# .env
MDM_API_KEY=your-mdm-api-key
GLPI_APP_TOKEN=your-glpi-app-token
GLPI_USER_TOKEN=your-glpi-user-token
POSTGRES_PASSWORD=secure-password
```

### Comandos Docker

```bash
# Construir imagen
docker build -t mdm-glpi-integration .

# Ejecutar con Docker Compose
docker-compose up -d

# Ver logs
docker-compose logs -f mdm-glpi-integration

# Ejecutar comandos
docker-compose exec mdm-glpi-integration python cli.py health
docker-compose exec mdm-glpi-integration python cli.py sync --full

# Parar servicios
docker-compose down

# Parar y eliminar volúmenes
docker-compose down -v
```

## ☸️ Kubernetes

### Namespace

```yaml
# k8s/namespace.yaml
apiVersion: v1
kind: Namespace
metadata:
  name: mdm-glpi
  labels:
    name: mdm-glpi
```

### ConfigMap

```yaml
# k8s/configmap.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: mdm-glpi-config
  namespace: mdm-glpi
data:
  config.yaml: |
    mdm:
      base_url: "https://mdm.company.com"
      timeout: 30
      rate_limit: 100
      ssl_verify: true
    
    glpi:
      base_url: "https://glpi.company.com/apirest.php"
      timeout: 30
      ssl_verify: true
    
    sync:
      schedule_full: "0 2 * * *"
      schedule_incremental: "*/15 * * * *"
      batch_size: 50
      max_retries: 3
      initial_sync: true
    
    database:
      url: "postgresql://mdmglpi:password@postgres:5432/mdmglpi"
      pool_size: 10
      max_overflow: 20
    
    monitoring:
      enable_metrics: true
      port: 8080
      host: "0.0.0.0"
    
    logging:
      level: "INFO"
      format: "json"
      file: "/app/logs/mdm-glpi.log"
```

### Secret

```yaml
# k8s/secret.yaml
apiVersion: v1
kind: Secret
metadata:
  name: mdm-glpi-secrets
  namespace: mdm-glpi
type: Opaque
data:
  mdm-api-key: <base64-encoded-api-key>
  glpi-app-token: <base64-encoded-app-token>
  glpi-user-token: <base64-encoded-user-token>
  postgres-password: <base64-encoded-password>
```

### Deployment

```yaml
# k8s/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: mdm-glpi-integration
  namespace: mdm-glpi
  labels:
    app: mdm-glpi-integration
spec:
  replicas: 2
  selector:
    matchLabels:
      app: mdm-glpi-integration
  template:
    metadata:
      labels:
        app: mdm-glpi-integration
    spec:
      containers:
      - name: mdm-glpi-integration
        image: mdm-glpi-integration:latest
        ports:
        - containerPort: 8080
          name: http
        env:
        - name: MDM_GLPI_MDM__API_KEY
          valueFrom:
            secretKeyRef:
              name: mdm-glpi-secrets
              key: mdm-api-key
        - name: MDM_GLPI_GLPI__APP_TOKEN
          valueFrom:
            secretKeyRef:
              name: mdm-glpi-secrets
              key: glpi-app-token
        - name: MDM_GLPI_GLPI__USER_TOKEN
          valueFrom:
            secretKeyRef:
              name: mdm-glpi-secrets
              key: glpi-user-token
        - name: MDM_GLPI_DATABASE__URL
          value: "postgresql://mdmglpi:$(POSTGRES_PASSWORD)@postgres:5432/mdmglpi"
        - name: POSTGRES_PASSWORD
          valueFrom:
            secretKeyRef:
              name: mdm-glpi-secrets
              key: postgres-password
        volumeMounts:
        - name: config
          mountPath: /app/config.yaml
          subPath: config.yaml
        - name: logs
          mountPath: /app/logs
        - name: data
          mountPath: /app/data
        livenessProbe:
          httpGet:
            path: /live
            port: 8080
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /ready
            port: 8080
          initialDelaySeconds: 5
          periodSeconds: 5
        resources:
          requests:
            memory: "256Mi"
            cpu: "100m"
          limits:
            memory: "512Mi"
            cpu: "500m"
      volumes:
      - name: config
        configMap:
          name: mdm-glpi-config
      - name: logs
        emptyDir: {}
      - name: data
        persistentVolumeClaim:
          claimName: mdm-glpi-data
```

### Service

```yaml
# k8s/service.yaml
apiVersion: v1
kind: Service
metadata:
  name: mdm-glpi-service
  namespace: mdm-glpi
  labels:
    app: mdm-glpi-integration
spec:
  selector:
    app: mdm-glpi-integration
  ports:
  - name: http
    port: 80
    targetPort: 8080
    protocol: TCP
  type: ClusterIP
```

### Ingress

```yaml
# k8s/ingress.yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: mdm-glpi-ingress
  namespace: mdm-glpi
  annotations:
    nginx.ingress.kubernetes.io/rewrite-target: /
    nginx.ingress.kubernetes.io/ssl-redirect: "true"
    cert-manager.io/cluster-issuer: "letsencrypt-prod"
spec:
  tls:
  - hosts:
    - mdm-glpi.company.com
    secretName: mdm-glpi-tls
  rules:
  - host: mdm-glpi.company.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: mdm-glpi-service
            port:
              number: 80
```

### PersistentVolumeClaim

```yaml
# k8s/pvc.yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: mdm-glpi-data
  namespace: mdm-glpi
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 10Gi
  storageClassName: fast-ssd
```

### CronJob para Limpieza

```yaml
# k8s/cronjob.yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: mdm-glpi-cleanup
  namespace: mdm-glpi
spec:
  schedule: "0 3 * * 0"  # Domingos a las 3 AM
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: cleanup
            image: mdm-glpi-integration:latest
            command: ["python", "cli.py", "admin", "cleanup-logs"]
            env:
            - name: MDM_GLPI_DATABASE__URL
              value: "postgresql://mdmglpi:$(POSTGRES_PASSWORD)@postgres:5432/mdmglpi"
            - name: POSTGRES_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: mdm-glpi-secrets
                  key: postgres-password
          restartPolicy: OnFailure
```

### Comandos Kubernetes

```bash
# Aplicar configuración
kubectl apply -f k8s/

# Ver estado
kubectl get pods -n mdm-glpi
kubectl get services -n mdm-glpi

# Ver logs
kubectl logs -f deployment/mdm-glpi-integration -n mdm-glpi

# Ejecutar comandos
kubectl exec -it deployment/mdm-glpi-integration -n mdm-glpi -- python cli.py health

# Escalar
kubectl scale deployment mdm-glpi-integration --replicas=3 -n mdm-glpi

# Actualizar imagen
kubectl set image deployment/mdm-glpi-integration mdm-glpi-integration=mdm-glpi-integration:v1.1.0 -n mdm-glpi
```

## 🖥️ Instalación Tradicional

### Requisitos del Sistema

```bash
# Ubuntu/Debian
sudo apt update
sudo apt install -y python3.9 python3.9-venv python3.9-dev \
                    postgresql-client libpq-dev gcc \
                    nginx supervisor

# CentOS/RHEL
sudo yum install -y python39 python39-devel postgresql-devel \
                    gcc nginx supervisor
```

### Instalación de la Aplicación

```bash
# Crear usuario del sistema
sudo useradd --system --create-home --shell /bin/bash mdmglpi

# Cambiar a usuario mdmglpi
sudo su - mdmglpi

# Clonar repositorio
git clone https://github.com/company/mdm-glpi-integration.git
cd mdm-glpi-integration

# Crear entorno virtual
python3.9 -m venv venv
source venv/bin/activate

# Instalar dependencias
pip install -r requirements.txt

# Configurar aplicación
cp config.example.yaml config.yaml
# Editar config.yaml con configuración específica

# Crear directorios
mkdir -p data logs

# Probar instalación
python cli.py test-connections
```

### Configuración de Supervisor

```ini
# /etc/supervisor/conf.d/mdm-glpi.conf
[program:mdm-glpi-integration]
command=/home/mdmglpi/mdm-glpi-integration/venv/bin/python cli.py run
directory=/home/mdmglpi/mdm-glpi-integration
user=mdmglpi
autostart=true
autorestart=true
stderr_logfile=/var/log/supervisor/mdm-glpi-integration.err.log
stdout_logfile=/var/log/supervisor/mdm-glpi-integration.out.log
environment=PATH="/home/mdmglpi/mdm-glpi-integration/venv/bin"
```

```bash
# Recargar supervisor
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl start mdm-glpi-integration

# Ver estado
sudo supervisorctl status mdm-glpi-integration
```

### Configuración de Nginx

```nginx
# /etc/nginx/sites-available/mdm-glpi
server {
    listen 80;
    server_name mdm-glpi.company.com;
    
    # Redirect HTTP to HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name mdm-glpi.company.com;
    
    # SSL configuration
    ssl_certificate /etc/ssl/certs/mdm-glpi.crt;
    ssl_certificate_key /etc/ssl/private/mdm-glpi.key;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-RSA-AES256-GCM-SHA512:DHE-RSA-AES256-GCM-SHA512;
    
    # Security headers
    add_header X-Frame-Options DENY;
    add_header X-Content-Type-Options nosniff;
    add_header X-XSS-Protection "1; mode=block";
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains";
    
    # Proxy to application
    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Timeouts
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }
    
    # Health check endpoint
    location /health {
        proxy_pass http://127.0.0.1:8080/health;
        access_log off;
    }
    
    # Metrics endpoint (restrict access)
    location /metrics {
        allow 10.0.0.0/8;
        allow 172.16.0.0/12;
        allow 192.168.0.0/16;
        deny all;
        
        proxy_pass http://127.0.0.1:8080/metrics;
    }
}
```

```bash
# Habilitar sitio
sudo ln -s /etc/nginx/sites-available/mdm-glpi /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### Configuración de Systemd (Alternativa a Supervisor)

```ini
# /etc/systemd/system/mdm-glpi-integration.service
[Unit]
Description=MDM-GLPI Integration Service
After=network.target postgresql.service
Requires=postgresql.service

[Service]
Type=simple
User=mdmglpi
Group=mdmglpi
WorkingDirectory=/home/mdmglpi/mdm-glpi-integration
Environment=PATH=/home/mdmglpi/mdm-glpi-integration/venv/bin
ExecStart=/home/mdmglpi/mdm-glpi-integration/venv/bin/python cli.py run
Restart=always
RestartSec=10

# Security settings
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/home/mdmglpi/mdm-glpi-integration/data
ReadWritePaths=/home/mdmglpi/mdm-glpi-integration/logs

[Install]
WantedBy=multi-user.target
```

```bash
# Habilitar y iniciar servicio
sudo systemctl daemon-reload
sudo systemctl enable mdm-glpi-integration
sudo systemctl start mdm-glpi-integration

# Ver estado
sudo systemctl status mdm-glpi-integration
sudo journalctl -u mdm-glpi-integration -f
```

## 📊 Monitoreo

### Prometheus Configuration

```yaml
# monitoring/prometheus.yml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

rule_files:
  - "rules/*.yml"

scrape_configs:
  - job_name: 'mdm-glpi-integration'
    static_configs:
      - targets: ['mdm-glpi-integration:8080']
    metrics_path: '/metrics'
    scrape_interval: 30s
    scrape_timeout: 10s

alerting:
  alertmanagers:
    - static_configs:
        - targets:
          - alertmanager:9093
```

### Grafana Dashboard

```json
{
  "dashboard": {
    "title": "MDM-GLPI Integration",
    "panels": [
      {
        "title": "Sync Status",
        "type": "stat",
        "targets": [
          {
            "expr": "mdm_glpi_sync_total",
            "legendFormat": "Total Syncs"
          }
        ]
      },
      {
        "title": "Devices Processed",
        "type": "graph",
        "targets": [
          {
            "expr": "rate(mdm_glpi_devices_processed_total[5m])",
            "legendFormat": "Devices/sec"
          }
        ]
      },
      {
        "title": "API Response Times",
        "type": "graph",
        "targets": [
          {
            "expr": "histogram_quantile(0.95, rate(mdm_glpi_api_request_duration_seconds_bucket[5m]))",
            "legendFormat": "95th percentile"
          }
        ]
      }
    ]
  }
}
```

### Alerting Rules

```yaml
# monitoring/rules/mdm-glpi.yml
groups:
  - name: mdm-glpi-integration
    rules:
      - alert: MDMGLPISyncFailed
        expr: increase(mdm_glpi_sync_errors_total[1h]) > 5
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "MDM-GLPI sync failures detected"
          description: "More than 5 sync failures in the last hour"
      
      - alert: MDMGLPIHighResponseTime
        expr: histogram_quantile(0.95, rate(mdm_glpi_api_request_duration_seconds_bucket[5m])) > 5
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "High API response times"
          description: "95th percentile response time is above 5 seconds"
      
      - alert: MDMGLPIServiceDown
        expr: up{job="mdm-glpi-integration"} == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "MDM-GLPI Integration service is down"
          description: "The MDM-GLPI Integration service has been down for more than 1 minute"
```

## 🔒 Seguridad

### Configuración de Firewall

```bash
# UFW (Ubuntu)
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 80/tcp    # HTTP
sudo ufw allow 443/tcp   # HTTPS
sudo ufw enable

# iptables
sudo iptables -A INPUT -p tcp --dport 22 -j ACCEPT
sudo iptables -A INPUT -p tcp --dport 80 -j ACCEPT
sudo iptables -A INPUT -p tcp --dport 443 -j ACCEPT
sudo iptables -A INPUT -p tcp --dport 8080 -s 127.0.0.1 -j ACCEPT
sudo iptables -A INPUT -j DROP
```

### SSL/TLS Configuration

```bash
# Generar certificado Let's Encrypt
sudo certbot --nginx -d mdm-glpi.company.com

# O usar certificado propio
sudo openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout /etc/ssl/private/mdm-glpi.key \
    -out /etc/ssl/certs/mdm-glpi.crt
```

### Configuración de Backup

```bash
#!/bin/bash
# backup.sh

BACKUP_DIR="/backup/mdm-glpi"
DATE=$(date +%Y%m%d_%H%M%S)

# Crear directorio de backup
mkdir -p $BACKUP_DIR

# Backup de base de datos
pg_dump -h localhost -U mdmglpi mdmglpi | gzip > $BACKUP_DIR/db_$DATE.sql.gz

# Backup de configuración
tar -czf $BACKUP_DIR/config_$DATE.tar.gz /home/mdmglpi/mdm-glpi-integration/config.yaml

# Backup de logs (últimos 7 días)
find /home/mdmglpi/mdm-glpi-integration/logs -name "*.log" -mtime -7 | \
    tar -czf $BACKUP_DIR/logs_$DATE.tar.gz -T -

# Limpiar backups antiguos (más de 30 días)
find $BACKUP_DIR -name "*.gz" -mtime +30 -delete

echo "Backup completed: $DATE"
```

```bash
# Agregar a crontab
crontab -e
# Agregar línea:
0 2 * * * /home/mdmglpi/backup.sh >> /var/log/mdm-glpi-backup.log 2>&1
```

## 🚀 Optimización de Rendimiento

### Configuración de Base de Datos

```sql
-- PostgreSQL optimizations
-- /etc/postgresql/15/main/postgresql.conf

shared_buffers = 256MB
effective_cache_size = 1GB
maintenance_work_mem = 64MB
checkpoint_completion_target = 0.9
wal_buffers = 16MB
default_statistics_target = 100
random_page_cost = 1.1
effective_io_concurrency = 200

-- Índices recomendados
CREATE INDEX CONCURRENTLY idx_sync_records_device_id ON sync_records(device_id);
CREATE INDEX CONCURRENTLY idx_sync_records_timestamp ON sync_records(timestamp);
CREATE INDEX CONCURRENTLY idx_sync_logs_sync_id ON sync_logs(sync_id);
CREATE INDEX CONCURRENTLY idx_device_mapping_mdm_id ON device_mapping(mdm_device_id);
```

### Configuración de Aplicación

```yaml
# config.prod.yaml - Optimizaciones
sync:
  batch_size: 100          # Aumentar para mejor throughput
  max_retries: 2           # Reducir para fallar más rápido
  
database:
  pool_size: 20            # Aumentar pool de conexiones
  max_overflow: 30
  pool_timeout: 10
  pool_recycle: 1800
  
connectors:
  mdm:
    timeout: 15            # Reducir timeout
    rate_limit: 200        # Aumentar si el MDM lo permite
  glpi:
    timeout: 15
    session_timeout: 1800  # Reducir para renovar sesiones
```

## 📋 Checklist de Despliegue

### Pre-despliegue

- [ ] Verificar conectividad a MDM y GLPI
- [ ] Configurar base de datos
- [ ] Configurar certificados SSL
- [ ] Configurar backup
- [ ] Configurar monitoreo
- [ ] Probar configuración en entorno de staging

### Despliegue

- [ ] Desplegar aplicación
- [ ] Verificar health checks
- [ ] Ejecutar sincronización de prueba
- [ ] Configurar proxy reverso
- [ ] Configurar alertas
- [ ] Documentar URLs y credenciales

### Post-despliegue

- [ ] Monitorear logs por 24h
- [ ] Verificar métricas
- [ ] Probar recuperación ante fallos
- [ ] Entrenar al equipo de operaciones
- [ ] Documentar procedimientos de troubleshooting

## 🆘 Troubleshooting

Ver [`troubleshooting.md`](troubleshooting.md) para guías detalladas de solución de problemas.