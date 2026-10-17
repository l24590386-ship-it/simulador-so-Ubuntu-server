from collections import deque
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Deque, Dict, List, Optional, Tuple

class TipoInterrupcion(str, Enum):
    TIMER = "TIMER"
    ES_COMPLETA = "ES_COMPLETA"
    LLAMADA_SISTEMA = "LLAMADA_SISTEMA"

@dataclass
class Interrupcion:
    tipo: TipoInterrupcion
    t: int
    origen: str
    pid: Optional[int] = None
    dispositivo: Optional[str] = None
    servicio: str = ""
    semaforo: Optional[str] = None

    def a_dict(self) -> dict:
        return {"tipo": self.tipo.value, "t": self.t, "origen": self.origen,
                "pid": self.pid, "dispositivo": self.dispositivo, "servicio": self.servicio,
                "semaforo": self.semaforo}

class Dispositivo:
    def __init__(self, nombre: str):
        self.nombre = nombre
        self.cola: Deque[Tuple[object, int]] = deque()
        self.actual = None
        self.restante = 0

    def solicitar(self, proceso, duracion: int):
        self.cola.append((proceso, max(1, duracion)))

    def tick(self):
        if self.actual is None and self.cola:
            self.actual, self.restante = self.cola.popleft()
        if self.actual is None:
            return None
        self.restante -= 1
        if self.restante <= 0:
            terminado, self.actual = self.actual, None
            return terminado
        return None

    def cancelar(self, proceso):
        if self.actual is proceso:
            self.actual, self.restante = None, 0
        else:
            self.cola = deque((p, d) for p, d in self.cola if p is not proceso)

    def a_dict(self) -> dict:
        return {"nombre": self.nombre,
                "atendiendo": self.actual.pid if self.actual else None,
                "restante": self.restante,
                "cola": [p.pid for p, _ in self.cola]}

class ControladorInterrupciones:
    def __init__(self):
        self.pendientes: Deque[Interrupcion] = deque()
        self.historial: List[Interrupcion] = []
        self.manejadores: Dict[TipoInterrupcion, Callable[[Interrupcion], None]] = {}

    def registrar(self, tipo: TipoInterrupcion, manejador):
        self.manejadores[tipo] = manejador

    def levantar(self, irq: Interrupcion):
        self.pendientes.append(irq)

    def atender(self, log):
        while self.pendientes:
            irq = self.pendientes.popleft()
            self.historial.append(irq)
            log("IRQ", f"{irq.tipo.value} ({irq.origen}): el CPU suspende lo que hacía, "
                       f"identifica el tipo y ejecuta su manejador", irq.pid)
            self.manejadores[irq.tipo](irq)