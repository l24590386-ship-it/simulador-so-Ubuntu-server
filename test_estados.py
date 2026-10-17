import unittest
from backend.planificador import RoundRobin
from backend.modelos import Estado


class TestEstados(unittest.TestCase):
    def test_transicion_invalida(self):
        rr = RoundRobin(4)
        p = rr.crear_proceso("a", 5)
        with self.assertRaises(ValueError):
            p.cambiar_estado(Estado.BLOQUEADO)      # LISTO → BLOQUEADO no existe

    def test_bloqueo_y_regreso_por_irq(self):
        rr = RoundRobin(10, costo_cambio_contexto=0)
        p = rr.crear_proceso("a", 6, eventos_es=[(2, "disco", 3)])
        vistos = set()
        while not rr.sin_trabajo():
            rr.tick()
            vistos.add(p.estado)
        self.assertIn(Estado.BLOQUEADO, vistos)
        self.assertEqual(p.estado, Estado.ZOMBI)
        tipos = [i.tipo.value for i in rr.irq.historial]
        self.assertIn("ES_COMPLETA", tipos)
        # nunca saltó de BLOQUEADO directo a EJECUCION
        for h in p.historial:
            self.assertFalse(h["de"] == "BLOQUEADO" and h["a"] == "EJECUCION")

    def test_dispositivo_atiende_uno_a_la_vez(self):
        rr = RoundRobin(10, costo_cambio_contexto=0)
        rr.crear_proceso("a", 4, eventos_es=[(1, "disco", 5)])
        rr.crear_proceso("b", 4, eventos_es=[(1, "disco", 5)])
        for _ in range(4):
            rr.tick()
        d = rr.dispositivos["disco"]
        self.assertEqual(len(d.cola) + (1 if d.actual else 0), 2)

    def test_quantum_dispara_timer(self):
        rr = RoundRobin(2, costo_cambio_contexto=0)
        rr.crear_proceso("a", 10)
        rr.crear_proceso("b", 10)
        for _ in range(3):
            rr.tick()
        self.assertTrue(any(i.tipo.value == "TIMER" for i in rr.irq.historial))

    def test_forzar_fin_es(self):
        rr = RoundRobin(10, costo_cambio_contexto=0)
        p = rr.crear_proceso("a", 8, eventos_es=[(1, "red", 50)])
        rr.tick(); rr.tick()
        self.assertEqual(p.estado, Estado.BLOQUEADO)
        self.assertTrue(rr.forzar_fin_es(p.pid))
        self.assertEqual(p.estado, Estado.LISTO)


if __name__ == "__main__":
    unittest.main()