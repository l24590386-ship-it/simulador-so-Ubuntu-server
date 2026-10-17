"""Máquina virtual: secuencia de arranque real que alimenta al kernel simulado."""

PASOS = [
    {"capa": "Hardware", "titulo": "La placa base despierta",
     "texto": "La fuente ATX entrega +12V/+5V/+3.3V y, al estabilizarse (señal Power Good), la placa libera el reset de la CPU.",
     "log": ["PSU: Power Good OK (+12V +5V +3.3V)", "Chipset: reset liberado, CPU en modo real"]},
    {"capa": "Hardware", "titulo": "Se alimentan los dispositivos",
     "texto": "RAM, discos y tarjetas reciben energía. Aún nadie los ha inicializado: el firmware lo hará a continuación.",
     "log": ["DIMM0: 16 GB DDR5 energizado", "nvme0n1: 512 GB detectado en PCIe", "enp0s3: enlace de red arriba"]},
    {"capa": "Firmware", "titulo": "POST (Power-On Self Test)",
     "texto": "El firmware prueba memoria, teclado y discos. Si algo falla emite pitidos (beep codes) y se detiene.",
     "log": ["POST: memoria 16384 MB ... OK", "POST: teclado ... OK", "POST: disco ... OK", "beep x1 (todo correcto)"]},
    {"capa": "Firmware", "titulo": "UEFI busca el arranque",
     "texto": "Recorre la boot sequence (disco, USB, red) hasta hallar un bootloader firmado en la partición EFI.",
     "log": ["UEFI: Boot0001 'ubuntu' -> \\EFI\\ubuntu\\shimx64.efi", "Secure Boot: firma válida"]},
    {"capa": "Bootloader", "titulo": "GRUB 2 carga el kernel",
     "texto": "GRUB localiza vmlinuz e initrd en /boot, los copia a RAM y salta al punto de entrada del kernel.",
     "log": ["GRUB 2.12: cargando /boot/vmlinuz-6.8.0-generic", "GRUB: cargando initrd.img-6.8.0-generic"]},
    {"capa": "Kernel", "titulo": "Kernel Linux 6.8 toma el control",
     "texto": "El kernel se descomprime, detecta CPU y RAM, monta el sistema raíz, activa el planificador y el timer, y lanza /sbin/init.",
     "log": ["Linux version 6.8.0-generic (x86_64)", "smpboot: 4 núcleos / 8 hilos detectados",
             "Memory: 16 GB disponibles", "sched: Round Robin, quantum=4 ticks",
             "timer: IRQ0 programada (interrupción de reloj)", "VFS: rootfs montado, ejecutando /sbin/init"]},
    {"capa": "Espacio de usuario", "titulo": "systemd (PID 1)",
     "texto": "El primer proceso de usuario. Nace aquí: ve al módulo Procesos y verás a systemd con PID 1 en la cola de listos.",
     "log": ["systemd 255 iniciado como PID 1", "sysinit.target alcanzado", "basic.target alcanzado"]},
    {"capa": "Espacio de usuario", "titulo": "Sistema listo",
     "texto": "multi-user.target levanta los servicios: cada uno es un proceso nuevo (PCB) que el planificador ya está repartiendo.",
     "log": ["Started nginx.service", "Started ssh.service", "Started mysql.service",
             "Started backup.service", "multi-user.target alcanzado", "ubuntu login:"]},
]


class Maquina:
    def __init__(self):
        self.apagar()

    def apagar(self):
        self.fase = "apagada"      # apagada | arrancando | encendida
        self.paso = 0              # pasos completados
        self.consola = []
        self._t = 0.0

    def siguiente(self, hook=None) -> bool:
        if self.fase == "encendida":
            return False
        self.fase = "arrancando"
        for linea in PASOS[self.paso]["log"]:
            self._t += 0.137
            self.consola.append(f"[{self._t:10.6f}] {linea}")
        self.paso += 1
        if hook:
            hook(self.paso)
        if self.paso == len(PASOS):
            self.fase = "encendida"
        return True

    def a_dict(self) -> dict:
        return {"fase": self.fase, "paso": self.paso, "total": len(PASOS),
                "pasos": PASOS, "consola": self.consola[-40:]}
