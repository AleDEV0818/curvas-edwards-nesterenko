import argparse
import hashlib
import json
import re
import os
import random
import sys
import time

import consola as C
from consola import S, c, escribir

VERSION = "1.6"
TOTAL_PASOS = 4


def comprobar_motor():
    faltantes = []
    detalle = {}
    try:
        import gmpy2
        detalle["gmpy2"] = gmpy2.version()
    except ImportError:
        faltantes.append("gmpy2")
    try:
        import cypari2
        detalle["PARI"] = str(cypari2.Pari().version())
    except ImportError:
        faltantes.append("cypari2")
    return (not faltantes), faltantes, detalle


def instrucciones_instalacion(faltantes):
    escribir()
    C.caja([
        c("Falta instalar algo antes de empezar", "amarillo", "negrita"),
        "",
        "Este programa necesita dos bibliotecas de matematicas:",
        "",
        "   gmpy2     numeros enteros grandes, muy rapido",
        "   cypari2   PARI/GP, para contar puntos de la curva",
        "",
        c("No se encontro: " + ", ".join(faltantes), "rojo"),
    ], "amarillo")
    escribir()
    escribir("  " + c("Como instalarlo", "negrita"))
    escribir()
    escribir(c("  En Linux o WSL (Ubuntu/Debian):", "cian"))
    escribir("      sudo apt update")
    escribir("      sudo apt install -y pari-gp pari-seadata libpari-dev libgmp-dev python3-pip")
    escribir("      pip install gmpy2 cypari2 --break-system-packages")
    escribir()
    escribir(c("  En Windows:", "cian"))
    escribir("      PARI/GP no tiene una version comoda para Windows nativo.")
    escribir("      La forma recomendada es instalar WSL (Ubuntu) y correr alli:")
    escribir("          wsl --install -d Ubuntu")
    escribir("      y luego repetir los comandos de Linux de arriba.")
    escribir()
    escribir(c(f"  Cuando termines, vuelve a ejecutar:  python3 {os.path.basename(__file__)}",
               "gris"))
    escribir()


NIVELES = {
    "1": dict(
        nombre="Produccion 256",
        bits=256,
        alpha=250, beta=255, alpha_twist=240, B=200, h_min=500, cof_max=8,
        residues=(7,), disc_count=4000, d_start=200000,
        tiempo="de varias horas a varios dias",
        para="p de 256 bits, q ~254 bits. Seguridad generica ~2^127, "
             "equiparable a Curve25519 / Ed25519.",
        aviso="Corridas documentadas del metodo: entre 14 y 29 horas por curva "
              "en un solo nucleo. Conviene lanzar varias semillas en paralelo "
              "con correr_produccion.sh.",
    ),
    "2": dict(
        nombre="Produccion 512",
        bits=512,
        alpha=506, beta=511, alpha_twist=496, B=200, h_min=500, cof_max=8,
        residues=(7,), disc_count=4000, d_start=200000,
        tiempo="alrededor de un dia en un solo nucleo",
        para="p de 512 bits, q ~510 bits. Seguridad generica ~2^255, "
             "margen frente a avances en criptoanalisis clasico.",
        aviso="Medido sobre el mismo equipo: 22 horas en un solo nucleo, frente "
              "a 1,5 h a 256 bits. El cuello de botella es la primalidad segura "
              "de q; el coste por primo sube 6,7x (de 0,056 a 0,348 s) y hacen "
              "falta 14 veces mas primos por exito. No son meses: con cuatro "
              "exitos registrados el dato no autoriza una estimacion fina, pero "
              "el orden de magnitud es de un dia.",
    ),
}


def bienvenida():
    escribir()
    C.titulo([
        c("GENERADOR DE CURVAS DE EDWARDS TORCIDAS", "negrita"),
        c("Propiedades de seguridad de Nesterenko (C1-C5, VS1-VS2)", "gris"),
        c(f"version {VERSION}", "gris"),
    ])
    escribir()
    escribir("  Genera parametros de dominio por multiplicacion compleja sobre")
    escribir("  ordenes de conductor 2. Se solicitan "
             + c(f"{TOTAL_PASOS} parametros", "negrita")
             + " antes de iniciar.")
    escribir()
    escribir(c("  La busqueda admite interrupcion: el estado se guarda "
               "periodicamente y", "gris"))
    escribir(c("  la corrida se reanuda desde el ultimo punto guardado.", "gris"))
    escribir()
    C.pausa()


def paso_nivel(por_defecto="1"):
    C.paso(1, TOTAL_PASOS, "Tamano del campo y criterios de aceptacion")
    escribir("  El tamano de p fija la seguridad generica (~2^(bits(q)/2) operaciones")
    escribir("  frente a Pollard rho) y domina el coste de la busqueda.")
    escribir()
    opciones = []
    for clave in ("1", "2"):
        n = NIVELES[clave]
        opciones.append((
            clave,
            f"{n['bits']} bits",
            [n["para"], f"Coste {S['aprox']} {n['tiempo']}."],
        ))
    opciones.append((
        "3", "Personalizado",
        ["Fija a mano el tamano del campo, los umbrales alpha y alpha_twist,",
         "el cofactor maximo, h_min y la cota MOV."]))
    clave = C.preguntar_opcion("Configuracion:", opciones, por_defecto)
    if clave == "3":
        return paso_personalizado()
    nivel = dict(NIVELES[clave])
    nivel["clave"] = clave
    import textwrap
    for i, ln in enumerate(textwrap.wrap(nivel["aviso"], 70)):
        prefijo = f"  {S['bala']} " if i == 0 else "    "
        escribir(c(prefijo + ln, "amarillo"))
    escribir()
    return nivel


def paso_personalizado():
    escribir(c("  Enter acepta el valor entre corchetes.", "gris"))
    escribir()

    def entero(pregunta, defecto, minimo, maximo, ayuda=None):
        def validar(t):
            if not t.lstrip("-").isdigit():
                return "Tiene que ser un numero entero."
            if not (minimo <= int(t) <= maximo):
                return f"Tiene que estar entre {minimo} y {maximo}."
            return None
        return int(C.preguntar_texto(pregunta, str(defecto), validar, ayuda))

    bits = entero("Tamano del campo p, en bits", 256, 32, 1024,
                  "Numero de bits de p. Por debajo de 160 no tiene valor "
                  "criptografico; util unicamente para validar el flujo.")
    beta = bits - 1
    alpha = entero("Tamano minimo del subgrupo, en bits", max(beta - 5, 8),
                   8, beta - 1,
                   "Criterio C4: se exige 2^alpha < q < 2^beta. Cuanto mas "
                   "proximo a beta, menor la densidad de candidatas.")
    atw = entero("Tamano minimo del primo de la curva gemela, en bits",
                 max(alpha - 10, 8), 8, beta - 1,
                 "Criterio VS2: factor primo de la curva torcida > 2^este "
                 "valor. Reducirlo ~10 bits respecto de alpha aumenta "
                 "sustancialmente la densidad de aceptacion.")
    cof_max = entero("Cofactor maximo", 8, 4, 64,
                     "Debe ser multiplo de 4 (exigencia de la forma de "
                     "Edwards). Con 8, cofactor 4 u 8 como Ed25519; con 24 se "
                     "admiten tambien 12 y 24, con mayor densidad.")
    if cof_max % 4:
        cof_max += 4 - (cof_max % 4)
        escribir(c(f"    (ajustado a {cof_max}: tiene que ser multiplo de 4)", "gris"))
    h_min = entero("Numero de clase minimo h(D)", 500, 1, 100000,
                   "Criterio VS1: numero de clase del orden. 500 es el valor "
                   "adoptado en el articulo.")
    B = entero("Cota para la condicion MOV", 200 if bits >= 200 else 20,
               1, 10000,
               "Criterio C5: se exige p^t != 1 (mod q) para t = 1..B, es "
               "decir grado de encaje mayor que B.")
    n_disc = entero("Tamano de la lista de discriminantes",
                    4000 if bits > 160 else 2500, 100, 50000,
                    "Cuantos discriminantes se enumeran. Fija el espacio de "
                    "busqueda (el Delta_max del articulo). Mas discriminantes "
                    "dan mas soluciones de Cornacchia por primo, pero cada primo "
                    "cuesta proporcionalmente mas.")
    d_ini = entero("Valor de D desde el que enumerar",
                   200000 if bits > 160 else 60000, 1000, 10**7,
                   "La enumeracion recorre D creciente desde aqui, quedandose "
                   "con los libres de cuadrados, D = 7 u 11 mod 12 y h(Delta) "
                   ">= h_min.")
    amplio = C.preguntar_si_no(
        "Admitir discriminantes con d = 11 mod 12 (3 divide |E|, "
        "cofactor 12 o 24)?", cof_max >= 12)

    nivel = dict(
        nombre=f"Personalizado {bits}", clave="3", bits=bits,
        alpha=alpha, beta=beta, alpha_twist=atw, B=B, h_min=h_min,
        cof_max=cof_max,
        residues=(7, 11) if amplio else (7,),
        disc_count=n_disc,
        d_start=d_ini,
        tiempo="depende de lo exigentes que sean tus criterios",
        para="Configuracion manual.",
        aviso="Con umbrales muy ajustados la busqueda puede no converger en "
              "tiempo util. Si no aparecen candidatas, baje alpha, alpha_twist "
              "o amplie el cofactor maximo.",
    )
    escribir()
    return nivel


def _semilla_desde_texto(texto):
    return int(hashlib.sha256(texto.encode("utf-8")).hexdigest(), 16)


def paso_semilla():
    C.paso(2, TOTAL_PASOS, "Semilla del generador determinista")
    escribir("  La semilla inicializa el generador pseudoaleatorio que muestrea los")
    escribir("  primos candidatos. La busqueda es " + c("determinista", "negrita")
             + ": la misma semilla y la")
    escribir("  misma configuracion recorren identico camino y devuelven identica curva.")
    escribir()
    escribir("  Esto constituye la evidencia de generacion verificable: un tercero puede")
    escribir("  reejecutar el procedimiento y comprobar que los parametros no fueron")
    escribir("  seleccionados para satisfacer un criterio no declarado.")
    escribir()
    opciones = [
        ("1", "Semilla pseudoaleatoria de 256 bits",
         ["Obtenida del generador de entropia del sistema (os.urandom). El "
          "espacio de 2^256 semillas hace inviable enumerar semillas buscando "
          "una curva debil que supere los criterios."]),
        ("2", "Semilla explicita",
         ["Entero arbitrario, o cadena de texto que se reduce a entero mediante "
          "SHA-256. Ambas opciones son reproducibles."]),
    ]
    clave = C.preguntar_opcion("Origen de la semilla:", opciones, "1")

    if clave == "1":
        import secrets
        s = secrets.randbits(256)
        escribir(c("  Semilla generada (256 bits):", "verde", "negrita"))
        escribir()
        escribir(c("    " + str(s), "verde"))
        escribir()
        escribir(c(f"    hex: {s:064x}", "gris"))
        escribir(c("    Queda registrada en el campo 'seed' del .json de salida.",
                   "gris"))
        escribir()
        return s, "pseudoaleatoria de 256 bits (os.urandom)"

    texto = C.preguntar_texto(
        "Semilla", "",
        validar=lambda t: "No puede quedar vacia." if not t.strip() else None,
        ayuda="Entero (p.ej. 20250815) o cadena de texto (p.ej. tesis-2026), "
              "que se reduce a entero con SHA-256.")
    texto = texto.strip()
    if texto.isdigit():
        return int(texto), f"entero explicito ({texto})"
    s = _semilla_desde_texto(texto)
    escribir(c(f'    "{texto}" {S["flecha"]} {s}', "verde"))
    escribir()
    return s, f'SHA-256 de la cadena "{texto}"'


def normalizar_ruta(ruta):
    r = (ruta or "").strip().strip('"').strip("'")
    m = re.match(r"^([A-Za-z]):[\\/](.*)$", r)
    if m:
        letra, resto = m.group(1).lower(), m.group(2).replace("\\", "/")
        if os.path.isdir(f"/mnt/{letra}"):
            return f"/mnt/{letra}/{resto}"
    return os.path.expanduser(r)


def _directorio_de_trabajo():
    for candidato in (os.getcwd(), os.path.expanduser("~")):
        try:
            prueba = os.path.join(candidato, ".permiso_escritura")
            with open(prueba, "w") as fh:
                fh.write("ok")
            os.remove(prueba)
            return candidato
        except Exception:
            continue
    return os.getcwd()


def paso_destino(nivel, semilla):
    C.paso(3, TOTAL_PASOS, "Nombre de los archivos de salida")
    carpeta = _directorio_de_trabajo()
    escribir("  Los archivos se escriben en el directorio actual:")
    escribir()
    escribir("    " + c(carpeta, "cian"))
    escribir()
    escribir(c("  Para dejarlos en otro sitio, salga (Ctrl+C), situese alli con "
               "cd y", "gris"))
    escribir(c("  vuelva a ejecutar; o use --auto --salida RUTA.", "gris"))
    escribir()
    escribir("  Se escriben dos archivos:")
    escribir()
    escribir(c("    .json   parametros completos, las 18 comprobaciones, el "
               "embudo", "gris"))
    escribir(c("            de descarte y el tiempo de busqueda.", "gris"))
    escribir(c("    .pem    parametros de dominio en SEC 1 (SpecifiedECDomain).", "gris"))
    escribir()
    escribir(c("  Solo se persiste la curva aceptada; las candidatas no se "
               "archivan.", "gris"))
    escribir()

    def _validar(t):
        t = (t or "").strip()
        if not t:
            return "No puede quedar vacio."
        if any(ch in t for ch in "\\/:*?\"<>|"):
            return ("Solo el nombre, sin carpetas ni unidades. "
                    f"Se guardara en {carpeta}")
        if t.lower().endswith((".json", ".pem")):
            return "Sin extension: se anaden .json y .pem automaticamente."
        return None

    sugerido = f"curva{nivel['bits']}_s{str(semilla)[:12]}"
    nombre = C.preguntar_texto("Nombre base (sin extension ni carpetas)",
                               sugerido, validar=_validar)
    return os.path.join(carpeta, nombre.strip())


def paso_confirmar(nivel, semilla, origen_semilla, destino, detalle_motor):
    C.paso(4, TOTAL_PASOS, "Confirmacion de parametros")
    sem = str(semilla)
    if len(sem) > 46:
        sem = sem[:43] + "..."
    C.caja([
        c("Campo", "negrita") + f"        p de {nivel['bits']} bits"
        + f"   (2^{nivel['beta']} < p < 2^{nivel['beta'] + 1})",
        c("Subgrupo", "negrita") + f"     q en (2^{nivel['alpha']}, 2^{nivel['beta']})"
        + f",  cofactor <= {nivel['cof_max']}",
        c("VS1", "negrita") + f"          h(Delta) >= {nivel['h_min']}"
        + f",  {nivel['disc_count']} discriminantes desde D = {nivel['d_start']}",
        c("VS2", "negrita") + f"          r primo de la torcida en "
        + f"(2^{nivel['alpha']}, 2^{nivel['beta']})",
        c("", "gris") + "             "
        + c(f"prefiltro de busqueda  r > 2^{nivel.get('alpha_twist', nivel['alpha'])}"
            "   (no redefine VS2)", "gris"),
        c("C5", "negrita") + f"           cota MOV B = {nivel['B']}",
        c("Cota", "negrita") + f"         {C.miles(nivel['max_primos'])} primos"
        + c("   (al agotarla: «busqueda agotada»)", "gris")
        if nivel.get("max_primos") else
        c("Cota", "negrita") + "         sin cota de primos"
        + c("   (terminacion no garantizada)", "amarillo"),
        "",
        c("Semilla", "negrita") + f"      {sem}",
        c("", "gris") + f"             ({origen_semilla})",
        c("Salida", "negrita") + f"       {os.path.basename(destino)}.json  +  .pem",
        c("Directorio", "negrita") + f"   {os.path.dirname(destino)}",
        c("Estado", "negrita") + f"       {os.path.basename(destino)}.estado.json"
        + c("  (reanudacion)", "gris"),
        c("Motor", "negrita") + f"        PARI/GP {detalle_motor.get('PARI', '?')}",
        c("Coste", "negrita") + f"        {S['aprox']} {nivel['tiempo']}",
    ])
    escribir()
    escribir("  Durante la busqueda se reporta el embudo de descarte en tiempo real.")
    escribir("  " + c("Ctrl+C", "amarillo", "negrita")
             + " interrumpe y emite el resumen parcial; la corrida es")
    escribir("  reproducible, de modo que puede reanudarse con la misma semilla.")
    escribir()
    if not C.preguntar_si_no("Iniciar busqueda?", True):
        escribir()
        escribir(c("  Cancelado.", "gris"))
        escribir()
        sys.exit(0)


class Contador:
    def __init__(self, nivel=None):
        self.nivel = nivel
        self.funnel = dict(p=0, solv=0, cof=0, qsafe=0, built=0, complete=0, vs2=0)
        self.descartes = dict(
            tamano_grupo=0,
            fuera_de_rango=0,
            subgrupo_debil=0,
            no_construible=0,
            suma_incompleta=0,
            ataque_mov=0,
            gemela_debil=0,
            gemela_fuera_intervalo=0,
            punto_base=0,
        )
        self.propuestas = 0
        self.volcar = None
        self.retroceder = None
        self.segundos = 0.0

    def segundos_estimados(self):
        return self.segundos

    def total_descartadas(self):
        return sum(self.descartes.values())


ETIQUETAS_DESCARTE = [
    ("tamano_grupo",    "cofactor no valido  (4 no divide h, o h > max)"),
    ("fuera_de_rango",  "q fuera del rango  (2^alpha, 2^beta)"),
    ("subgrupo_debil",  "q no es primo seguro  [C4]"),
    ("no_construible",  "sin curva de orden m utilizable"),
    ("suma_incompleta", "2-Sylow no ciclico / no completable  [cond. 3]"),
    ("ataque_mov",      "grado de encaje <= B  [C5]"),
    ("gemela_debil",    "torcida sin factor primo grande  [prefiltro a_tw]"),
    ("gemela_fuera_intervalo", "r fuera de (2^alpha, 2^beta)  [VS2 real]"),
    ("punto_base",      "sin punto base de orden q"),
]


def preparar_discriminantes(nivel, pari, class_number, panel):
    objetivo = nivel["disc_count"]
    L = []
    d = nivel["d_start"]
    t0 = time.time()
    giro = 0
    ultimo = 0.0
    while len(L) < objetivo:
        if d % 12 in nivel["residues"] and pari.moebius(int(d)) != 0:
            D = -4 * d
            if class_number(D) >= nivel["h_min"]:
                L.append((d, D))
                ahora = time.time()
                if ahora - ultimo >= 0.15 or len(L) == objetivo:
                    ultimo = ahora
                    giro += 1
                    frac = len(L) / objetivo
                    panel.dibujar([
                        "",
                        "  " + c(C.GIRO[giro % len(C.GIRO)], "cian")
                        + "  Construyendo la lista de discriminantes"
                        + c("   (fase previa, una sola vez)", "gris"),
                        "",
                        "     " + c(C.barra(frac), "cian")
                        + f"  {C.miles(len(L))} / {C.miles(objetivo)}",
                        "",
                        c(f"     Ordenes de conductor 2 (Delta = -4d, d = 7 u 11 mod 12)",
                          "gris"),
                        c(f"     con h(Delta) >= {nivel['h_min']}  [criterio VS1].", "gris"),
                        "",
                    ],
                        resumen_log=(f"[disc] {len(L)}/{objetivo} discriminantes "
                                     f"({time.time() - t0:.0f}s)"),
                        linea_compacta=("  " + c(C.GIRO[giro % len(C.GIRO)], "cian")
                                        + f"  discriminantes {len(L)}/{objetivo}"))
        d += 1
    panel.cerrar()
    return L


def buscar_curva(nivel, semilla, motor, panel, cnt, destino=None, estado=None):
    (mpz, powmod, is_prime, legendre, kronecker, invert, isqrt,
     pari, cornacchia_4p, is_safe_prime, strip_cofactor, class_number,
     hilbert_poly, roots_mod, curve_from_j, quad_twist, ell_card,
     two_torsion_x, complete_edwards, ed_mul, ed_random_point, NEUTRAL) = motor

    rng = random.Random(semilla)
    alpha, beta, B = nivel["alpha"], nivel["beta"], nivel["B"]
    cof_max, atw = nivel["cof_max"], nivel.get("alpha_twist", nivel["alpha"])
    max_primos = nivel.get("max_primos")
    vs2_regla = nivel.get("vs2_regla", "intervalo")
    t0 = time.monotonic()
    previo = 0.0

    if estado:
        cnt.segundos = float(estado["segundos"])
        rs = estado["rng_state"]
        rng.setstate((rs[0], tuple(rs[1]), rs[2]))
        cnt.funnel.update(estado["funnel"])
        cnt.descartes.update(estado["descartes"])
        cnt.propuestas = estado["propuestas"]
        previo = float(estado["segundos"])
        L = [(mpz(d), mpz(D)) for d, D in estado["discriminantes"]]
        escribir()
        escribir(c(f"  {S['ok']} Estado restaurado: {C.miles(cnt.funnel['p'])} "
                   f"primos ya muestreados, {C.miles(cnt.total_descartadas())} "
                   f"descartadas, {C.duracion(previo)} de computo previo.",
                   "verde"))
    else:
        L = preparar_discriminantes(nivel, pari, class_number, panel)
    escribir()
    escribir(c(f"  {S['ok']} {C.miles(len(L))} discriminantes de conductor 2, "
               f"|Delta| de {C.miles(abs(L[0][1]))} a {C.miles(abs(L[-1][1]))}.",
               "verde"))
    escribir()
    escribir("  " + c("Busqueda en curso.", "negrita")
             + c("   Ctrl+C interrumpe; el avance queda guardado.", "gris"))
    escribir()

    f = cnt.funnel
    Hcache = {}
    ultimo_dibujo = 0.0
    ultimo_estado = time.monotonic()
    fase = "muestreando primos seguros"

    def _ahora():
        return previo + (time.monotonic() - t0)

    snap = {}

    def _tomar_snapshot():
        est = rng.getstate()
        snap.clear()
        snap.update(rng_state=[est[0], list(est[1]), est[2]],
                    funnel=dict(cnt.funnel),
                    descartes=dict(cnt.descartes),
                    propuestas=cnt.propuestas,
                    segundos=_ahora())

    def _volcar():
        if destino:
            guardar_estado(destino, nivel, semilla, snap, L)

    def _retroceder():
        if snap:
            cnt.funnel.update(snap["funnel"])
            cnt.descartes.update(snap["descartes"])
            cnt.propuestas = snap["propuestas"]
            cnt.segundos = snap["segundos"]

    cnt.volcar = _volcar
    cnt.retroceder = _retroceder
    instalar_senales(_volcar)

    while True:
        _tomar_snapshot()
        if destino and time.monotonic() - ultimo_estado >= 60:
            ultimo_estado = time.monotonic()
            _volcar()

        if max_primos is not None and f["p"] >= max_primos:
            panel.cerrar()
            cnt.segundos = _ahora()
            return None, cnt, round(_ahora(), 2)

        while True:
            p = mpz(rng.getrandbits(beta)) | (mpz(1) << beta) | 1
            p = p - (p % 12) + 11
            if p.bit_length() == beta + 1 and is_safe_prime(p):
                break
        f["p"] += 1
        nonres = next(x for x in range(2, 1000) if legendre(mpz(x), p) == -1)
        fase = "resolviendo 4p = t^2 + 4D v^2 sobre la lista"

        for d, D in L:
            ahora = time.monotonic()
            if ahora - ultimo_dibujo > 1.0:
                ultimo_dibujo = ahora
                cnt.segundos = _ahora()
                dibujar_progreso(panel, cnt, cnt.segundos, fase)
            sol = cornacchia_4p(D, p)
            if not sol:
                continue
            f["solv"] += 1
            x = sol[0]
            for m in (p + 1 - x, p + 1 + x):
                if m == p:
                    continue
                cnt.propuestas += 1
                h, q = strip_cofactor(m)
                if h % 4 != 0 or h > cof_max:
                    cnt.descartes["tamano_grupo"] += 1
                    continue
                f["cof"] += 1
                if not (mpz(1) << alpha < q < mpz(1) << beta):
                    cnt.descartes["fuera_de_rango"] += 1
                    continue
                if not is_safe_prime(q):
                    cnt.descartes["subgrupo_debil"] += 1
                    continue
                f["qsafe"] += 1

                fase = "calculando H_Delta mod p y realizando la curva"
                dibujar_progreso(panel, cnt, _ahora(), fase)

                if D not in Hcache:
                    Hcache[D] = hilbert_poly(int(D))
                elegida = None
                for j in roots_mod(Hcache[D], p):
                    if j in (mpz(0), mpz(1728) % p):
                        continue
                    a4, a6 = curve_from_j(j, p)
                    if ell_card(a4, a6, p) != int(m):
                        a4, a6 = quad_twist(a4, a6, p, mpz(nonres))
                        if ell_card(a4, a6, p) != int(m):
                            continue
                    if len(two_torsion_x(a4, a6, p)) != 1:
                        continue
                    ce = complete_edwards(a4, a6, p)
                    if ce is None:
                        continue
                    elegida = (a4, a6, ce, j)
                    break
                if elegida is None:
                    cnt.descartes["no_construible"] += 1
                    fase = "resolviendo 4p = t^2 + 4D v^2 sobre la lista"
                    continue
                a4, a6, (a_ed, d_ed, A, Bm), j = elegida
                f["built"] += 1
                f["complete"] += 1

                pe, ok = mpz(1), True
                for _ in range(1, B + 1):
                    pe = (pe * p) % q
                    if pe == 1:
                        ok = False
                        break
                if not ok:
                    cnt.descartes["ataque_mov"] += 1
                    continue

                T = 2 * (p + 1) - m
                ht, rt = strip_cofactor(T)
                if not (is_prime(rt) and rt > (mpz(1) << atw)):
                    cnt.descartes["gemela_debil"] += 1
                    continue
                vs2_ok = bool((mpz(1) << alpha) < rt < (mpz(1) << beta))
                if vs2_regla == "intervalo" and not vs2_ok:
                    cnt.descartes["gemela_fuera_intervalo"] += 1
                    continue
                f["vs2"] += 1

                R = ed_random_point(a_ed, d_ed, p, rng.getrandbits)
                G = ed_mul(h, R, a_ed, d_ed, p)
                if G == NEUTRAL or ed_mul(q, G, a_ed, d_ed, p) != NEUTRAL:
                    cnt.descartes["punto_base"] += 1
                    continue

                panel.cerrar()
                segundos = round(_ahora(), 2)
                curva = dict(
                    p=p, a=a_ed, d=d_ed, q=q, Gx=G[0], Gy=G[1],
                    cofactor=int(h), D=int(D), conductor=2, d_fund=int(d),
                    h_class=class_number(int(D)), j=int(j),
                    A=int(A), B_mont=int(Bm),
                    twist_order=int(T), twist_prime=int(rt), twist_cofactor=int(ht),
                    seed=semilla, alpha=alpha, alpha_twist=int(atw), beta=beta,
                    B_mov=B, a4=int(a4), a6=int(a6),
                    bits_twist_prime=int(rt).bit_length(),
                    VS2=vs2_ok,
                    vs2_regla=vs2_regla,
                    clasificacion=("muy fuerte (C1-C5, VS1, VS2)" if vs2_ok
                                   else "fuerte (C1-C5, VS1); NO cumple VS2"),
                    D_mod_8=int(d) % 8,
                    v2_orden=int(m & -m).bit_length() - 1,
                    v2_previsto=("= 2" if int(d) % 8 == 3 else
                                 ">= 3" if int(d) % 8 == 7 else "sin prediccion"),
                    funnel=dict(f), seconds=segundos)
                return curva, cnt, segundos

            fase = "resolviendo 4p = t^2 + 4D v^2 sobre la lista"


def dibujar_progreso(panel, cnt, transcurrido, fase):
    f = cnt.funnel
    giro = C.GIRO[int(transcurrido) % len(C.GIRO)]
    ritmo = f["p"] / max(transcurrido / 60.0, 1e-9)

    activos = [(k, t) for k, t in ETIQUETAS_DESCARTE
               if cnt.descartes[k] or k == "gemela_debil"]
    ancho = max([len(t) for _, t in activos] + [24]) + 2

    lineas = [
        "",
        "  " + c(giro, "cian") + "  " + c("Busqueda en curso", "negrita")
        + c(f"   t = {C.duracion(transcurrido)}", "gris"),
        c(f"     {fase}", "gris"),
        "",
        "     Primos seguros  " + c(f"{C.miles(f['p']):>12}", "negrita")
        + c(f"   ({ritmo:.0f}/min)", "gris"),
        "     Cornacchia      " + c(f"{C.miles(f['solv']):>12}", "negrita")
        + c(f"   ({f['solv'] / max(f['p'], 1):.2f} por primo)", "gris"),
        "     Candidatos      " + c(f"{C.miles(cnt.propuestas):>12}", "negrita"),
        "",
        "     " + c("Descartes", "gris"),
    ]
    for clave, texto in activos:
        n = cnt.descartes[clave]
        relleno = S["punto"] * max(2, ancho - len(texto))
        lineas.append(f"       {texto} {relleno} "
                      + c(f"{C.miles(n):>11}", "gris" if not n else "amarillo"))
    lineas += [
        "",
        "     " + c(f"Descartadas {C.miles(cnt.total_descartadas())}", "negrita")
        + c(f"     construidas {f['built']}     aceptadas {f['vs2']}", "gris"),
        "",
    ]

    compacta = ("  " + c(giro, "cian")
                + f"  t {C.duracion(transcurrido)}"
                + f"  primos {C.miles(f['p'])} ({ritmo:.0f}/min)"
                + f"  descartadas {C.miles(cnt.total_descartadas())}"
                + f"  construidas {f['built']}")
    resumen = (f"  [{transcurrido:6.0f}s] p={f['p']:6d}  {f}  "
               f"descartadas={cnt.total_descartadas()}")
    panel.dibujar(lineas, resumen_log=resumen, linea_compacta=compacta)


ESTADO_VERSION = 1


def ruta_estado(destino):
    return destino + ".estado.json"


def firma_config(nivel, semilla):
    relevante = dict(
        alpha=nivel["alpha"], beta=nivel["beta"],
        alpha_twist=nivel.get("alpha_twist", nivel["alpha"]),
        B=nivel["B"], h_min=nivel["h_min"], cof_max=nivel["cof_max"],
        residues=list(nivel["residues"]), disc_count=nivel["disc_count"],
        d_start=nivel["d_start"], semilla=str(semilla))
    return hashlib.sha256(
        json.dumps(relevante, sort_keys=True).encode()).hexdigest()[:32]


_escribiendo = [False]


def guardar_estado(destino, nivel, semilla, snapshot, L):
    if not snapshot or _escribiendo[0]:
        return
    _escribiendo[0] = True
    try:
        datos = dict(
            version=ESTADO_VERSION,
            firma=firma_config(nivel, semilla),
            seed=str(semilla),
            rng_state=snapshot["rng_state"],
            funnel=snapshot["funnel"],
            descartes=snapshot["descartes"],
            propuestas=snapshot["propuestas"],
            segundos=round(snapshot["segundos"], 2),
            discriminantes=[[int(d), int(D)] for d, D in L],
        )
        ruta = ruta_estado(destino)
        tmp = f"{ruta}.{os.getpid()}.tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(datos, fh)
        os.replace(tmp, ruta)
    except Exception:
        pass
    finally:
        _escribiendo[0] = False


def cargar_estado(destino, nivel, semilla):
    ruta = ruta_estado(destino)
    if not os.path.exists(ruta):
        return None
    try:
        with open(ruta, encoding="utf-8") as fh:
            datos = json.load(fh)
    except Exception:
        return None
    if datos.get("version") != ESTADO_VERSION:
        return None
    if datos.get("firma") != firma_config(nivel, semilla):
        return None
    return datos


def borrar_estado(destino):
    import glob as _glob
    for ruta in [ruta_estado(destino)] + _glob.glob(ruta_estado(destino) + ".*.tmp"):
        try:
            os.remove(ruta)
        except OSError:
            pass


def instalar_senales(al_terminar):
    import signal
    try:
        signal.signal(signal.SIGHUP, signal.SIG_IGN)
    except (AttributeError, ValueError, OSError):
        pass

    def _manejar(signum, frame):
        al_terminar()
        raise KeyboardInterrupt

    for nombre in ("SIGTERM", "SIGINT"):
        try:
            signal.signal(getattr(signal, nombre), _manejar)
        except (AttributeError, ValueError, OSError):
            pass


def ESPECIFICACION(nivel, curva):
    return {
        "1_umbrales": {
            "alpha": curva["alpha"], "beta": curva["beta"],
            "clasificacion_final": "VS2 <=> r primo y 2^alpha < r < 2^beta",
            "alpha_twist": curva["alpha_twist"],
            "papel_de_alpha_twist": ("PREFILTRO de busqueda; no redefine VS2 ni "
                                     "entra en la clasificacion"),
            "regla_de_aceptacion": curva["vs2_regla"],
        },
        "2_n_q": {
            "criterio": "cota, no longitud exacta: se exige 2^alpha < q < 2^beta",
            "comprobacion": "sobre q = m / h tras extraer el cofactor",
        },
        "3_cotas": {
            "h_max": nivel.get("cof_max"),
            "h_min_clase": nivel.get("h_min"),
            "D_inicial": nivel.get("d_start"),
            "numero_de_discriminantes": nivel.get("disc_count"),
            "residuos_admitidos_mod_12": list(nivel.get("residues", ())),
            "orden_de_enumeracion": ("D creciente desde D_inicial, quedandose con "
                                     "los libres de cuadrados (moebius != 0) que "
                                     "cumplen el residuo y h(-4D) >= h_min_clase"),
            "max_primos": nivel.get("max_primos"),
            "al_agotar": "se devuelve el resultado explicito «busqueda agotada»",
        },
        "4_prng": {
            "generador": "random.Random de la biblioteca estandar (Mersenne Twister)",
            "python": sys.version.split()[0],
            "expansion_de_la_semilla": ("random.Random(semilla) con semilla entera; "
                                        "una semilla dada como texto se reduce antes "
                                        "con SHA-256 y se interpreta en hexadecimal"),
            "consumo": ("rng.getrandbits(beta) por primo candidato, y "
                        "rng.getrandbits(bits(p)) por intento de punto base"),
        },
        "5_recorrido": {
            "raices_de_H_Delta": ("orden que devuelve polrootsmod de PARI/GP; se "
                                  "toma la primera raiz utilizable"),
            "ordenes_por_solucion": "primero m = p+1-t, despues m = p+1+t",
            "signo_de_sigma": ("se elige de modo que (a|p) = +1; equivalentemente "
                               "se permutan (a, d) si resulta (a|p) = -1"),
            "no_residuo_para_la_torcida": "el menor entero c >= 2 con (c|p) = -1",
            "desempate": "se acepta el primer candidato admisible y se detiene",
        },
        "6_primalidad": {
            "division_por_primos_pequenos": "hasta 4096 (criba previa)",
            "durante_la_busqueda": "BPSW y Miller-Rabin (probabilistico)",
            "en_la_salida": ("certificados ECPP revalidables para p, (p-1)/2, q, "
                             "(q-1)/2 y r, mas APRCL independiente"),
        },
        "7_salida": {
            "json": "parametros, clasificacion, embudo y comprobaciones",
            "pem": "SEC 1 SpecifiedECDomain (Weierstrass corta)",
            "certificados_gp": "revalidable con: gp -q <archivo>.certificados.gp",
        },
    }


def guardar(curva, destino, cnt, verificacion, todo_ok, pari=None):
    import formato_pem

    p = int(curva["p"])
    q = int(curva["q"])
    tw = int(curva["twist_prime"])
    cof = int(curva["cofactor"])
    nivel = cnt.nivel or {}

    salida = {}
    salida["generado_por"] = f"generador.py v{VERSION}"
    salida["seed"] = curva["seed"]

    for k in ("p", "a", "d", "q", "Gx", "Gy"):
        salida[k] = str(curva[k])
    salida["cofactor"] = cof
    salida["orden_total"] = str(cof * q)

    salida["bits_p"] = p.bit_length()
    salida["bits_q"] = q.bit_length()
    salida["seguridad_bits"] = q.bit_length() // 2

    for k in ("D", "conductor", "d_fund", "h_class"):
        salida[k] = curva[k]
    salida["j"] = curva["j"]

    salida["A"] = curva["A"]
    salida["B_mont"] = curva["B_mont"]
    salida["a4"] = curva["a4"]
    salida["a6"] = curva["a6"]

    salida["twist_order"] = curva["twist_order"]
    salida["twist_prime"] = curva["twist_prime"]
    salida["twist_cofactor"] = curva["twist_cofactor"]
    salida["bits_twist_prime"] = tw.bit_length()

    salida["VS2"] = bool(curva["VS2"])
    salida["vs2_regla_de_aceptacion"] = curva["vs2_regla"]
    salida["clasificacion"] = curva["clasificacion"]
    salida["D_mod_8"] = curva["D_mod_8"]
    salida["v2_orden"] = curva["v2_orden"]
    salida["v2_previsto_por_D_mod_8"] = curva["v2_previsto"]

    salida["alpha"] = curva["alpha"]
    salida["beta"] = curva["beta"]
    salida["alpha_twist"] = curva["alpha_twist"]
    salida["B_mov"] = curva["B_mov"]
    salida["configuracion"] = dict(
        h_min=nivel.get("h_min"),
        cofactor_max=nivel.get("cof_max"),
        residuos=list(nivel.get("residues", ())),
        discriminantes=nivel.get("disc_count"),
        d_inicial=nivel.get("d_start"),
        max_primos=nivel.get("max_primos"),
    )

    salida["especificacion_determinista"] = ESPECIFICACION(nivel, curva)

    salida["seconds"] = curva["seconds"]
    salida["funnel"] = dict(curva["funnel"])
    salida["descartes"] = dict(cnt.descartes)
    salida["descartadas_total"] = cnt.total_descartadas()
    salida["candidatas_propuestas"] = cnt.propuestas

    salida["verification"] = {k: bool(v) for k, v in verificacion.items()}
    salida["all_ok"] = bool(todo_ok)

    ruta_pem = None
    aviso_pem = None
    prueba_pem = None
    try:
        pem, datos_w = formato_pem.exportar_pem(curva)
        ruta_pem = destino + ".pem"
        with open(ruta_pem, "w", encoding="utf-8") as fh:
            fh.write(pem)
        salida["pem_weierstrass"] = dict(
            a=str(datos_w["A4"]), b=str(datos_w["A6"]),
            Gx=str(datos_w["Gx_w"]), Gy=str(datos_w["Gy_w"]))
        estado, detalle = formato_pem.probar_con_openssl(
            ruta_pem, bits_q=q.bit_length())
        prueba_pem = (estado, detalle)
        salida["pem_probado_openssl"] = dict(estado=estado, detalle=detalle)
    except Exception as e:
        aviso_pem = str(e)

    ruta_cert = None
    if pari is not None:
        import certificados
        try:
            escribir("  " + c("Certificando la primalidad de p, (p-1)/2, q, "
                              "(q-1)/2 y r...", "gris"))
            resumen_cert, texto_gp = certificados.certificar(curva, pari)
            ruta_cert = destino + ".certificados.gp"
            with open(ruta_cert, "w", encoding="utf-8") as fh:
                fh.write(texto_gp)
            salida["certificados"] = resumen_cert
        except Exception as e:
            salida["certificados"] = dict(error=str(e), todos_certificados=False)

    ruta_json = destino + ".json"
    with open(ruta_json, "w", encoding="utf-8") as fh:
        json.dump(salida, fh, indent=2, default=str, ensure_ascii=False)

    return ruta_json, ruta_pem, aviso_pem, prueba_pem, ruta_cert


def explicar_seguridad(lam):
    if lam < 64:
        return ["Insuficiente para uso criptografico: al alcance de un ataque",
                "por fuerza bruta con recursos modestos."]
    if lam < 100:
        return ["Margen estrecho. Adecuado para experimentacion, no para",
                "despliegue."]
    return ["Sin ataque generico practicable conocido. Coste dominado por",
            "Pollard rho sobre el subgrupo de orden q."]


def resumen_final(curva, cnt, segundos, verificacion, todo_ok,
                  ruta_json, ruta_pem, aviso_pem, nivel, prueba_pem=None,
                  ruta_cert=None):
    escribir()
    vs2_ok = bool(curva.get("VS2", True))
    otras = {k: v for k, v in verificacion.items()
             if k not in ("VS2_twist_prime", "prefiltro_alpha_twist")}
    estructura_ok = all(otras.values())
    if todo_ok:
        color, rotulo = "verde", "CURVA ACEPTADA - MUY FUERTE"
    elif estructura_ok and not vs2_ok:
        color, rotulo = "cian", "CURVA ACEPTADA - FUERTE (no cumple VS2)"
    else:
        color, rotulo = "amarillo", "CURVA HALLADA - VERIFICACION INCOMPLETA"
    C.titulo([c(rotulo, "negrita")], color)
    escribir()

    p = int(curva["p"])
    q = int(curva["q"])
    aprobadas = sum(1 for v in verificacion.values() if v)
    total = len(verificacion)
    f = curva["funnel"]
    C.caja([
        c("Tiempo de busqueda", "negrita") + f"   {C.duracion(segundos)}",
        c("Primos muestreados", "negrita") + f"   {C.miles(f['p'])}",
        c("Ordenes candidatos", "negrita") + f"   {C.miles(cnt.propuestas)}",
        c("Descartadas", "negrita") + f"          {C.miles(cnt.total_descartadas())}",
        c("Curvas construidas", "negrita") + f"   {f['built']}",
        "",
        c("Verificacion", "negrita")
        + f"         {aprobadas}/{total} comprobaciones "
        + (c(f"{S['ok']} conformes", "verde") if todo_ok
           else c(f"{S['no']} con fallos", "rojo")),
    ], color)

    escribir()
    escribir("  " + c("Embudo de descarte", "negrita"))
    escribir()
    total_desc = max(cnt.total_descartadas(), 1)
    ancho = max(len(t) for _, t in ETIQUETAS_DESCARTE) + 2
    for clave, texto in ETIQUETAS_DESCARTE:
        n = cnt.descartes[clave]
        if n == 0:
            continue
        relleno = S["punto"] * max(2, ancho - len(texto))
        escribir(f"    {texto} {relleno} {C.miles(n):>11}"
                 + c(f"   {100.0 * n / total_desc:5.1f}%", "gris"))
    escribir()
    escribir(c(f"    Densidad global: 1 curva aceptada por cada "
               f"{C.miles(f['p'])} primos seguros muestreados.", "gris"))
    escribir()

    escribir("  " + c("Clasificacion segun el perfil", "negrita"))
    escribir()
    bits_r = int(curva["twist_prime"]).bit_length()
    escribir(f"    {curva['clasificacion']}")
    escribir(c(f"      r de la torcida: {bits_r} bits", "gris"))
    escribir(c(f"      VS2 exige 2^{curva['alpha']} < r < 2^{curva['beta']}"
               f"   ->   {'se cumple' if vs2_ok else 'NO se cumple'}", "gris"))
    escribir(c(f"      el prefiltro de busqueda era r > 2^{curva['alpha_twist']}"
               "; no es VS2", "gris"))
    escribir(c(f"      D mod 8 = {curva['D_mod_8']}  =>  v_2(|E|) "
               f"{curva['v2_previsto']}   (observado {curva['v2_orden']})", "gris"))
    escribir()

    if not vs2_ok:
        escribir(c("    Un entero de n bits cumple 2^(n-1) <= r < 2^n, de modo "
                   "que un r de", "gris"))
        escribir(c(f"    {bits_r} bits no puede superar 2^{curva['alpha']}. Para "
                   "obtener una curva muy", "gris"))
        escribir(c("    fuerte, repita con otra semilla: los parametros son "
                   "correctos y", "gris"))
        escribir(c("    utilizables, pero deben publicarse como fuertes, no como "
                   "muy fuertes.", "gris"))
        escribir()

    if not estructura_ok:
        escribir("  " + c("Comprobaciones no conformes", "amarillo", "negrita"))
        for k, v in otras.items():
            if not v:
                escribir(c(f"    {S['no']} {k}", "rojo"))
        escribir()

    escribir("  " + c("Parametros obtenidos", "negrita"))
    escribir()
    lam = q.bit_length() // 2
    filas = [
        ("Campo  p", f"{p.bit_length()} bits"),
        ("Subgrupo  q", f"{q.bit_length()} bits"),
        ("Cofactor  h", str(curva["cofactor"])),
        ("Discriminante  Delta", f"{curva['D']}   (conductor {curva['conductor']})"),
        ("Numero de clase  h(Delta)", str(curva["h_class"])),
        ("Torcida", f"cofactor {curva['twist_cofactor']}, "
                    f"primo de {int(curva['twist_prime']).bit_length()} bits"),
        ("Seguridad generica", f"2^{lam} operaciones de grupo"),
    ]
    ancho2 = max(len(k) for k, _ in filas) + 2
    for k, v in filas:
        escribir(f"    {k} {S['punto'] * max(2, ancho2 - len(k))} {v}")
    for linea in explicar_seguridad(lam):
        escribir(c("      " + linea, "gris"))
    escribir()

    escribir("  " + c("Archivos escritos", "negrita"))
    escribir()
    escribir(c(f"    {S['ok']} ", "verde") + ruta_json)
    if ruta_pem:
        escribir(c(f"    {S['ok']} ", "verde") + ruta_pem)
    elif aviso_pem:
        escribir(c(f"    {S['no']} PEM no escrito: {aviso_pem}", "amarillo"))
    escribir()

    if prueba_pem:
        estado, detalle = prueba_pem
        escribir("  " + c("Prueba de uso real del .pem", "negrita"))
        if estado in ("ok", "ok_sin_firma"):
            escribir(c(f"    {S['ok']} {detalle}", "verde"))
            escribir(c("      Los parametros son operativos con bibliotecas reales.", "gris"))
        elif estado == "no_aplicable":
            escribir(c(f"    {S['bala']} {detalle}", "amarillo"))
            escribir(c("      No es un defecto del archivo: ECDSA trunca el resumen a", "gris"))
            escribir(c("      bits(q) y por debajo de ~160 bits OpenSSL no firma.", "gris"))
        elif estado == "sin_openssl":
            escribir(c(f"    {S['bala']} No se pudo probar: {detalle}", "amarillo"))
        else:
            escribir(c(f"    {S['no']} {detalle}", "rojo"))
        escribir()
        base = os.path.basename(ruta_pem)
        escribir("  " + c("Como usarla", "negrita"))
        escribir(c(f"    openssl ecparam -in {base} -text -noout"
                   "            # ver los parametros", "cian"))
        escribir(c(f"    openssl genpkey -paramfile {base} -out clave.pem"
                   "      # clave privada", "cian"))
        escribir(c("    openssl pkey -in clave.pem -pubout -out publica.pem"
                   "   # clave publica", "cian"))
        escribir(c("    openssl dgst -sha256 -sign clave.pem -out f.bin msg"
                   "   # firmar", "cian"))
        escribir(c("    openssl dgst -sha256 -verify publica.pem -signature "
                   "f.bin msg", "cian"))
        escribir()

    if ruta_cert:
        cert = json.load(open(ruta_json, encoding="utf-8")).get("certificados", {})
        ok_cert = cert.get("todos_certificados")
        escribir("  " + c("Certificados de primalidad", "negrita"))
        if ok_cert:
            escribir(c(f"    {S['ok']} p, (p-1)/2, q, (q-1)/2 y r demostrados primos "
                       f"por ECPP y APRCL", "verde"))
        else:
            escribir(c(f"    {S['no']} algun certificado no resulto valido", "rojo"))
        escribir(c(f"    {os.path.basename(ruta_cert)}", "gris"))
        escribir(c(f"      revalidable por cualquiera:  gp -q "
                   f"{os.path.basename(ruta_cert)}", "cian"))
        escribir()

    escribir("  " + c("Verificacion independiente", "negrita"))
    escribir(c(f"    python3 verificar_curva.py {os.path.basename(ruta_json)}", "cian"))
    escribir()
    escribir("  " + c("Reproduccion", "negrita"))
    if nivel["clave"] == "3":
        escribir(c("    Reejecutar con configuracion personalizada equivalente:", "gris"))
        escribir(c(f"      bits {p.bit_length()}   alpha {curva['alpha']}   "
                   f"alpha_twist {curva['alpha_twist']}   "
                   f"cofactor_max {nivel['cof_max']}   h_min {nivel['h_min']}   "
                   f"B {curva['B_mov']}", "cian"))
        escribir(c(f"      semilla {curva['seed']}", "cian"))
    else:
        escribir(c(f"    python3 {os.path.basename(__file__)} --auto "
                   f"--nivel {nivel['clave']} --semilla {curva['seed']} "
                   f"--salida <nombre>", "cian"))
    escribir()


def resumen_agotada(cnt, segundos, nivel, destino=None):
    escribir()
    C.titulo([c("BUSQUEDA AGOTADA", "negrita")], "amarillo")
    escribir()
    C.caja([
        c("Resultado", "negrita") + "        ninguna curva dentro de las cotas",
        c("Cota alcanzada", "negrita")
        + f"   {C.miles(nivel.get('max_primos'))} primos seguros",
        c("Tiempo de computo", "negrita") + f"  {C.duracion(segundos)}",
        c("Ordenes candidatos", "negrita") + f" {C.miles(cnt.propuestas)}",
        c("Descartadas", "negrita") + f"        {C.miles(cnt.total_descartadas())}",
        "",
        "El procedimiento termino: la terminacion esta garantizada por las",
        "cotas. Lo que no esta garantizado es el exito.",
    ], "amarillo")
    escribir()
    ancho = max(len(t) for _, t in ETIQUETAS_DESCARTE) + 2
    for clave, texto in ETIQUETAS_DESCARTE:
        n = cnt.descartes[clave]
        if n:
            escribir(f"    {texto} {S['punto'] * max(2, ancho - len(texto))} "
                     f"{C.miles(n):>11}")
    escribir()
    escribir("  " + c("Que hacer", "negrita"))
    escribir(c("    Subir --max-primos, o relajar alpha_twist unos bits, o "
               "ampliar", "gris"))
    escribir(c("    el cofactor maximo, o probar otra semilla.", "gris"))
    escribir()


def resumen_interrumpido(cnt, destino=None, nivel=None, semilla=None,
                         auto=False):
    escribir()
    escribir()
    C.titulo([c("BUSQUEDA INTERRUMPIDA", "negrita")], "amarillo")
    escribir()
    C.caja([
        c("Tiempo de computo", "negrita")
        + f"    {C.duracion(cnt.segundos_estimados())}",
        c("Primos muestreados", "negrita") + f"   {C.miles(cnt.funnel['p'])}",
        c("Ordenes candidatos", "negrita") + f"   {C.miles(cnt.propuestas)}",
        c("Descartadas", "negrita") + f"          {C.miles(cnt.total_descartadas())}",
        c("Curvas construidas", "negrita") + f"   {cnt.funnel['built']}",
        "",
        "Ninguna candidata supero el conjunto completo de criterios.",
    ], "amarillo")
    escribir()
    ancho = max(len(t) for _, t in ETIQUETAS_DESCARTE) + 2
    hay = False
    for clave, texto in ETIQUETAS_DESCARTE:
        n = cnt.descartes[clave]
        if n:
            hay = True
            escribir(f"    {texto} {S['punto'] * max(2, ancho - len(texto))} "
                     f"{C.miles(n):>11}")
    if hay:
        escribir()

    if destino and os.path.exists(ruta_estado(destino)):
        escribir("  " + c(f"{S['ok']} Estado guardado", "verde", "negrita")
                 + c(f"   {os.path.basename(ruta_estado(destino))}", "gris"))
        escribir()
        escribir("  Para continuar desde este punto exacto:")
        if auto and nivel is not None:
            escribir(c(f"    python3 {os.path.basename(__file__)} --auto "
                       + (f"--bits {nivel['bits']} " if nivel["clave"] == "3"
                          else f"--nivel {nivel['clave']} ")
                       + f"--semilla {semilla} --salida {destino}", "cian"))
        else:
            escribir(c(f"    python3 {os.path.basename(__file__)}", "cian"))
            escribir(c("    (misma configuracion, misma semilla y mismo nombre "
                       "de salida)", "gris"))
        escribir()
        escribir(c("  Para descartar el avance y empezar de nuevo, anada "
                   "--desde-cero", "gris"))
        escribir(c(f"  o borre {os.path.basename(ruta_estado(destino))}.", "gris"))
    else:
        escribir(c("  La corrida es determinista: reejecutar con la misma semilla "
                   "y", "gris"))
        escribir(c("  configuracion recorre identico camino.", "gris"))
    escribir()


def cargar_motor():
    import contextlib
    import io
    from gmpy2 import (mpz, powmod, is_prime, legendre, kronecker, invert, isqrt)
    with contextlib.redirect_stdout(io.StringIO()), \
            contextlib.redirect_stderr(io.StringIO()):
        import edwards_nesterenko as E
    return (mpz, powmod, is_prime, legendre, kronecker, invert, isqrt,
            E._pari, E.cornacchia_4p, E.is_safe_prime, E.strip_cofactor,
            E.class_number, E.hilbert_poly, E.roots_mod, E.curve_from_j,
            E.quad_twist, E.ell_card, E.two_torsion_x, E.complete_edwards,
            E.ed_mul, E.ed_random_point, E.NEUTRAL)


def main():
    ap = argparse.ArgumentParser(
        description="Generador de curvas de Edwards torcidas (Nesterenko C1-C5, VS1-VS2).")
    ap.add_argument("--auto", action="store_true",
                    help="no preguntar nada; usar los valores de la linea de comandos")
    ap.add_argument("--nivel", choices=["1", "2"], default="1",
                    help="1 = p de 256 bits, 2 = p de 512 bits")
    ap.add_argument("--bits", type=int, default=None,
                    help="tamano de p; anula --nivel y activa configuracion manual")
    ap.add_argument("--alpha", type=int, default=None, help="cota inferior de q (bits)")
    ap.add_argument("--cofactor-max", type=int, default=None, help="cofactor maximo")
    ap.add_argument("--h-min", type=int, default=None, help="numero de clase minimo")
    ap.add_argument("--discriminantes", type=int, default=None,
                    help="tamano de la lista de discriminantes (por defecto 4000)")
    ap.add_argument("--d-inicial", type=int, default=None,
                    help="valor de D desde el que se enumera (por defecto 200000)")
    ap.add_argument("--mov", type=int, default=None, help="cota B de la condicion C5")
    ap.add_argument("--residuos-amplios", action="store_true",
                    help="aceptar d = 7 u 11 mod 12 (cofactor 12/24), no solo 7")
    ap.add_argument("--semilla", type=int, default=None,
                    help="semilla entera; si se omite se genera de 256 bits")
    ap.add_argument("--reanudar", dest="reanudar", action="store_true",
                    default=True, help="reanudar si hay estado guardado (por defecto)")
    ap.add_argument("--desde-cero", dest="reanudar", action="store_false",
                    help="ignorar el estado guardado y empezar de nuevo")
    ap.add_argument("--alpha-twist", type=int, default=None,
                    help="PREFILTRO de busqueda sobre la torcida (por defecto, el "
                         "del nivel). No redefine VS2: la clasificacion usa "
                         "siempre el intervalo (2^alpha, 2^beta)")
    ap.add_argument("--vs2", choices=["intervalo", "prefiltro"], default="intervalo",
                    help="regla de ACEPTACION. 'intervalo': se exige VS2 real, "
                         "2^alpha < r < 2^beta. 'prefiltro': se acepta con "
                         "r > 2^alpha_twist y solo se etiqueta el resultado "
                         "(reproduce corridas antiguas)")
    ap.add_argument("--max-primos", type=int, default=20_000_000,
                    help="cota de primos seguros a muestrear; al alcanzarla se "
                         "emite «busqueda agotada». 0 = sin cota (entonces la "
                         "terminacion deja de estar garantizada)")
    ap.add_argument("--salida", default=None,
                    help="ruta y nombre de los archivos, sin extension")
    ap.add_argument("--sin-certificados", action="store_true",
                    help="no emitir los certificados ECPP de primalidad")
    ap.add_argument("--panel", choices=["auto", "simple", "ninguno"],
                    default="auto",
                    help="auto = panel en vivo; simple = una linea cada 30 s; "
                         "ninguno = sin salida de progreso")
    args = ap.parse_args()

    ok, faltantes, detalle = comprobar_motor()
    if not ok:
        if not args.auto:
            bienvenida()
        instrucciones_instalacion(faltantes)
        return 2

    if args.auto:
        if args.bits:
            b = args.bits
            nivel = dict(
                nombre=f"Personalizado {b}", clave="3", bits=b,
                alpha=args.alpha if args.alpha is not None else b - 6,
                beta=b - 1,
                alpha_twist=(args.alpha_twist if args.alpha_twist is not None
                             else b - 16),
                B=args.mov if args.mov is not None else (200 if b >= 200 else 20),
                h_min=args.h_min if args.h_min is not None else 500,
                cof_max=args.cofactor_max if args.cofactor_max is not None else 8,
                residues=(7, 11) if args.residuos_amplios else (7,),
                disc_count=4000 if b > 160 else 2500,
                d_start=200000 if b > 160 else 60000,
                tiempo="segun configuracion", para="Configuracion manual.",
                aviso="")
        else:
            nivel = dict(NIVELES[args.nivel])
            nivel["clave"] = args.nivel
            if args.alpha_twist is not None:
                nivel["alpha_twist"] = args.alpha_twist
            if args.alpha is not None:
                nivel["alpha"] = args.alpha
            if args.cofactor_max is not None:
                nivel["cof_max"] = args.cofactor_max
            if args.h_min is not None:
                nivel["h_min"] = args.h_min
            if args.mov is not None:
                nivel["B"] = args.mov
        if args.discriminantes is not None:
            nivel["disc_count"] = args.discriminantes
        if args.d_inicial is not None:
            nivel["d_start"] = args.d_inicial
        nivel["vs2_regla"] = args.vs2
        nivel["max_primos"] = args.max_primos if args.max_primos > 0 else None
        if nivel["max_primos"] is None:
            escribir(c("== aviso: sin cota de primos; la terminacion no queda "
                       "garantizada ==", "amarillo"))
        if args.semilla is None:
            import secrets
            semilla = secrets.randbits(256)
            escribir(f"== semilla generada (256 bits) = {semilla} ==")
        else:
            semilla = args.semilla
        destino = args.salida or f"curva{nivel['bits']}_s{str(semilla)[:12]}"
        destino = os.path.abspath(normalizar_ruta(destino))
        padre = os.path.dirname(destino) or "."
        if not os.path.isdir(padre):
            escribir(f"== el directorio {padre} no existe; se crea ==")
        os.makedirs(padre, exist_ok=True)
        escribir(f"== p={nivel['bits']} bits  alpha={nivel['alpha']} "
                 f"beta={nivel['beta']} alpha_twist={nivel.get('alpha_twist')} "
                 f"h_min={nivel['h_min']} cofactor<={nivel['cof_max']} "
                 f"B={nivel['B']} residuos={nivel['residues']} ==")
        escribir(f"== semilla={semilla} salida={destino} ==")
    else:
        bienvenida()
        nivel = paso_nivel()
        nivel["vs2_regla"] = args.vs2
        nivel["max_primos"] = args.max_primos if args.max_primos > 0 else None
        semilla, origen = paso_semilla()
        destino = paso_destino(nivel, semilla)
        paso_confirmar(nivel, semilla, origen, destino, detalle)

    nivel.setdefault("vs2_regla", "intervalo")
    nivel.setdefault("max_primos", 20_000_000)

    estado = cargar_estado(destino, nivel, semilla) if args.reanudar else None
    if estado:
        prev = (f"{C.miles(estado['funnel']['p'])} primos, "
                f"{C.miles(sum(estado['descartes'].values()))} descartadas, "
                f"{C.duracion(estado['segundos'])} de computo")
        if args.auto:
            escribir(f"== reanudando corrida previa: {prev} ==")
        else:
            escribir()
            C.caja([
                c("Corrida previa interrumpida", "negrita"),
                "",
                prev,
                "",
                "Reanudar continua exactamente donde quedo.",
            ], "cian")
            escribir()
            if not C.preguntar_si_no("Reanudar la corrida guardada?", True):
                estado = None
                borrar_estado(destino)
    elif args.reanudar and os.path.exists(ruta_estado(destino)):
        escribir(c("  Se encontro un estado guardado que no corresponde a esta "
                   "configuracion; se ignora.", "amarillo"))

    motor = cargar_motor()
    panel = C.Panel(modo=args.panel)
    cnt = Contador(nivel)
    try:
        curva, cnt, segundos = buscar_curva(nivel, semilla, motor, panel, cnt,
                                            destino=destino, estado=estado)
        if curva is None:
            resumen_agotada(cnt, segundos, nivel, destino)
            return 4
    except KeyboardInterrupt:
        panel.cerrar()
        if getattr(cnt, "volcar", None):
            cnt.volcar()
            cnt.retroceder()
        resumen_interrumpido(cnt, destino, nivel, semilla, args.auto)
        return 1

    escribir()
    escribir("  " + c("Ejecutando la verificacion independiente...", "gris"))
    import edwards_nesterenko as E
    todo_ok, verificacion = E.verify_domain_params(curva)

    ruta_json, ruta_pem, aviso_pem, prueba_pem, ruta_cert = guardar(
        curva, destino, cnt, verificacion, todo_ok,
        pari=None if args.sin_certificados else motor[7])
    borrar_estado(destino)
    resumen_final(curva, cnt, segundos, verificacion, todo_ok,
                  ruta_json, ruta_pem, aviso_pem, nivel, prueba_pem, ruta_cert)
    return 0 if todo_ok else 3


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        escribir()
        escribir(c("  Cancelado.", "gris"))
        escribir()
        sys.exit(1)
