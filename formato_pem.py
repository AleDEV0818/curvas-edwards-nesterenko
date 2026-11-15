import base64
import os

OID_CAMPO_PRIMO = (1, 2, 840, 10045, 1, 1)
NEUTRO = (0, 1)


def edwards_a_weierstrass(a, d, p):
    a %= p
    d %= p
    inv_ad = pow((a - d) % p, -1, p)
    A = (2 * (a + d) * inv_ad) % p
    B = (4 * inv_ad) % p
    invB = pow(B, -1, p)
    a2 = (A * invB) % p
    a4 = (invB * invB) % p
    t = (a2 * pow(3, -1, p)) % p
    A4 = (a4 - 3 * t * t) % p
    A6 = (2 * t * t * t - a4 * t) % p
    return A4, A6, A, B, t


def punto_edwards_a_weierstrass(x, y, a, d, p):
    if (x, y) == NEUTRO:
        return None
    _, _, A, B, t = edwards_a_weierstrass(a, d, p)
    if (1 - y) % p == 0 or x % p == 0:
        return None
    u = ((1 + y) * pow((1 - y) % p, -1, p)) % p
    v = (u * pow(x, -1, p)) % p
    invB = pow(B, -1, p)
    X = (u * invB) % p
    Y = (v * invB) % p
    return ((X + t) % p, Y % p)


def punto_en_weierstrass(P, A4, A6, p):
    x, y = P
    return (y * y - x * x * x - A4 * x - A6) % p == 0


def _w_sumar(P, Q, A4, p):
    if P is None:
        return Q
    if Q is None:
        return P
    x1, y1 = P
    x2, y2 = Q
    if x1 == x2 and (y1 + y2) % p == 0:
        return None
    if P == Q:
        lam = (3 * x1 * x1 + A4) * pow((2 * y1) % p, -1, p) % p
    else:
        lam = (y2 - y1) * pow((x2 - x1) % p, -1, p) % p
    x3 = (lam * lam - x1 - x2) % p
    return (x3, (lam * (x1 - x3) - y1) % p)


def w_multiplicar(k, P, A4, p):
    R, Q = None, P
    while k > 0:
        if k & 1:
            R = _w_sumar(R, Q, A4, p)
        Q = _w_sumar(Q, Q, A4, p)
        k >>= 1
    return R


def _longitud(n):
    if n < 0x80:
        return bytes([n])
    cuerpo = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return bytes([0x80 | len(cuerpo)]) + cuerpo


def _tlv(etiqueta, contenido):
    return bytes([etiqueta]) + _longitud(len(contenido)) + contenido


def der_entero(n):
    if n == 0:
        return _tlv(0x02, b"\x00")
    cuerpo = n.to_bytes((n.bit_length() + 8) // 8, "big")
    return _tlv(0x02, cuerpo)


def der_octetos(b):
    return _tlv(0x04, b)


def der_secuencia(*partes):
    return _tlv(0x30, b"".join(partes))


def der_oid(arcos):
    primero = 40 * arcos[0] + arcos[1]
    cuerpo = bytes([primero])
    for arco in arcos[2:]:
        grupo = []
        while True:
            grupo.insert(0, arco & 0x7F)
            arco >>= 7
            if arco == 0:
                break
        for i in range(len(grupo) - 1):
            grupo[i] |= 0x80
        cuerpo += bytes(grupo)
    return _tlv(0x06, cuerpo)


def construir_parametros_der(p, A4, A6, Gx, Gy, orden, cofactor):
    tam = (p.bit_length() + 7) // 8
    campo = der_secuencia(der_oid(OID_CAMPO_PRIMO), der_entero(p))
    curva = der_secuencia(der_octetos(A4.to_bytes(tam, "big")),
                          der_octetos(A6.to_bytes(tam, "big")))
    base = der_octetos(b"\x04" + Gx.to_bytes(tam, "big") + Gy.to_bytes(tam, "big"))
    return der_secuencia(der_entero(1), campo, curva, base,
                         der_entero(orden), der_entero(cofactor))


def a_pem(der, etiqueta="EC PARAMETERS"):
    b64 = base64.b64encode(der).decode()
    lineas = [b64[i:i + 64] for i in range(0, len(b64), 64)]
    return (f"-----BEGIN {etiqueta}-----\n" + "\n".join(lineas)
            + f"\n-----END {etiqueta}-----\n")


def exportar_pem(curva):
    p = int(curva["p"])
    a = int(curva["a"])
    d = int(curva["d"])
    q = int(curva["q"])
    Gx = int(curva["Gx"])
    Gy = int(curva["Gy"])
    cof = int(curva["cofactor"])

    A4, A6, A, B, t = edwards_a_weierstrass(a, d, p)
    G = punto_edwards_a_weierstrass(Gx, Gy, a, d, p)
    if G is None:
        raise ValueError("el punto base no se puede llevar a la forma de Weierstrass")
    if not punto_en_weierstrass(G, A4, A6, p):
        raise ValueError("el punto base convertido no cae sobre la curva")
    if w_multiplicar(q, G, A4, p) is not None:
        raise ValueError("el punto base convertido no tiene orden q")
    if (4 * pow(A4, 3, p) + 27 * pow(A6, 2, p)) % p == 0:
        raise ValueError("la curva de Weierstrass resulta singular")

    der = construir_parametros_der(p, A4, A6, G[0], G[1], q, cof)
    datos = dict(A4=A4, A6=A6, Gx_w=G[0], Gy_w=G[1], A_montgomery=A, B_montgomery=B)
    return a_pem(der), datos


def probar_con_openssl(ruta_pem, bits_q=None, tiempo_max=90):
    import shutil
    import subprocess
    import tempfile

    if not shutil.which("openssl"):
        return "sin_openssl", "openssl no esta en el PATH"

    if bits_q and bits_q >= 512:
        digest = "-sha512"
    elif bits_q and bits_q >= 384:
        digest = "-sha384"
    else:
        digest = "-sha256"

    def correr(*orden):
        return subprocess.run(orden, capture_output=True, timeout=tiempo_max)

    try:
        with tempfile.TemporaryDirectory() as tmp:
            r = lambda n: os.path.join(tmp, n)
            with open(r("m1"), "wb") as fh:
                fh.write(b"prueba de firma")
            with open(r("m2"), "wb") as fh:
                fh.write(b"mensaje distinto")

            for nombre in ("kA", "kB"):
                if correr("openssl", "genpkey", "-paramfile", ruta_pem,
                          "-out", r(nombre + ".pem")).returncode:
                    return "fallo", "no se pudo generar una clave sobre la curva"
            for nombre in ("kA", "kB"):
                if correr("openssl", "pkey", "-in", r(nombre + ".pem"), "-pubout",
                          "-out", r(nombre + ".pub")).returncode:
                    return "fallo", "no se pudo derivar la clave publica"

            ecdh = False
            if not correr("openssl", "pkeyutl", "-derive", "-inkey", r("kA.pem"),
                          "-peerkey", r("kB.pub"), "-out", r("s1")).returncode \
                    and not correr("openssl", "pkeyutl", "-derive", "-inkey",
                                   r("kB.pem"), "-peerkey", r("kA.pub"),
                                   "-out", r("s2")).returncode:
                ecdh = (open(r("s1"), "rb").read() == open(r("s2"), "rb").read()
                        and os.path.getsize(r("s1")) > 0)

            firma_ok = correr("openssl", "dgst", digest, "-sign", r("kA.pem"),
                              "-out", r("f.bin"), r("m1")).returncode == 0
            if not firma_ok:
                if bits_q and bits_q < 160:
                    base = ("claves generadas" + (" y ECDH correcto" if ecdh else ""))
                    return "no_aplicable", (
                        f"{base}; ECDSA no aplica con q de {bits_q} bits "
                        "(curva de juguete)")
                return "fallo", "no se pudo firmar"

            if correr("openssl", "dgst", digest, "-verify", r("kA.pub"),
                      "-signature", r("f.bin"), r("m1")).returncode:
                return "fallo", "la firma valida no se verifico"
            if correr("openssl", "dgst", digest, "-verify", r("kA.pub"),
                      "-signature", r("f.bin"), r("m2")).returncode == 0:
                return "fallo", "se acepto una firma sobre otro mensaje"

        if ecdh:
            return "ok", ("claves generadas, ECDH coincidente, firma "
                          f"{digest[1:].upper()} verificada y firma invalida "
                          "rechazada")
        return "ok_sin_firma", ("claves y firma correctas, pero ECDH no "
                                "pudo comprobarse")
    except subprocess.TimeoutExpired:
        return "fallo", "openssl no respondio a tiempo"
    except Exception as e:
        return "fallo", f"error al probar: {e}"
