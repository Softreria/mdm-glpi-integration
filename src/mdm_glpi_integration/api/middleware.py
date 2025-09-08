"""Middleware personalizado para la aplicación FastAPI."""

import time
from typing import Callable, Dict, Optional
from collections import defaultdict, deque
from datetime import datetime, timedelta

import structlog
from fastapi import Request, Response, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

logger = structlog.get_logger()


class LoggingMiddleware(BaseHTTPMiddleware):
    """Middleware para logging de requests y responses."""
    
    def __init__(self, app: ASGIApp):
        super().__init__(app)
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Procesar request y response con logging.
        
        Args:
            request: Request HTTP
            call_next: Siguiente middleware/handler
            
        Returns:
            Response HTTP
        """
        start_time = time.time()
        
        # Log del request
        logger.info(
            "Request iniciado",
            method=request.method,
            path=request.url.path,
            query_params=dict(request.query_params),
            client_ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
            request_id=id(request)
        )
        
        try:
            # Procesar request
            response = await call_next(request)
            
            # Calcular tiempo de procesamiento
            process_time = time.time() - start_time
            
            # Log del response
            logger.info(
                "Request completado",
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                process_time=round(process_time, 4),
                request_id=id(request)
            )
            
            # Agregar headers de timing
            response.headers["X-Process-Time"] = str(process_time)
            response.headers["X-Request-ID"] = str(id(request))
            
            return response
            
        except Exception as e:
            # Log de errores
            process_time = time.time() - start_time
            
            logger.error(
                "Error en request",
                method=request.method,
                path=request.url.path,
                error=str(e),
                error_type=type(e).__name__,
                process_time=round(process_time, 4),
                request_id=id(request)
            )
            
            # Re-raise para que otros handlers lo manejen
            raise


class MetricsMiddleware(BaseHTTPMiddleware):
    """Middleware para recolección de métricas."""
    
    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self.request_count = defaultdict(int)
        self.request_duration = defaultdict(list)
        self.error_count = defaultdict(int)
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Procesar request y recolectar métricas.
        
        Args:
            request: Request HTTP
            call_next: Siguiente middleware/handler
            
        Returns:
            Response HTTP
        """
        start_time = time.time()
        method = request.method
        path = request.url.path
        
        try:
            # Procesar request
            response = await call_next(request)
            
            # Recolectar métricas
            duration = time.time() - start_time
            status_code = response.status_code
            
            # Incrementar contadores
            self.request_count[f"{method}_{path}"] += 1
            self.request_count[f"status_{status_code}"] += 1
            
            # Guardar duración (mantener solo últimas 1000)
            duration_key = f"{method}_{path}"
            if len(self.request_duration[duration_key]) >= 1000:
                self.request_duration[duration_key].pop(0)
            self.request_duration[duration_key].append(duration)
            
            # Actualizar métricas en el servicio si está disponible
            if hasattr(request.app.state, 'metrics_service'):
                metrics_service = request.app.state.metrics_service
                metrics_service.record_api_request(
                    method=method,
                    endpoint=path,
                    status_code=status_code,
                    duration=duration
                )
            
            return response
            
        except Exception as e:
            # Recolectar métricas de error
            duration = time.time() - start_time
            
            self.error_count[f"{method}_{path}"] += 1
            self.error_count[f"error_{type(e).__name__}"] += 1
            
            # Actualizar métricas de error
            if hasattr(request.app.state, 'metrics_service'):
                metrics_service = request.app.state.metrics_service
                metrics_service.record_error(
                    error_type=type(e).__name__,
                    endpoint=path
                )
            
            raise
    
    def get_metrics_summary(self) -> Dict:
        """Obtener resumen de métricas.
        
        Returns:
            Diccionario con métricas
        """
        return {
            "request_count": dict(self.request_count),
            "error_count": dict(self.error_count),
            "avg_duration": {
                key: sum(durations) / len(durations) if durations else 0
                for key, durations in self.request_duration.items()
            }
        }


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Middleware para rate limiting."""
    
    def __init__(self, app: ASGIApp, requests_per_minute: int = 60):
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self.requests: Dict[str, deque] = defaultdict(deque)
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Aplicar rate limiting por IP.
        
        Args:
            request: Request HTTP
            call_next: Siguiente middleware/handler
            
        Returns:
            Response HTTP
            
        Raises:
            HTTPException: Si se excede el rate limit
        """
        # Obtener IP del cliente
        client_ip = request.client.host if request.client else "unknown"
        
        # Limpiar requests antiguos (más de 1 minuto)
        now = datetime.now()
        cutoff = now - timedelta(minutes=1)
        
        client_requests = self.requests[client_ip]
        while client_requests and client_requests[0] < cutoff:
            client_requests.popleft()
        
        # Verificar rate limit
        if len(client_requests) >= self.requests_per_minute:
            logger.warning(
                "Rate limit excedido",
                client_ip=client_ip,
                requests_count=len(client_requests),
                limit=self.requests_per_minute
            )
            
            # Actualizar métricas si está disponible
            if hasattr(request.app.state, 'metrics_service'):
                metrics_service = request.app.state.metrics_service
                metrics_service.record_rate_limit_hit()
            
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Rate limit excedido",
                    "detail": f"Máximo {self.requests_per_minute} requests por minuto",
                    "retry_after": 60
                },
                headers={"Retry-After": "60"}
            )
        
        # Registrar request actual
        client_requests.append(now)
        
        # Procesar request
        return await call_next(request)


class SecurityMiddleware(BaseHTTPMiddleware):
    """Middleware para headers de seguridad."""
    
    def __init__(self, app: ASGIApp):
        super().__init__(app)
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Agregar headers de seguridad.
        
        Args:
            request: Request HTTP
            call_next: Siguiente middleware/handler
            
        Returns:
            Response HTTP con headers de seguridad
        """
        response = await call_next(request)
        
        # Headers de seguridad
        security_headers = {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
            "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Content-Security-Policy": "default-src 'self'",
            "Permissions-Policy": "geolocation=(), microphone=(), camera=()"
        }
        
        for header, value in security_headers.items():
            response.headers[header] = value
        
        return response


class HealthCheckMiddleware(BaseHTTPMiddleware):
    """Middleware para health checks automáticos."""
    
    def __init__(self, app: ASGIApp, check_interval: int = 300):
        super().__init__(app)
        self.check_interval = check_interval
        self.last_check = datetime.now()
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Ejecutar health check periódico.
        
        Args:
            request: Request HTTP
            call_next: Siguiente middleware/handler
            
        Returns:
            Response HTTP
        """
        # Verificar si es tiempo de health check
        now = datetime.now()
        if (now - self.last_check).total_seconds() > self.check_interval:
            if hasattr(request.app.state, 'health_checker'):
                try:
                    health_checker = request.app.state.health_checker
                    health_status = await health_checker.check_health()
                    
                    # Actualizar métricas de salud
                    if hasattr(request.app.state, 'metrics_service'):
                        metrics_service = request.app.state.metrics_service
                        metrics_service.update_health_metrics(
                            health_checker.get_health_summary()
                        )
                    
                    logger.debug(
                        "Health check automático completado",
                        status=health_status.overall_status.value
                    )
                    
                except Exception as e:
                    logger.error(
                        "Error en health check automático",
                        error=str(e)
                    )
                
                self.last_check = now
        
        return await call_next(request)