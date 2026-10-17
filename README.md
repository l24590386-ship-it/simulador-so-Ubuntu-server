# Laboratorio SO · Ubuntu Server 24.04 LTS

Un solo sistema simulado, tres vistas conectadas:

    01 Arranque ──► crea el kernel, systemd (PID 1) y los servicios
    02 Procesador ─► ejecuta las instrucciones REALES del proceso que eligió el planificador
    03 Procesos ───► PCB, estados, Round Robin, IRQ, semáforos, top

## Ejecutar
    pip install flask
    python app.py          # http://127.0.0.1:5000
    python demo_consola.py # versión sin web
    python -m unittest discover -p "test_*.py"

## Estados de proceso (los de Linux)
    R  LISTO + EJECUCION      T  DETENIDO  (Ctrl+Z / SIGSTOP → SIGCONT)
    S  BLOQUEADO (semáforo)   Z  ZOMBI     (terminó; espera wait() del padre)
    D  BLOQUEADO (E/S, ignora señales)   X  MUERTO (wait() lo borra de la tabla)

## Estructura
    app.py                  rutas + API (estado único compartido)
    backend/arranque.py     máquina: pasos de boot, consola dmesg
    backend/planificador.py Round Robin, E/S, interrupciones
    backend/modelos.py      PCB, estados y transiciones válidas
    backend/concurrencia.py semáforos y recursos compartidos
    templates/ static/      base.html + 3 módulos + lab.css / lab.js
