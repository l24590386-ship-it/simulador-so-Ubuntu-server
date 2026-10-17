
from collections import deque, Counter
from typing import Deque, Dict, List, Optional
from .modelos import Proceso, Estado
from .concurrencia import EntornoSync
from .interrupciones import ControladorInterrupciones, Dispositivo, Interrupcion, TipoInterrupcion as TI

DISPOSITIVOS_BASE = ("disco", "red", "teclado", "impresora")

class Planificador:
    def __init__(self, costo_cambio_contexto: int = 1):
        self.reloj = 0
        self.costo_cc = costo_cambio_contexto
        self.cola_listos: Deque[Proceso] = deque()
        self.bloqueados: List[Proceso] = []
        self.terminados: List[Proceso] = []   # zombis (aún sin wait() del padre)
        self.detenidos: List[Proceso] = []
        self.finalizados: List[Proceso] = []  # todos los que terminaron (para métricas)
        self.muertos = 0
        self.cpu: Optional[Proceso] = None
        self.todos: Dict[int, Proceso] = {}
        self.dispositivos = {n: Dispositivo(n) for n in DISPOSITIVOS_BASE}
        self.sync = EntornoSync()
        self.trazar = False
        self.irq = ControladorInterrupciones()
        self.irq.registrar(TI.ES_COMPLETA, self._manejador_es)
        self.irq.registrar(TI.LLAMADA_SISTEMA, self._manejador_syscall)
        self.irq.registrar(TI.TIMER, self._manejador_timer)
        self.cambios_contexto = 0
        self.ticks_utiles = 0
        self.ticks_cc = 0
        self._cc_restante = 0
        self.bitacora: List[dict] = []
        self._siguiente_pid = 1
        self._pendientes: List[Proceso] = []
        self.linea: List[dict] = []

    def _log(self, tipo: str, msg: str, pid: int = None):
        self.bitacora.append({"t": self.reloj, "tipo": tipo, "pid": pid, "msg": msg})

    def _mover(self, p: Proceso, nuevo: Estado, motivo: str):
        p.cambiar_estado(nuevo, self.reloj, motivo)

    def crear_semaforo(self, nombre: str, valor: int = 1):
        return self.sync.crear_semaforo(nombre, valor)

    def crear_recurso(self, nombre: str, valor: int = 0):
        return self.sync.crear_recurso(nombre, valor)

    def crear_proceso(self, nombre: str, rafaga: int = 0, prioridad: int = 5,
                      memoria_kb: int = 64, eventos_es=None, llegada: int = None,
                      programa=None, ppid: int = None) -> Proceso:
        llegada = self.reloj if llegada is None else llegada
        for ins in (programa or []):
            if ins[0] in ("P", "V") and ins[1] not in self.sync.semaforos:
                raise ValueError(f"Semáforo desconocido: {ins[1]}")
            if ins[0] in ("LEER", "ESCRIBIR") and ins[1] not in self.sync.recursos:
                raise ValueError(f"Recurso compartido desconocido: {ins[1]}")
        p = Proceso(self._siguiente_pid, nombre, rafaga, prioridad,
                    memoria_kb, eventos_es, llegada, programa,
                    ppid if ppid is not None else (0 if self._siguiente_pid == 1 else 1))
        for (_, disp, _) in p.eventos_es:
            if disp not in self.dispositivos:
                raise ValueError(f"Dispositivo desconocido: {disp}")
        self._siguiente_pid += 1
        self.todos[p.pid] = p
        self._log("CREAR", f"P{p.pid} '{nombre}' creado (ráfaga={rafaga})", p.pid)
        if llegada <= self.reloj:
            self._admitir(p)
        else:
            self._pendientes.append(p)
        return p

    def _admitir(self, p: Proceso):
        self._mover(p, Estado.LISTO, "admitido por el SO")
        self.cola_listos.append(p)
        self._log("ADMITIR", f"P{p.pid} entra a la cola de listos", p.pid)

    def seleccionar_siguiente(self) -> Optional[Proceso]:
        return self.cola_listos.popleft() if self.cola_listos else None

    def debe_expulsar(self) -> bool:
        return False

    def _on_despacho(self, p: Proceso):
        pass

    def _despachar(self):
        p = self.seleccionar_siguiente()
        if p is None:
            return
        self._mover(p, Estado.EJECUCION, "elegido por el planificador")
        self.cpu = p
        self.cambios_contexto += 1
        self._cc_restante = self.costo_cc
        self._on_despacho(p)
        self._log("DESPACHO", f"Cambio de contexto: P{p.pid} recibe el CPU (PC={p.pcb.pc})", p.pid)

    def _liberar_cpu(self, nuevo: Estado, motivo: str, tipo: str) -> Proceso:
        p = self.cpu
        self._mover(p, nuevo, motivo)
        self.cpu = None
        self._log(tipo, f"P{p.pid}: {motivo} (PCB guardado: PC={p.pcb.pc})", p.pid)
        return p

    def _manejador_syscall(self, irq: Interrupcion):
        p = self.cpu
        if irq.servicio in ("P", "V"):
            return self._operacion_semaforo(irq)
        if irq.servicio == "exit":
            p.t_finalizacion = self.reloj + 1
            self._liberar_cpu(Estado.ZOMBI, "exit(): terminó → ZOMBI (espera wait() del padre)", "FIN")
            p.codigo_salida = 0
            self._registrar_fin(p)
        else:
            disp, dur = p.solicitud_es
            p.solicitud_es = None
            p.dispositivo_espera = disp
            self._liberar_cpu(Estado.BLOQUEADO, f"pidió E/S a '{disp}' ({dur} ticks) → BLOQUEADO", "BLOQUEO")
            self.bloqueados.append(p)
            self.dispositivos[disp].solicitar(p, dur)

    def _operacion_semaforo(self, irq: Interrupcion):
        p = self.cpu
        sem = self.sync.semaforos[irq.semaforo]
        if irq.servicio == "P":
            if sem.P(p):
                self._log("SEM P", f"P{p.pid} hace P({sem.nombre}) → valor={sem.valor}: ENTRA a sección crítica", p.pid)
            else:
                p.esperando_semaforo = sem.nombre
                self._liberar_cpu(Estado.BLOQUEADO, f"hizo P({sem.nombre}) con valor 0 → BLOQUEADO", "SEM P")
                self.bloqueados.append(p)
        else:
            sig = sem.V(p)
            msg = f"P{p.pid} hace V({sem.nombre}) → SALE de sección crítica"
            msg += (f"; despierta a P{sig.pid}" if sig else f"; valor={sem.valor}")
            self._log("SEM V", msg, p.pid)
            if sig:
                self._despertar_de_semaforo(sig, sem)

    def _manejador_es(self, irq: Interrupcion):
        p = self.todos[irq.pid]
        self.bloqueados.remove(p)
        p.dispositivo_espera = None
        self._mover(p, Estado.LISTO, f"IRQ de '{irq.dispositivo}': E/S completada")
        self.cola_listos.append(p)
        self._log("E/S OK", f"P{p.pid}: '{irq.dispositivo}' terminó → LISTO", p.pid)
        self._entregar_pendientes(p)

    def _manejador_timer(self, irq: Interrupcion):
        p = self._liberar_cpu(Estado.LISTO, "agotó su quantum → LISTO", "QUANTUM")
        self.cola_listos.append(p)

    def tick(self):
        for p in [x for x in self._pendientes if x.llegada <= self.reloj]:
            self._pendientes.remove(p)
            self._admitir(p)

        for d in self.dispositivos.values():
            terminado = d.tick()
            if terminado:
                self.irq.levantar(Interrupcion(TI.ES_COMPLETA, self.reloj, "hardware", terminado.pid, d.nombre))
        self.irq.atender(self._log)

        if self.cpu is None:
            self._despachar()

        slot = {"t": self.reloj, "k": "idle", "pid": None}
        if self.cpu is not None:
            if self._cc_restante > 0:
                self._cc_restante -= 1
                self.ticks_cc += 1
                slot.update(k="cc", pid=self.cpu.pid)
            else:
                self.ticks_utiles += 1
                cur = self.cpu
                slot.update(k="ej", pid=cur.pid)
                res = cur.ejecutar_instruccion(self.sync)
                if cur.incidente:
                    self._log("CARRERA", f"P{cur.pid}: {cur.incidente}", cur.pid)
                if res == "fin":
                    self.irq.levantar(Interrupcion(TI.LLAMADA_SISTEMA, self.reloj, "software", cur.pid, servicio="exit"))
                elif res == "es":
                    self.irq.levantar(Interrupcion(TI.LLAMADA_SISTEMA, self.reloj, "software", cur.pid, cur.solicitud_es[0], "E/S"))
                elif res in ("P", "V"):
                    self.irq.levantar(Interrupcion(TI.LLAMADA_SISTEMA, self.reloj, "software", cur.pid, servicio=res, semaforo=cur.sem_objetivo))
                    self.irq.atender(self._log)
                    if self.cpu is cur:
                        if cur.restante <= 0:
                            self.irq.levantar(Interrupcion(TI.LLAMADA_SISTEMA, self.reloj, "software", cur.pid, servicio="exit"))
                        elif self.debe_expulsar():
                            self.irq.levantar(Interrupcion(TI.TIMER, self.reloj, "hardware", cur.pid))
                elif self.debe_expulsar():
                    self.irq.levantar(Interrupcion(TI.TIMER, self.reloj, "hardware", cur.pid))
                self.irq.atender(self._log)

        for p in self.cola_listos:
            p.t_espera += 1
        self.linea.append(slot)
        self.reloj += 1

    def forzar_fin_es(self, pid: int) -> bool:
        """Simula que el dispositivo termina YA: levanta la IRQ de E/S completa."""
        p = self.todos.get(pid)
        if not p or p.estado != Estado.BLOQUEADO or not p.dispositivo_espera:
            return False
        disp = self.dispositivos[p.dispositivo_espera]
        disp.cancelar(p)
        self.irq.levantar(Interrupcion(TI.ES_COMPLETA, self.reloj, "hardware", p.pid, disp.nombre))
        self.irq.atender(self._log)
        return True


    # ------------------------------------------------------------------
    # Señales (kill / Ctrl+Z) y ciclo Z → X
    # ------------------------------------------------------------------
    SENALES = {"stop": "SIGSTOP", "cont": "SIGCONT", "term": "SIGTERM", "kill": "SIGKILL"}

    def _registrar_fin(self, p: Proceso):
        if p.t_finalizacion is None:
            p.t_finalizacion = self.reloj
        self.terminados.append(p)
        self.finalizados.append(p)

    def _despertar_de_semaforo(self, p: Proceso, sem):
        self.bloqueados.remove(p)
        p.esperando_semaforo = None
        self._mover(p, Estado.LISTO, f"V({sem.nombre}): se le concede la sección crítica")
        self.cola_listos.append(p)
        self._entregar_pendientes(p)

    def _liberar_semaforos(self, p: Proceso):
        """Un proceso muerto que tenía un semáforo lo dejaría tomado para siempre: el SO lo libera."""
        for sem in self.sync.semaforos.values():
            if p.pid in sem.titulares:
                sig = sem.V(p)
                self._log("SEM V", f"SO libera '{sem.nombre}' que retenía P{p.pid} (ya murió)", p.pid)
                if sig:
                    self._despertar_de_semaforo(sig, sem)

    def _entregar_pendientes(self, p: Proceso):
        pend, p.senales_pendientes = p.senales_pendientes, []
        for sig in pend:
            if p.estado in (Estado.ZOMBI, Estado.MUERTO):
                break
            self._log("SEÑAL", f"P{p.pid}: se entrega la {sig} que estaba pendiente", p.pid)
            self._aplicar_senal(p, sig)

    def enviar_senal(self, pid: int, sig: str) -> str:
        """Devuelve un mensaje explicativo. Lanza ValueError si no tiene sentido."""
        p = self.todos.get(pid)
        if p is None:
            raise ValueError(f"No existe el proceso {pid}")
        if p.estado in (Estado.ZOMBI, Estado.MUERTO):
            raise ValueError(f"P{pid} ya terminó: un zombi no puede recibir señales, solo wait() de su padre")
        if p.estado == Estado.BLOQUEADO and p.dispositivo_espera:
            p.senales_pendientes.append(sig)
            self._log("SEÑAL", f"{sig} → P{pid} en estado D (E/S de '{p.dispositivo_espera}'): NO se puede interrumpir, queda PENDIENTE", pid)
            return f"{sig} queda pendiente: P{pid} está en D (ininterrumpible) hasta que termine la E/S, ni kill -9 lo evita"
        self._log("SEÑAL", f"{sig} → P{pid}", pid)
        return self._aplicar_senal(p, sig) or f"{sig} enviada a P{pid}"

    def _aplicar_senal(self, p: Proceso, sig: str):
        if sig == "SIGCONT":
            if p.estado != Estado.DETENIDO:
                return f"P{p.pid} no estaba detenido: SIGCONT sin efecto"
            self.detenidos.remove(p)
            self._mover(p, Estado.LISTO, "SIGCONT: reanuda")
            self.cola_listos.append(p)
            self._entregar_pendientes(p)
            return f"P{p.pid} T → R: vuelve a la cola de listos"
        if sig == "SIGSTOP":
            if p.estado == Estado.DETENIDO:
                return f"P{p.pid} ya estaba detenido"
            if p.estado == Estado.BLOQUEADO:           # S (semáforo): se detiene al despertar
                p.senales_pendientes.append(sig)
                return "SIGSTOP pendiente: se aplicará cuando P despierte"
            if p.estado == Estado.EJECUCION:
                self._liberar_cpu(Estado.DETENIDO, "SIGSTOP (Ctrl+Z): detenido → T", "SEÑAL")
            else:
                self.cola_listos.remove(p)
                self._mover(p, Estado.DETENIDO, "SIGSTOP (Ctrl+Z): detenido → T")
            self.detenidos.append(p)
            return f"P{p.pid} R → T: sale de la cola de listos y no recibe CPU hasta SIGCONT"
        # SIGTERM / SIGKILL
        if p.estado == Estado.DETENIDO and sig == "SIGTERM":
            p.senales_pendientes.append(sig)
            return "SIGTERM queda pendiente: un proceso detenido solo la recibe tras SIGCONT (usa SIGKILL)"
        self._matar(p, 137 if sig == "SIGKILL" else 143, sig)
        return f"P{p.pid} → Z (zombi): murió por {sig}; espera wait() de su padre P{p.pcb.ppid}"

    def _matar(self, p: Proceso, codigo: int, sig: str):
        motivo = f"{sig}: terminado → ZOMBI"
        if p.estado == Estado.EJECUCION:
            self._liberar_cpu(Estado.ZOMBI, motivo, "FIN")
        elif p.estado == Estado.LISTO:
            self.cola_listos.remove(p)
            self._mover(p, Estado.ZOMBI, motivo)
        elif p.estado == Estado.DETENIDO:
            self.detenidos.remove(p)
            self._mover(p, Estado.ZOMBI, motivo)
        elif p.estado == Estado.BLOQUEADO:          # S (semáforo): interrumpible
            sem = self.sync.semaforos[p.esperando_semaforo]
            sem.cola.remove(p)
            self.bloqueados.remove(p)
            p.esperando_semaforo = None
            self._mover(p, Estado.ZOMBI, motivo)
        p.codigo_salida = codigo
        p.senales_pendientes = []
        self._registrar_fin(p)
        self._log("FIN", f"P{p.pid} '{p.pcb.nombre}' murió por {sig} (código de salida {codigo})", p.pid)
        self._liberar_semaforos(p)

    def wait(self, pid: int) -> str:
        """El padre recoge el estado de salida: Z → X y la entrada desaparece de la tabla."""
        p = self.todos.get(pid)
        if p is None or p.estado != Estado.ZOMBI:
            raise ValueError(f"P{pid} no es un zombi: wait() no tiene nada que recoger")
        self.terminados.remove(p)
        self._mover(p, Estado.MUERTO, f"wait() del padre P{p.pcb.ppid}: estado de salida recogido")
        self.muertos += 1
        self._log("WAIT", f"P{p.pcb.ppid} hace wait(): recoge salida={p.codigo_salida} de P{pid} → X, se borra de la tabla", pid)
        return f"wait(): P{pid} Z → X, eliminado de la tabla de procesos"

    def wait_todos(self) -> int:
        zs = list(self.terminados)
        for p in zs:
            self.wait(p.pid)
        return len(zs)

    def sin_trabajo(self) -> bool:
        return not (self.cpu or self.cola_listos or self.bloqueados or self.detenidos or self._pendientes)

    def conteo_transiciones(self) -> dict:
        c = Counter()
        for p in self.todos.values():
            for h in p.historial:
                c[f"{h['de']}→{h['a']}"] += 1
        return dict(c)

    def metricas(self) -> dict:
        n = len(self.finalizados)
        r = self.reloj or 1
        return {
            "cambios_contexto": self.cambios_contexto,
            "uso_cpu_pct": round(100 * self.ticks_utiles / r, 1),
            "sobrecarga_cc_pct": round(100 * self.ticks_cc / r, 1),
            "ocioso_pct": round(100 * (r - self.ticks_utiles - self.ticks_cc) / r, 1),
            "interrupciones": len(self.irq.historial),
            "espera_promedio": round(sum(p.t_espera for p in self.finalizados) / n, 2) if n else 0,
            "retorno_promedio": round(sum(p.t_finalizacion - p.llegada for p in self.finalizados) / n, 2) if n else 0,
        }

    def estado_actual(self) -> dict:
        return {
            "reloj": self.reloj,
            "algoritmo": self.__class__.__name__,
            "cpu": self.cpu.a_dict() if self.cpu else None,
            "cola_listos": [p.a_dict() for p in self.cola_listos],
            "bloqueados": [p.a_dict() for p in self.bloqueados],
            "terminados": [p.a_dict() for p in self.terminados],   # zombis
            "detenidos": [p.a_dict() for p in self.detenidos],
            "muertos": self.muertos,
            "todos": [p.a_dict() for p in self.todos.values()],  # ← AÑADIDO PARA EL FRONTEND
            "dispositivos": [d.a_dict() for d in self.dispositivos.values()],
            "interrupciones": [i.a_dict() for i in self.irq.historial[-15:]],
            "transiciones": self.conteo_transiciones(),
            "semaforos": [s.a_dict() for s in self.sync.semaforos.values()],
            "recursos": [r.a_dict() for r in self.sync.recursos.values()],
            "metricas": self.metricas(),
            "bitacora": self.bitacora[-40:],
            "linea": self.linea[-60:],
        }


class RoundRobin(Planificador):
    def __init__(self, quantum: int = 4, costo_cambio_contexto: int = 1):
        super().__init__(costo_cambio_contexto)
        self.quantum = quantum
        self._uso_quantum = 0

    def _on_despacho(self, p):
        self._uso_quantum = 0

    def debe_expulsar(self) -> bool:
        self._uso_quantum += 1
        return self._uso_quantum >= self.quantum

    def estado_actual(self) -> dict:
        d = super().estado_actual()
        d["quantum"] = self.quantum
        d["quantum_usado"] = self._uso_quantum if self.cpu else 0
        return d