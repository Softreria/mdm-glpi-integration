"""Rate limiter para controlar la velocidad de peticiones a APIs."""

import asyncio
import time
from typing import Optional
from collections import deque


class RateLimiter:
    """Rate limiter basado en token bucket para controlar peticiones por minuto."""
    
    def __init__(self, max_requests: int, time_window: int = 60):
        """Inicializar el rate limiter.
        
        Args:
            max_requests: Número máximo de peticiones permitidas
            time_window: Ventana de tiempo en segundos (default: 60 para por minuto)
        """
        self.max_requests = max_requests
        self.time_window = time_window
        self.requests = deque()
        self._lock = asyncio.Lock()
    
    async def acquire(self) -> None:
        """Adquirir permiso para hacer una petición.
        
        Bloquea hasta que sea seguro hacer la petición.
        """
        async with self._lock:
            now = time.time()
            
            # Remover peticiones fuera de la ventana de tiempo
            while self.requests and self.requests[0] <= now - self.time_window:
                self.requests.popleft()
            
            # Si hemos alcanzado el límite, esperar
            if len(self.requests) >= self.max_requests:
                # Calcular cuánto tiempo esperar
                oldest_request = self.requests[0]
                wait_time = self.time_window - (now - oldest_request)
                
                if wait_time > 0:
                    await asyncio.sleep(wait_time)
                    # Recursivamente intentar de nuevo
                    await self.acquire()
                    return
            
            # Registrar esta petición
            self.requests.append(now)
    
    def can_proceed(self) -> bool:
        """Verificar si se puede proceder sin bloquear.
        
        Returns:
            True si se puede hacer una petición inmediatamente
        """
        now = time.time()
        
        # Remover peticiones fuera de la ventana de tiempo
        while self.requests and self.requests[0] <= now - self.time_window:
            self.requests.popleft()
        
        return len(self.requests) < self.max_requests
    
    def get_wait_time(self) -> float:
        """Obtener el tiempo de espera necesario.
        
        Returns:
            Tiempo en segundos que hay que esperar, 0 si se puede proceder
        """
        if self.can_proceed():
            return 0.0
        
        now = time.time()
        oldest_request = self.requests[0]
        return max(0.0, self.time_window - (now - oldest_request))
    
    def reset(self) -> None:
        """Resetear el rate limiter."""
        self.requests.clear()
    
    @property
    def current_usage(self) -> int:
        """Obtener el uso actual del rate limiter.
        
        Returns:
            Número de peticiones en la ventana actual
        """
        now = time.time()
        
        # Remover peticiones fuera de la ventana de tiempo
        while self.requests and self.requests[0] <= now - self.time_window:
            self.requests.popleft()
        
        return len(self.requests)
    
    @property
    def usage_percentage(self) -> float:
        """Obtener el porcentaje de uso actual.
        
        Returns:
            Porcentaje de uso (0.0 a 100.0)
        """
        return (self.current_usage / self.max_requests) * 100.0


class AdaptiveRateLimiter(RateLimiter):
    """Rate limiter adaptativo que ajusta la velocidad basado en errores."""
    
    def __init__(self, max_requests: int, time_window: int = 60, 
                 backoff_factor: float = 0.5, recovery_factor: float = 1.1):
        """Inicializar el rate limiter adaptativo.
        
        Args:
            max_requests: Número máximo de peticiones permitidas
            time_window: Ventana de tiempo en segundos
            backoff_factor: Factor de reducción cuando hay errores (0.0-1.0)
            recovery_factor: Factor de recuperación cuando no hay errores
        """
        super().__init__(max_requests, time_window)
        self.original_max_requests = max_requests
        self.backoff_factor = backoff_factor
        self.recovery_factor = recovery_factor
        self.consecutive_errors = 0
        self.consecutive_successes = 0
    
    def report_error(self) -> None:
        """Reportar un error para ajustar la velocidad."""
        self.consecutive_errors += 1
        self.consecutive_successes = 0
        
        # Reducir la velocidad
        new_max = int(self.max_requests * self.backoff_factor)
        self.max_requests = max(1, new_max)  # Mínimo 1 petición
    
    def report_success(self) -> None:
        """Reportar un éxito para potencialmente aumentar la velocidad."""
        self.consecutive_successes += 1
        self.consecutive_errors = 0
        
        # Después de varios éxitos, intentar recuperar velocidad
        if self.consecutive_successes >= 5:
            new_max = int(self.max_requests * self.recovery_factor)
            self.max_requests = min(self.original_max_requests, new_max)
            self.consecutive_successes = 0
    
    def reset_to_original(self) -> None:
        """Resetear a la velocidad original."""
        self.max_requests = self.original_max_requests
        self.consecutive_errors = 0
        self.consecutive_successes = 0
        self.reset()


class BurstRateLimiter:
    """Rate limiter que permite ráfagas controladas."""
    
    def __init__(self, sustained_rate: int, burst_rate: int, 
                 burst_duration: int = 10, time_window: int = 60):
        """Inicializar el burst rate limiter.
        
        Args:
            sustained_rate: Velocidad sostenida (peticiones por time_window)
            burst_rate: Velocidad de ráfaga (peticiones por burst_duration)
            burst_duration: Duración de la ráfaga en segundos
            time_window: Ventana de tiempo para velocidad sostenida
        """
        self.sustained_limiter = RateLimiter(sustained_rate, time_window)
        self.burst_limiter = RateLimiter(burst_rate, burst_duration)
        self._lock = asyncio.Lock()
    
    async def acquire(self) -> None:
        """Adquirir permiso respetando ambos límites."""
        async with self._lock:
            # Debe pasar ambos limitadores
            await self.sustained_limiter.acquire()
            await self.burst_limiter.acquire()
    
    def can_proceed(self) -> bool:
        """Verificar si se puede proceder sin bloquear."""
        return (self.sustained_limiter.can_proceed() and 
                self.burst_limiter.can_proceed())
    
    def get_wait_time(self) -> float:
        """Obtener el tiempo de espera necesario."""
        sustained_wait = self.sustained_limiter.get_wait_time()
        burst_wait = self.burst_limiter.get_wait_time()
        return max(sustained_wait, burst_wait)
    
    def reset(self) -> None:
        """Resetear ambos limitadores."""
        self.sustained_limiter.reset()
        self.burst_limiter.reset()
    
    @property
    def current_usage(self) -> dict:
        """Obtener el uso actual de ambos limitadores."""
        return {
            "sustained": self.sustained_limiter.current_usage,
            "burst": self.burst_limiter.current_usage
        }