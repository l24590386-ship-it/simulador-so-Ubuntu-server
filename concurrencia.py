from collections import deque
from typing import Deque, Dict, Optional, Set

class RecursoCompartido:
    def __init__(self, nombre: str, valor: int = 0):
        self.nombre = nombre
        self.valor = valor
        self.esperado = valor
        self.version = 0
        self.perdidas = 0
        self.escrituras = 0
        self.dentro: Set[int] = set()
        self.max_dentro = 0

    def leer(self, pid: int) -> int:
        self.dentro.add(pid)
        self.max_dentro = max(self.max_dentro, len(self.dentro))
        return self.valor

    def escribir(self, pid: int, nuevo: int, delta: int, version_leida: int) -> bool:
        carrera = version_leida != self.version
        if carrera:
            self.perdidas += 1
        self.esperado += delta
        self.valor = nuevo
        self.version += 1
        self.escrituras += 1
        self.dentro.discard(pid)
        return carrera

    def a_dict(self) -> dict:
        return {"nombre": self.nombre, "valor": self.valor, "esperado": self.esperado,
                "perdidas": self.perdidas, "dentro": sorted(self.dentro),
                "max_dentro": self.max_dentro}

class Semaforo:
    def __init__(self, nombre: str, valor: int = 1):
        self.nombre = nombre
        self.inicial = valor
        self.valor = valor
        self.binario = (valor == 1)
        self.cola: Deque = deque()
        self.titulares: Set[int] = set()
        self.max_titulares = 0
        self.ops_p = 0
        self.ops_v = 0

    def _entra(self, p):
        self.titulares.add(p.pid)
        self.max_titulares = max(self.max_titulares, len(self.titulares))

    def P(self, p) -> bool:
        self.ops_p += 1
        if self.valor > 0:
            self.valor -= 1
            self._entra(p)
            return True
        self.cola.append(p)
        return False

    def V(self, p=None):
        self.ops_v += 1
        if p is not None:
            self.titulares.discard(p.pid)
        if self.cola:
            siguiente = self.cola.popleft()
            self._entra(siguiente)
            return siguiente
        self.valor = min(1, self.valor + 1) if self.binario else self.valor + 1
        return None

    def a_dict(self) -> dict:
        return {"nombre": self.nombre, "valor": self.valor, "inicial": self.inicial,
                "tipo": "binario" if self.binario else "contador",
                "cola": [p.pid for p in self.cola], "titulares": sorted(self.titulares),
                "max_titulares": self.max_titulares, "ops_p": self.ops_p, "ops_v": self.ops_v}

class EntornoSync:
    def __init__(self):
        self.semaforos: Dict[str, Semaforo] = {}
        self.recursos: Dict[str, RecursoCompartido] = {}

    def crear_semaforo(self, nombre: str, valor: int = 1) -> Semaforo:
        self.semaforos[nombre] = Semaforo(nombre, valor)
        return self.semaforos[nombre]

    def crear_recurso(self, nombre: str, valor: int = 0) -> RecursoCompartido:
        self.recursos[nombre] = RecursoCompartido(nombre, valor)
        return self.recursos[nombre]