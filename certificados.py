import time


NOMBRES = {
    "p": "p (caracteristica del campo)",
    "p_medio": "(p-1)/2  [p es primo seguro]",
    "q": "q (orden del subgrupo principal)",
    "q_medio": "(q-1)/2  [q es primo seguro]",
    "r": "r (factor primo de la curva torcida)",
}


def valores_a_certificar(curva):
    p = int(curva["p"])
    q = int(curva["q"])
    r = int(curva["twist_prime"])
    return [
        ("p", p),
        ("p_medio", (p - 1) // 2),
        ("q", q),
        ("q_medio", (q - 1) // 2),
        ("r", r),
    ]


def certificar(curva, pari, al_avanzar=None):
    resumen = {}
    bloques = []
    todo_ok = True

    for clave, n in valores_a_certificar(curva):
        if al_avanzar:
            al_avanzar(clave)
        t0 = time.time()
        try:
            cert = pari.primecert(int(n))
            ecpp = int(pari.primecertisvalid(cert)) == 1
            aprcl = int(pari.isprime(int(n))) == 1
            texto = str(cert)
        except Exception as e:
            ecpp = aprcl = False
            texto = f"\\\\ error: {e}"
        segundos = round(time.time() - t0, 2)
        resumen[clave] = dict(
            descripcion=NOMBRES[clave],
            bits=int(n).bit_length(),
            ecpp_valido=bool(ecpp),
            aprcl_primo=bool(aprcl),
            segundos=segundos,
        )
        todo_ok = todo_ok and ecpp and aprcl
        bloques.append((clave, n, texto))

    resumen["todos_certificados"] = todo_ok

    lineas = [
        "\\\\ Certificados de primalidad ECPP (Atkin-Morain), generados con",
        "\\\\ primecert de PARI/GP. Cada certificado demuestra la primalidad del",
        "\\\\ entero correspondiente sin necesidad de confiar en el generador.",
        "\\\\",
        "\\\\ Para revalidarlos, basta PARI/GP:",
        "\\\\     gp -q este_archivo.gp",
        "\\\\",
        "\\\\ Se comprueban dos cosas por cada entero: que el certificado ECPP es",
        "\\\\ valido, y que APRCL (isprime) lo demuestra primo de forma",
        "\\\\ independiente del certificado.",
        "",
    ]
    for clave, n, texto in bloques:
        lineas.append(f"\\\\ ---- {NOMBRES[clave]}  ({int(n).bit_length()} bits) ----")
        lineas.append(f"n_{clave} = {n};")
        lineas.append(f"cert_{clave} = {texto};")
        lineas.append("")

    lineas.append("\\\\ ---- validacion ----")
    lineas.append("errores = 0;")
    for clave, _, _ in bloques:
        lineas.append(
            f'if(primecertisvalid(cert_{clave}) && isprime(n_{clave}),'
            f' print("  OK    {clave}"),'
            f' print("  FALLA {clave}"); errores++);')
    lineas.append('if(errores == 0, print("TODOS LOS CERTIFICADOS SON '
                  'VALIDOS"), print("HAY CERTIFICADOS INVALIDOS: ", errores));')
    lineas.append("quit;")
    lineas.append("")

    return resumen, "\n".join(lineas)
