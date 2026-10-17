from backend.planificador import RoundRobin

rr = RoundRobin(quantum=4, costo_cambio_contexto=1)
rr.crear_proceso("systemd-journal", rafaga=9)
rr.crear_proceso("nginx", rafaga=8, eventos_es=[(2, "disco", 3)])
rr.crear_proceso("sshd", rafaga=5, prioridad=2, eventos_es=[(1, "disco", 2)])  # compite por el disco

while not rr.sin_trabajo() and rr.reloj < 200:
    rr.tick()

for e in rr.bitacora:
    print(f"t={e['t']:>2} [{e['tipo']:<8}] {e['msg']}")

print("\n--- Historial de transiciones de P2 (nginx) ---")
for h in rr.todos[2].historial:
    print(f"t={h['t']:>2}  {h['de']:<9} → {h['a']:<9}  {h['motivo']}")

print("\nTransiciones totales:", rr.conteo_transiciones())
print("Métricas:", rr.metricas())