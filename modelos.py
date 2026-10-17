from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

class Estado(str, Enum):
    NUEVO = "NUEVO"
    LISTO = "LISTO"
    EJECUCION = "EJECUCION"
    BLOQUEADO = "BLOQUEADO"
    DETENIDO = "DETENIDO"      # T: SIGSTOP / Ctrl+Z
    ZOMBI = "ZOMBI"            # Z: terminó, el padre aún no hizo wait()
    MUERTO = "MUERTO"          # X: borrado de la tabla de procesos

# Letra que muestran ps/top para cada estado (R agrupa LISTO y EJECUCION; S/D dependen de qué espera)

TRANSICIONES = {
    Estado.NUEVO: {Estado.LISTO},
    Estado.LISTO: {Estado.EJECUCION, Estado.DETENIDO, Estado.ZOMBI},
    Estado.EJECUCION: {Estado.LISTO, Estado.BLOQUEADO, Estado.DETENIDO, Estado.ZOMBI},
    Estado.BLOQUEADO: {Estado.LISTO, Estado.ZOMBI},
    Estado.DETENIDO: {Estado.LISTO, Estado.ZOMBI},
    Estado.ZOMBI: {Estado.MUERTO},
    Estado.MUERTO: set(),
}

@dataclass
class PCB:
    pid: int
    nombre: str
    estado: Estado = Estado.NUEVO
    pc: int = 0
    registros: Dict[str, int] = field(default_factory=lambda: {"AX": 0, "BX": 0, "CX": 0, "DX": 0})
    prioridad: int = 5
    ppid: int = 0
    memoria_kb: int = 0
    recursos: List[str] = field(default_factory=list)

    def a_dict(self) -> dict:
        return {
            "pid": self.pid, "nombre": self.nombre, "estado": self.estado.value,
            "pc": self.pc, "registros": dict(self.registros),
            "prioridad": self.prioridad, "ppid": self.ppid, "memoria_kb": self.memoria_kb,
            "recursos": list(self.recursos),
        }

class Proceso:
    def __init__(self, pid: int, nombre: str, rafaga: int = 0, prioridad: int = 5,
                 memoria_kb: int = 64, eventos_es: List[Tuple[int, int]] = None,
                 llegada: int = 0, programa: list = None, ppid: int = 0):
        self.programa = list(programa) if programa else None
        if self.programa:
            rafaga = len(self.programa)
        self.esperando_semaforo: Optional[str] = None
        self.sem_objetivo: Optional[str] = None
        self.incidente: Optional[str] = None
        self.ultima_instruccion = ""
        self._valor_leido = 0
        self._version_leida = 0
        self.pcb = PCB(pid, nombre, prioridad=prioridad, memoria_kb=memoria_kb, ppid=ppid)
        self.senales_pendientes: List[str] = []
        self.codigo_salida: Optional[int] = None
        self.rafaga = rafaga
        self.eventos_es = sorted(self._normalizar(e) for e in (eventos_es or []))
        self.solicitud_es: Optional[Tuple[str, int]] = None
        self.dispositivo_espera: Optional[str] = None
        self.historial: List[dict] = []
        self.llegada = llegada
        self.t_espera = 0
        self.t_cpu = 0
        self.t_finalizacion = None

    @property
    def pid(self): return self.pcb.pid
    @property
    def estado(self): return self.pcb.estado
    @property
    def restante(self): return self.rafaga - self.pcb.pc

    def cambiar_estado(self, nuevo: Estado, t: int = 0, motivo: str = ""):
        actual = self.pcb.estado
        if nuevo not in TRANSICIONES[actual]:
            raise ValueError(f"Transición inválida en P{self.pid}: {actual.value} → {nuevo.value}")
        self.historial.append({"t": t, "de": actual.value, "a": nuevo.value, "motivo": motivo})
        self.pcb.estado = nuevo

    @staticmethod
    def _normalizar(e):
        return (e[0], "disco", e[1]) if len(e) == 2 else (e[0], e[1], e[2])

    @staticmethod
    def _fmt(ins) -> str:
        return ins[0] if len(ins) == 1 else f"{ins[0]}({ins[1]})"

    def ejecutar_instruccion(self, sync=None) -> str:
        pc = self.pcb.pc
        r = self.pcb.registros
        codigo = "ok"
        self.incidente = None
        if self.programa:
            ins = self.programa[pc]
            op = ins[0]
            self.ultima_instruccion = self._fmt(ins)
            if op == "LEER":
                rec = sync.recursos[ins[1]]
                r["AX"] = rec.leer(self.pid)
                self._valor_leido, self._version_leida = r["AX"], rec.version
            elif op == "SUMAR":
                r["AX"] += ins[1]
            elif op == "ESCRIBIR":
                rec = sync.recursos[ins[1]]
                if rec.escribir(self.pid, r["AX"], r["AX"] - self._valor_leido, self._version_leida):
                    self.incidente = f"CONDICIÓN DE CARRERA en '{rec.nombre}': escribió {r['AX']} con un valor desactualizado"
            elif op in ("P", "V"):
                codigo = op
                self.sem_objetivo = ins[1]
            r["CX"] = pc
        else:
            r["AX"] = (r["AX"] + pc) % 256
            r["BX"] = (r["BX"] * 3 + 1) % 256
            r["CX"] = pc % 16
            r["DX"] = (r["AX"] ^ r["BX"]) % 256

        self.pcb.pc += 1
        self.t_cpu += 1

        if codigo in ("P", "V"):
            return codigo
        if self.pcb.pc >= self.rafaga:
            return "fin"
        for (pc_es, disp, dur) in self.eventos_es:
            if pc_es == self.pcb.pc:
                self.solicitud_es = (disp, dur)
                return "es"
        return "ok"

    def a_dict(self) -> dict:
        d = self.pcb.a_dict()
        d.update(rafaga=self.rafaga, restante=self.restante, llegada=self.llegada,
                 t_espera=self.t_espera, t_cpu=self.t_cpu,
                 t_finalizacion=self.t_finalizacion, historial=self.historial[-10:], senales_pendientes=list(self.senales_pendientes),
                 codigo_salida=self.codigo_salida,
                 dispositivo_espera=self.dispositivo_espera,
                 esperando_semaforo=self.esperando_semaforo,
                 ultima_instruccion=self.ultima_instruccion,
                 instruccion_siguiente=(self._fmt(self.programa[self.pcb.pc])
                                        if self.programa and self.pcb.pc < len(self.programa) else None))
        return d