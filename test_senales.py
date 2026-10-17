import unittest
from backend.planificador import RoundRobin
from backend.modelos import Estado


class TestSenales(unittest.TestCase):
    def rr(self):
        return RoundRobin(10, costo_cambio_contexto=0)

    def test_stop_y_cont(self):
        rr = self.rr(); p = rr.crear_proceso("a", 20)
        rr.tick()                                   # P1 corriendo
        rr.enviar_senal(p.pid, "SIGSTOP")
        self.assertEqual(p.estado, Estado.DETENIDO)
        self.assertIsNone(rr.cpu)
        pc = p.pcb.pc
        for _ in range(3): rr.tick()
        self.assertEqual(p.pcb.pc, pc)              # detenido: no avanza
        rr.enviar_senal(p.pid, "SIGCONT")
        self.assertEqual(p.estado, Estado.LISTO)

    def test_kill_en_listo_es_zombi_y_wait_lo_elimina(self):
        rr = self.rr(); a = rr.crear_proceso("a", 20); b = rr.crear_proceso("b", 20)
        rr.tick()
        rr.enviar_senal(b.pid, "SIGKILL")
        self.assertEqual(b.estado, Estado.ZOMBI)
        self.assertEqual(b.codigo_salida, 137)
        self.assertIn(b, rr.terminados)
        rr.wait(b.pid)
        self.assertEqual(b.estado, Estado.MUERTO)
        self.assertNotIn(b, rr.terminados)
        with self.assertRaises(ValueError): rr.wait(b.pid)

    def test_estado_D_ignora_kill9_hasta_terminar_es(self):
        rr = self.rr(); p = rr.crear_proceso("a", 10, eventos_es=[(1, "disco", 4)])
        rr.tick()
        self.assertEqual(p.estado, Estado.BLOQUEADO)
        rr.enviar_senal(p.pid, "SIGKILL")
        self.assertEqual(p.estado, Estado.BLOQUEADO)  # sigue vivo
        for _ in range(6): rr.tick()
        self.assertEqual(p.estado, Estado.ZOMBI)      # murió al volver de la E/S
        self.assertEqual(p.codigo_salida, 137)

    def test_sigterm_en_detenido_queda_pendiente_sigkill_no(self):
        rr = self.rr(); p = rr.crear_proceso("a", 20); rr.tick()
        rr.enviar_senal(p.pid, "SIGSTOP"); rr.enviar_senal(p.pid, "SIGTERM")
        self.assertEqual(p.estado, Estado.DETENIDO)
        rr.enviar_senal(p.pid, "SIGCONT")             # entrega SIGTERM pendiente
        self.assertEqual(p.estado, Estado.ZOMBI)
        self.assertEqual(p.codigo_salida, 143)

    def test_matar_al_titular_libera_el_semaforo(self):
        rr = self.rr(); rr.crear_semaforo("m", 1); rr.crear_recurso("r", 0)
        prog = [("P", "m"), ("SUMAR", 1), ("SUMAR", 1), ("SUMAR", 1), ("V", "m")]
        a = rr.crear_proceso("a", programa=prog); b = rr.crear_proceso("b", programa=prog)
        rr.tick(); rr.tick()                          # a toma el mutex
        rr.enviar_senal(a.pid, "SIGKILL")
        self.assertEqual(rr.sync.semaforos["m"].titulares, set())
        for _ in range(12): rr.tick()
        self.assertEqual(b.estado, Estado.ZOMBI)      # b pudo entrar y terminó

    def test_zombi_no_recibe_senales(self):
        rr = self.rr(); p = rr.crear_proceso("a", 2)
        while not rr.sin_trabajo(): rr.tick()
        with self.assertRaises(ValueError): rr.enviar_senal(p.pid, "SIGKILL")


if __name__ == "__main__":
    unittest.main()
