from flask import Flask, render_template, jsonify, request
from backend.planificador import RoundRobin
from backend.arranque import Maquina

app = Flask(__name__)
maquina = Maquina()
rr = None

SERVICIOS = [
    dict(nombre="nginx", rafaga=10, prioridad=3, eventos_es=[(2, "red", 3), (6, "disco", 4)]),
    dict(nombre="sshd", rafaga=7, prioridad=2, eventos_es=[(1, "teclado", 5)]),
    dict(nombre="mysql-db", rafaga=15, prioridad=2, eventos_es=[(3, "disco", 6)]),
    dict(nombre="backup-job", rafaga=14, prioridad=5, eventos_es=[(4, "impresora", 8)]),
]


def nuevo_kernel():
    """Un kernel vacío: así está el sistema justo después de encender, antes de systemd."""
    global rr
    rr = RoundRobin(quantum=4, costo_cambio_contexto=1)
    rr.crear_semaforo("mutex_bd", 1)
    rr.crear_recurso("conexiones_activas", 5)


def hook_arranque(paso: int):
    """El arranque es lo que crea los procesos: paso 7 → systemd (PID 1), paso 8 → servicios."""
    if paso == 7:
        rr.crear_proceso("systemd", rafaga=12, prioridad=1)
    elif paso == 8:
        for s in SERVICIOS:
            rr.crear_proceso(**s)


def snapshot():
    d = rr.estado_actual()
    d["maquina"] = maquina.a_dict()
    return d


def error(msg, code=409):
    return jsonify(error=msg), code


def apagada():
    return maquina.fase != "encendida"


nuevo_kernel()


# ---------- Páginas ----------
@app.route("/")
def index():
    return render_template("index.html", page="procesos")

@app.route("/arranque")
def arranque():
    return render_template("arranque.html", page="arranque")

@app.route("/procesador")
def procesador():
    return render_template("procesador.html", page="cpu")


# ---------- API ----------
@app.route("/api/estado")
def estado():
    return jsonify(snapshot())

@app.route("/api/arranque/siguiente", methods=["POST"])
def arranque_siguiente():
    maquina.siguiente(hook_arranque)
    return jsonify(snapshot())

@app.route("/api/apagar", methods=["POST"])
def apagar():
    maquina.apagar()
    nuevo_kernel()
    return jsonify(snapshot())

@app.route("/api/tick", methods=["POST"])
def tick():
    if apagada():
        return error("La máquina aún no terminó de arrancar. Ve a «01 · Arranque».")
    if not rr.sin_trabajo():
        rr.tick()
    return jsonify(snapshot())

@app.route("/api/reiniciar", methods=["POST"])
def reiniciar():
    """Reinicia solo el kernel (procesos y reloj), la máquina sigue encendida."""
    if apagada():
        return error("La máquina está apagada.")
    nuevo_kernel()
    hook_arranque(7)
    hook_arranque(8)
    return jsonify(snapshot())

@app.route("/api/proceso", methods=["POST"])
def crear_proceso():
    if apagada():
        return error("Enciende la máquina primero.")
    j = request.get_json(silent=True) or {}
    try:
        nombre = (str(j.get("nombre", "")).strip() or "proceso")[:18]
        rafaga = int(j.get("rafaga", 8))
        prioridad = int(j.get("prioridad", 5))
        if not 2 <= rafaga <= 60:
            return error("La ráfaga debe estar entre 2 y 60.", 400)
        io = []
        if j.get("io"):
            pc, disp, dur = int(j["io"]["pc"]), j["io"]["disp"], int(j["io"]["dur"])
            if not 1 <= pc < rafaga:
                return error("La E/S debe ocurrir en una instrucción entre 1 y ráfaga-1.", 400)
            io = [(pc, disp, max(1, min(dur, 30)))]
        rr.crear_proceso(nombre, rafaga=rafaga, prioridad=prioridad, eventos_es=io)
    except (ValueError, KeyError, TypeError) as e:
        return error(str(e), 400)
    return jsonify(snapshot())

@app.route("/api/es/<int:pid>/forzar", methods=["POST"])
def forzar_es(pid):
    if apagada():
        return error("La máquina está apagada.")
    if not rr.forzar_fin_es(pid):
        return error(f"P{pid} no está bloqueado esperando un dispositivo.", 400)
    return jsonify(snapshot())

@app.route("/api/senal/<int:pid>/<sig>", methods=["POST"])
def senal(pid, sig):
    """kill / Ctrl+Z: stop, cont, term, kill."""
    if apagada():
        return error("La máquina está apagada.")
    if sig not in rr.SENALES:
        return error("Señal desconocida.", 400)
    try:
        msg = rr.enviar_senal(pid, rr.SENALES[sig])
    except ValueError as e:
        return error(str(e), 400)
    return jsonify({**snapshot(), "mensaje": msg})

@app.route("/api/wait", methods=["POST"])
@app.route("/api/wait/<int:pid>", methods=["POST"])
def wait(pid=None):
    """El padre recoge a sus zombis (Z → X)."""
    if apagada():
        return error("La máquina está apagada.")
    try:
        msg = rr.wait(pid) if pid else f"wait(): {rr.wait_todos()} zombi(s) eliminados de la tabla"
    except ValueError as e:
        return error(str(e), 400)
    return jsonify({**snapshot(), "mensaje": msg})

@app.route("/api/demo/<tipo>", methods=["POST"])
def demo(tipo):
    """Dos procesos que incrementan un contador compartido: sin semáforo hay carrera, con mutex no."""
    if apagada():
        return error("Enciende la máquina primero.")
    r = "conexiones_activas"
    if tipo == "carrera":
        prog = [("LEER", r), ("SUMAR", 1), ("SUMAR", 0), ("SUMAR", 0), ("ESCRIBIR", r)]
    elif tipo == "mutex":
        prog = [("P", "mutex_bd"), ("LEER", r), ("SUMAR", 1), ("SUMAR", 0), ("ESCRIBIR", r), ("V", "mutex_bd")]
    else:
        return error("Demo desconocida.", 404)
    for n in ("A", "B"):
        rr.crear_proceso(f"{tipo}-{n}", prioridad=4, programa=prog)
    return jsonify(snapshot())


if __name__ == "__main__":
    print("Laboratorio SO en http://127.0.0.1:5000")
    app.run(debug=True, port=5000)
