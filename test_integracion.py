import unittest
from app import app


class TestIntegracion(unittest.TestCase):
    def setUp(self):
        self.c = app.test_client()
        self.c.post("/api/apagar")

    def arrancar(self):
        for _ in range(8):
            d = self.c.post("/api/arranque/siguiente").get_json()
        return d

    def test_sin_arranque_no_hay_ticks_ni_procesos(self):
        self.assertEqual(self.c.post("/api/tick").status_code, 409)
        self.assertEqual(self.c.get("/api/estado").get_json()["todos"], [])

    def test_arranque_crea_systemd_como_pid_1(self):
        for _ in range(6):
            d = self.c.post("/api/arranque/siguiente").get_json()
        self.assertEqual(d["todos"], [])                      # kernel sin systemd aún
        d = self.c.post("/api/arranque/siguiente").get_json()  # paso 7
        self.assertEqual([(p["pid"], p["nombre"]) for p in d["todos"]], [(1, "systemd")])
        d = self.c.post("/api/arranque/siguiente").get_json()  # paso 8
        self.assertEqual(d["maquina"]["fase"], "encendida")
        self.assertEqual(len(d["todos"]), 5)

    def test_carrera_sin_mutex_y_sin_carrera_con_mutex(self):
        self.arrancar()
        self.c.post("/api/demo/carrera")
        for _ in range(80):
            d = self.c.post("/api/tick").get_json()
        self.assertGreaterEqual(d["recursos"][0]["perdidas"], 1)
        perdidas = d["recursos"][0]["perdidas"]
        self.c.post("/api/demo/mutex")
        for _ in range(80):
            d = self.c.post("/api/tick").get_json()
        self.assertEqual(d["recursos"][0]["perdidas"], perdidas)

    def test_validaciones(self):
        self.arrancar()
        self.assertEqual(self.c.post("/api/proceso", json={"rafaga": 999}).status_code, 400)
        self.assertEqual(self.c.post("/api/es/1/forzar").status_code, 400)


if __name__ == "__main__":
    unittest.main()


class TestSenalesAPI(unittest.TestCase):
    def setUp(self):
        self.c = app.test_client()
        self.c.post("/api/apagar")
        for _ in range(8):
            self.c.post("/api/arranque/siguiente")

    def test_kill_zombi_wait(self):
        d = self.c.post("/api/senal/2/kill").get_json()
        self.assertIn("zombi", d["mensaje"])
        self.assertEqual([p["pid"] for p in d["terminados"]], [2])
        self.assertEqual(d["terminados"][0]["ppid"], 1)       # hijo de systemd
        d = self.c.post("/api/wait/2").get_json()
        self.assertEqual((d["terminados"], d["muertos"]), ([], 1))
        self.assertEqual(self.c.post("/api/wait/2").status_code, 400)

    def test_stop_cont(self):
        d = self.c.post("/api/senal/3/stop").get_json()
        self.assertEqual([p["pid"] for p in d["detenidos"]], [3])
        d = self.c.post("/api/senal/3/cont").get_json()
        self.assertEqual(d["detenidos"], [])
        self.assertEqual(self.c.post("/api/senal/3/xx").status_code, 400)
