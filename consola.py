import os
import sys
import shutil
import time


def _preparar_consola():
    if sys.platform == "win32":
        os.system("")
        try:
            import ctypes
            k = ctypes.windll.kernel32
            k.SetConsoleMode(k.GetStdHandle(-11), 7)
        except Exception:
            pass
    for flujo in (sys.stdout, sys.stderr):
        try:
            flujo.reconfigure(encoding="utf-8")
        except Exception:
            pass


_preparar_consola()


def _consola_soporta_unicode():
    enc = (getattr(sys.stdout, "encoding", None) or "ascii").lower()
    if "utf" in enc:
        return True
    try:
        "─│┌┐└┘✓·≈".encode(enc)
        return True
    except Exception:
        return False


UNICODE = _consola_soporta_unicode()
INTERACTIVO = sys.stdout.isatty()
COLOR = INTERACTIVO and os.environ.get("NO_COLOR") is None


def ancho_terminal(por_defecto=78):
    try:
        a = shutil.get_terminal_size().columns
        return max(60, min(a - 1, 100))
    except Exception:
        return por_defecto


_CODIGOS = {
    "reset": "\033[0m", "negrita": "\033[1m", "tenue": "\033[2m",
    "rojo": "\033[31m", "verde": "\033[32m", "amarillo": "\033[33m",
    "azul": "\033[34m", "magenta": "\033[35m", "cian": "\033[36m",
    "gris": "\033[90m",
}


def c(texto, *estilos):
    if not COLOR or not estilos:
        return texto
    return "".join(_CODIGOS.get(e, "") for e in estilos) + texto + _CODIGOS["reset"]


def _visible(texto):
    fuera, i = 0, 0
    while i < len(texto):
        if texto[i] == "\033":
            while i < len(texto) and texto[i] != "m":
                i += 1
            i += 1
        else:
            fuera += 1
            i += 1
    return fuera


if UNICODE:
    S = {
        "h": "─", "v": "│", "ul": "┌", "ur": "┐", "dl": "└", "dr": "┘",
        "H": "═", "V": "║", "UL": "╔", "UR": "╗", "DL": "╚", "DR": "╝",
        "ok": "✓", "no": "✗", "punto": "·", "flecha": "→", "rama": "├─",
        "fin": "└─", "bala": "•", "aprox": "≈",
    }
    GIRO = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
else:
    S = {
        "h": "-", "v": "|", "ul": "+", "ur": "+", "dl": "+", "dr": "+",
        "H": "=", "V": "|", "UL": "+", "UR": "+", "DL": "+", "DR": "+",
        "ok": "OK", "no": "X", "punto": ".", "flecha": "->", "rama": "|-",
        "fin": "\\-", "bala": "*", "aprox": "~",
    }
    GIRO = "|/-\\"


def sin_acentos(t):
    if UNICODE:
        return t
    tabla = str.maketrans("áéíóúÁÉÍÓÚñÑüÜ¿¡", "aeiouAEIOUnNuU??")
    return t.translate(tabla)


def escribir(t=""):
    print(sin_acentos(t))


def titulo(lineas, color="cian"):
    a = ancho_terminal()
    escribir(c(S["UL"] + S["H"] * (a - 2) + S["UR"], color, "negrita"))
    for ln in lineas:
        relleno = " " * max(0, a - 4 - _visible(ln))
        escribir(c(S["V"], color, "negrita") + " " + ln + relleno + " "
                 + c(S["V"], color, "negrita"))
    escribir(c(S["DL"] + S["H"] * (a - 2) + S["DR"], color, "negrita"))


def caja(lineas, color="gris"):
    a = min(ancho_terminal(), 74)
    escribir("  " + c(S["ul"] + S["h"] * (a - 4) + S["ur"], color))
    for ln in lineas:
        relleno = " " * max(0, a - 6 - _visible(ln))
        escribir("  " + c(S["v"], color) + " " + ln + relleno + " " + c(S["v"], color))
    escribir("  " + c(S["dl"] + S["h"] * (a - 4) + S["dr"], color))


def separador(etiqueta=""):
    a = ancho_terminal()
    if etiqueta:
        etiqueta = " " + etiqueta + " "
        izq = 2
        escribir(c(S["h"] * izq + etiqueta + S["h"] * max(0, a - izq - len(etiqueta)),
                   "gris"))
    else:
        escribir(c(S["h"] * a, "gris"))


def paso(numero, total, texto):
    escribir()
    separador()
    escribir("  " + c(f"PASO {numero} de {total}", "cian", "negrita")
             + c(f"  {S['punto']}  ", "gris") + c(texto, "negrita"))
    separador()
    escribir()


def miles(n):
    return f"{int(n):,}".replace(",", " ")


def duracion(segundos):
    s = int(max(0, segundos))
    if s < 60:
        return f"{s} s"
    if s < 3600:
        return f"{s // 60} min {s % 60:02d} s"
    d, resto = divmod(s, 86400)
    h, resto = divmod(resto, 3600)
    m = resto // 60
    if d:
        return f"{d} d {h} h {m:02d} min"
    return f"{h} h {m:02d} min"


def barra(fraccion, ancho=28):
    fraccion = max(0.0, min(1.0, fraccion))
    lleno = int(round(fraccion * ancho))
    if UNICODE:
        return "█" * lleno + "░" * (ancho - lleno)
    return "#" * lleno + "." * (ancho - lleno)


def _leer(prompt):
    try:
        return input(sin_acentos(prompt))
    except EOFError:
        raise KeyboardInterrupt


def preguntar_opcion(pregunta, opciones, por_defecto="1"):
    escribir("  " + c(pregunta, "negrita"))
    escribir()
    import textwrap
    for clave, tit, desc in opciones:
        marca = c(f"    {clave})", "cian", "negrita")
        escribir(f"{marca} {c(tit, 'negrita')}")
        for d in desc:
            for ln in textwrap.wrap(d, 68) or [""]:
                escribir(c(f"       {ln}", "gris"))
        escribir()
    validas = {o[0] for o in opciones}
    while True:
        r = _leer(f"  Tu eleccion [{por_defecto}]: ").strip()
        if r == "":
            r = por_defecto
        if r in validas:
            escribir()
            return r
        escribir(c(f"  {S['no']} Escribe una de estas opciones: "
                   + ", ".join(sorted(validas)), "amarillo"))


def preguntar_texto(pregunta, por_defecto="", validar=None, ayuda=None):
    if ayuda:
        import textwrap
        for ln in textwrap.wrap(ayuda, 72):
            escribir(c("    " + ln, "gris"))
    while True:
        sufijo = f" [{por_defecto}]" if por_defecto else ""
        r = _leer(f"  {pregunta}{sufijo}: ").strip()
        if r == "" and por_defecto != "":
            r = por_defecto
        if validar:
            problema = validar(r)
            if problema:
                escribir(c(f"  {S['no']} {problema}", "amarillo"))
                continue
        escribir()
        return r


def preguntar_si_no(pregunta, por_defecto=True):
    opciones = "[S/n]" if por_defecto else "[s/N]"
    while True:
        r = _leer(f"  {pregunta} {opciones}: ").strip().lower()
        if r == "":
            escribir()
            return por_defecto
        if r in ("s", "si", "sí", "y", "yes"):
            escribir()
            return True
        if r in ("n", "no"):
            escribir()
            return False
        escribir(c("  Responde s (si) o n (no).", "amarillo"))


def pausa(texto="Pulsa Enter para continuar"):
    if INTERACTIVO:
        _leer(c(f"  {texto}... ", "gris"))


class Panel:
    def __init__(self, cada_segundos_en_log=30, modo="auto"):
        self.lineas_previas = 0
        self.cada = cada_segundos_en_log
        self.ultimo_log = 0.0
        self.primera_vez = True
        self.modo = modo
        self.cursor_oculto = False

    @staticmethod
    def _alto_terminal():
        try:
            return shutil.get_terminal_size().lines
        except Exception:
            return 24

    def _ocultar_cursor(self):
        if not self.cursor_oculto:
            try:
                sys.stdout.write("\033[?25l")
                self.cursor_oculto = True
            except Exception:
                pass

    def _mostrar_cursor(self):
        if self.cursor_oculto:
            try:
                sys.stdout.write("\033[?25h")
                sys.stdout.flush()
            except Exception:
                pass
            self.cursor_oculto = False

    def dibujar(self, lineas, resumen_log=None, linea_compacta=None):
        if self.modo == "ninguno":
            return
        if not INTERACTIVO or self.modo == "simple":
            ahora = time.time()
            if resumen_log and (self.primera_vez
                                or ahora - self.ultimo_log >= self.cada):
                self.primera_vez = False
                self.ultimo_log = ahora
                try:
                    print(sin_acentos(resumen_log), flush=True)
                except Exception:
                    pass
            return

        if len(lineas) + 2 > self._alto_terminal() and linea_compacta:
            lineas = [linea_compacta]

        try:
            self._ocultar_cursor()
            partes = []
            if self.lineas_previas:
                partes.append("\r")
                if self.lineas_previas > 1:
                    partes.append(f"\033[{self.lineas_previas - 1}A")
            for i, ln in enumerate(lineas):
                if i:
                    partes.append("\n")
                partes.append("\033[2K" + sin_acentos(ln))
            for _ in range(max(0, self.lineas_previas - len(lineas))):
                partes.append("\n\033[2K")
            sobrantes = max(0, self.lineas_previas - len(lineas))
            if sobrantes:
                partes.append(f"\033[{sobrantes}A")
            sys.stdout.write("".join(partes))
            sys.stdout.flush()
            self.lineas_previas = len(lineas)
        except Exception:
            self.modo = "ninguno"

    def cerrar(self):
        if INTERACTIVO and self.lineas_previas and self.modo == "auto":
            try:
                sys.stdout.write("\n")
                sys.stdout.flush()
            except Exception:
                pass
        self._mostrar_cursor()
        self.lineas_previas = 0
