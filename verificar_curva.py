import sys, json, time
from gmpy2 import mpz, is_prime, is_square, isqrt, legendre, invert, powmod
import cypari2
_pari = cypari2.Pari(); _pari.allocatemem(1 << 30)

SMALL = [p for p in range(2, 4096) if all(p % q for q in range(2, int(p**0.5)+1))]


def is_safe_prime(n):
    n = mpz(n)
    return n > 7 and is_prime(n) and is_prime((n - 1)//2)


def strip_cofactor(m):
    h = mpz(1); r = mpz(m)
    for s in SMALL:
        while r % s == 0: r //= s; h *= s
        if r < s*s: break
    return h, r


def ell_card(a4, a6, p):
    return int(_pari.ellcard(_pari.ellinit([int(a4), int(a6)], int(p))))


def two_torsion_x(a4, a6, p):
    cubic = _pari.Pol([1, 0, int(a4) % int(p), int(a6) % int(p)])
    return [mpz(int(r)) for r in _pari.polrootsmod(cubic, int(p))]


def j_invariante(a4, a6, p):
    c = (4 * powmod(mpz(a4), 3, p)) % p
    den = (c + 27 * powmod(mpz(a6), 2, p)) % p
    if den == 0:
        return None
    return (1728 * c * invert(den, p)) % p


def discriminante_compatible(Delta, t, p):
    Delta = int(Delta)
    dpi = int(t*t - 4*p)
    if Delta >= 0 or dpi >= 0:
        return False, None
    if Delta % 4 not in (0, 1):
        return False, None
    if dpi % Delta != 0:
        return False, None
    f2 = dpi // Delta
    if f2 < 1 or not is_square(mpz(f2)):
        return False, None
    return True, int(isqrt(mpz(f2)))


def anillo_es_orden_declarado(Delta, j, p):
    t0 = time.time()
    H = _pari.polclass(int(Delta))
    coef = [mpz(int(c)) for c in _pari.Vec(H)]
    v = mpz(0)
    jj = mpz(j) % p
    for c in coef:
        v = (v * jj + c) % p
    return v == 0, len(coef) - 1, round(time.time() - t0, 1)


def verify(P, comprobar_anillo=False):
    p = mpz(P['p']); a = mpz(P['a']); d = mpz(P['d']); q = mpz(P['q'])
    Gx = mpz(P['Gx']); Gy = mpz(P['Gy'])
    alpha = int(P.get('alpha', 0)); beta = int(P.get('beta', p.bit_length()))
    atw   = int(P.get('alpha_twist', alpha))
    B = int(P.get('B_mov', P.get('B', 100)))

    a4, a6 = edwards_to_weierstrass(a, d, p)
    m = ell_card(a4, a6, p)
    cof = m // int(q) if q != 0 and m % int(q) == 0 else 0
    t = p + 1 - m
    T = 2*(p + 1) - m
    rt = strip_cofactor(T)[1]
    j = j_invariante(a4, a6, p)

    R = {}
    R['p primo (campo Fp valido)']        = bool(is_prime(p))
    R['a,d no nulos y a != d (no singular)'] = (a % p != 0 and d % p != 0 and (a - d) % p != 0)
    R['p primo seguro (C2)']              = is_safe_prime(p)
    R['p == 11 (mod 12)']                 = (p % 12 == 11)
    R['orden |E| = cofactor * q']         = (q != 0 and m % int(q) == 0)
    R['C1: |E| != p (no anomala)']        = (m != int(p))
    R['cofactor pequeno y multiplo de 4'] = (cof % 4 == 0 and cof <= 32) if cof else False
    R['2-Sylow ciclico (completable)']    = (len(two_torsion_x(a4, a6, p)) == 1)
    R['C3: j != 0, 1728']                 = (j is not None and j != 0
                                             and j != mpz(1728) % p)
    R['C4: q primo']                      = bool(is_prime(q))
    R['C4: q primo seguro']               = is_safe_prime(q)
    if alpha and beta:
        R['C4: q en (2^alpha, 2^beta)']   = (mpz(1) << alpha < q < mpz(1) << beta)
    pe = mpz(1); mov = True
    for _ in range(1, B + 1):
        pe = (pe * (p % q)) % q
        if pe == 1: mov = False; break
    R['C5: MOV (embedding degree > B)']   = mov

    conductor = None
    if 'D' in P:
        Delta = int(P['D'])
        ok_c, conductor = discriminante_compatible(Delta, t, p)
        R['Delta declarado compatible con la traza'] = ok_c
        R['VS1: h(Delta) >= 500']         = (int(_pari.qfbclassno(Delta)) >= 500)
        if comprobar_anillo and j is not None:
            ok_a, grado, seg = anillo_es_orden_declarado(Delta, j, p)
            R[f'End(E) = O_Delta  [H_Delta(j)=0, grado {grado}, {seg}s]'] = ok_a
            Dfund = Delta // 4 if Delta % 4 == 0 else Delta
            if Dfund != Delta:
                ok_f, gr_f, seg_f = anillo_es_orden_declarado(Dfund, j, p)
                R[f'conductor dos, no uno  [H_{Dfund}(j) != 0, grado {gr_f}, '
                  f'{seg_f}s]'] = (not ok_f)

        if ok_c and Delta % 4 == 0:
            D_pos = -Delta // 4
            u = int(t) // 2
            v = int(conductor)
            R['libre de cuadrados y D = 3 (mod 4)'] = (
                int(_pari.moebius(D_pos)) != 0 and D_pos % 4 == 3)
            R['traza par (t = 2u, del orden de conductor dos)'] = (int(t) % 2 == 0)
            R['Prop (i): u par, v impar'] = (u % 2 == 0 and v % 2 == 1)
            R['Prop: p = u^2 + D v^2'] = (u*u + D_pos*v*v == int(p))
            v2 = 0; mm = int(m)
            while mm % 2 == 0:
                mm //= 2; v2 += 1
            if D_pos % 8 == 3:
                R[f'Prop (iii): D = 3 (mod 8) => v_2(|E|) = 2  [es {v2}]'] = (v2 == 2)
            elif D_pos % 8 == 7:
                R[f'Prop (iii): D = 7 (mod 8) => 8 | |E|  [v_2 = {v2}]'] = (v2 >= 3)

    if alpha and beta:
        R[f'VS2: r primo en (2^{alpha}, 2^{beta})  [r de {rt.bit_length()} bits]'] = (
            bool(is_prime(rt)) and (mpz(1) << alpha) < rt < (mpz(1) << beta))
    else:
        R['VS2: r primo (sin alpha/beta declarados, solo se informa)'] = bool(is_prime(rt))
    R['Completitud: (a/p) = +1']          = (legendre(a, p) == 1)
    R['Completitud: (d/p) = -1']          = (legendre(d, p) == -1)
    R['G en la curva']                    = ((a*Gx*Gx + Gy*Gy - 1 - d*Gx*Gx*Gy*Gy) % p == 0)
    R['G != neutro (0,1)']                = not (Gx == 0 and Gy == 1)

    def ed_add(P1, P2):
        x1,y1 = P1; x2,y2 = P2
        tt = (d*x1*x2*y1*y2) % p
        return (((x1*y2+x2*y1)*invert((1+tt) % p, p)) % p,
                ((y1*y2-a*x1*x2)*invert((1-tt) % p, p)) % p)
    def ed_mul(k, Pt):
        Rr=(mpz(0),mpz(1)); Q=Pt; k=int(k)
        while k>0:
            if k&1: Rr=ed_add(Rr,Q)
            Q=ed_add(Q,Q); k>>=1
        return Rr
    R['[q]G = O (G tiene orden q)']       = (ed_mul(q, (Gx,Gy)) == (mpz(0), mpz(1)))

    prefiltro = dict(alpha_twist=atw,
                     cumple=bool(is_prime(rt) and rt > (mpz(1) << atw)) if atw else None)

    vs2 = bool(is_prime(rt) and alpha and beta
               and (mpz(1) << alpha) < rt < (mpz(1) << beta))
    return R, dict(m=m, cofactor=cof, twist_prime=int(rt), traza=int(t),
                   j=None if j is None else int(j), conductor=conductor,
                   bits_r=int(rt).bit_length(), VS2=vs2, prefiltro=prefiltro)


def edwards_to_weierstrass(a, d, p):
    a = mpz(a) % p; d = mpz(d) % p
    inv = invert((a - d) % p, p)
    A = (2*(a + d) * inv) % p
    B = (4 * inv) % p
    Binv = invert(B, p); Binv2 = (Binv*Binv) % p
    a2 = (A * Binv) % p
    a4 = Binv2 % p
    t = (a2 * invert(mpz(3), p)) % p
    A4 = (a4 - 3*t*t) % p
    A6 = (2*t*t*t - a4*t) % p
    return A4, A6


EJEMPLO = {
    "p":"13296111060347","a":"10049676220064","d":"9130075141143",
    "q":"3324029082719","Gx":"2057936421867","Gy":"8409892740748",
    "D":"-2281516","alpha":28,"beta":43,"B_mov":20
}


def main():
    args = [x for x in sys.argv[1:] if not x.startswith("--")]
    anillo = "--anillo" in sys.argv[1:]
    if args:
        P = json.load(open(args[0]))
        print(f"Verificando curva de: {args[0]}\n")
    else:
        P = EJEMPLO
        print("Verificando curva de EJEMPLO embebida (cofactor 4, 44 bits)\n")
    if not anillo:
        print("  (sin --anillo: no se identifica End(E); ver la nota de cabecera)\n")
    R, info = verify(P, comprobar_anillo=anillo)
    width = max(len(k) for k in R)
    allok = True
    for k, v in R.items():
        marca = "OK " if v else ("--" if k.startswith("VS2:") else "FALLA")
        print(f"  [{marca:5s}]  {k.ljust(width)}")
        if not k.startswith("VS2:"):
            allok = allok and v
    print(f"\n  |E| = {info['m']}   cofactor = {info['cofactor']}   "
          f"r de la torcida = {info['bits_r']} bits")
    if info['conductor'] is not None:
        print(f"  t^2-4p = Delta * v^2  con v de "
              f"{int(info['conductor']).bit_length()} bits  (v = conductor "
              f"relativo de Z[pi] en O_Delta)")

    pf = info['prefiltro']
    if pf['cumple'] is not None:
        print(f"\n  Prefiltro de busqueda declarado: r > 2^{pf['alpha_twist']} "
              f"-> {'se cumple' if pf['cumple'] else 'no se cumple'}")
        print("  (es una decision de eficiencia de la busqueda; NO es VS2 y no "
              "entra en el veredicto)")

    print()
    if allok and info['VS2']:
        print("  ==> CURVA MUY FUERTE: C1-C5, VS1 y VS2, con ley de adicion completa")
    elif allok:
        print("  ==> CURVA FUERTE: C1-C5 y VS1, con ley de adicion completa.")
        print("      NO cumple VS2 (el factor primo de la torcida cae fuera del")
        print("      intervalo). Debe publicarse como fuerte, no como muy fuerte.")
    else:
        print("  ==> CURVA RECHAZADA: hay comprobaciones que fallan")
    return 0 if allok else 1


if __name__ == "__main__":
    sys.exit(main())
