import sys, os, time, json, random, argparse
import gmpy2
from gmpy2 import mpz, powmod, is_prime, legendre, kronecker, invert, isqrt
import cypari2

_pari = cypari2.Pari()
_pari.allocatemem(1 << 30)

NEUTRAL = (mpz(0), mpz(1))

def _small_primes(limit):
    sieve = bytearray([1]) * (limit + 1)
    sieve[0] = sieve[1] = 0
    for i in range(2, int(limit ** 0.5) + 1):
        if sieve[i]:
            sieve[i * i::i] = bytearray(len(sieve[i * i::i]))
    return [i for i in range(2, limit + 1) if sieve[i]]

SMALL_PRIMES = _small_primes(4096)


def sqrt_mod(a, p):
    a = mpz(a) % p
    if a == 0:
        return mpz(0)
    if legendre(a, p) != 1:
        return None
    if p % 4 == 3:
        return powmod(a, (p + 1) // 4, p)
    q = p - 1; s = 0
    while q % 2 == 0:
        q //= 2; s += 1
    z = mpz(2)
    while legendre(z, p) != -1:
        z += 1
    m = s; c = powmod(z, q, p); t = powmod(a, q, p); r = powmod(a, (q + 1) // 2, p)
    while t != 1:
        i = 0; tt = t
        while tt != 1:
            tt = (tt * tt) % p; i += 1
        b = powmod(c, mpz(1) << (m - i - 1), p)
        m = i; c = (b * b) % p; t = (t * c) % p; r = (r * b) % p
    return r


def cornacchia_4p(D, p):
    p = mpz(p); D = mpz(D)
    if kronecker(D % p, p) == -1:
        return None
    x0 = sqrt_mod(D % p, p)
    if x0 is None:
        return None
    if (x0 - D) % 2 != 0:
        x0 = p - x0
    a = 2 * p; b = x0; limit = isqrt(4 * p)
    while b > limit:
        a, b = b, a % b
    c = 4 * p - b * b; absD = -D
    if c % absD != 0:
        return None
    y2 = c // absD; y = isqrt(y2)
    if y * y != y2:
        return None
    if b % 2 != 0:
        return None
    return (b, y)


def is_safe_prime(n):
    n = mpz(n)
    return n > 7 and is_prime(n) and is_prime((n - 1) // 2)


def valuation_2(n):
    n = int(n); v = 0
    while n and n % 2 == 0:
        n //= 2; v += 1
    return v


def strip_cofactor(m):
    h = mpz(1); r = mpz(m)
    for s in SMALL_PRIMES:
        if r % s == 0:
            while r % s == 0:
                r //= s; h *= s
        if r < s * s:
            break
    return h, r


def class_number(D):
    return int(_pari.qfbclassno(int(D)))

def hilbert_poly(D):
    return _pari.polclass(int(D))

def roots_mod(poly, p):
    return [mpz(int(r)) for r in _pari.polrootsmod(poly, int(p))]

def curve_from_j(j, p):
    j = mpz(j) % p
    k = (j * invert((1728 - j) % p, p)) % p
    return (3 * k) % p, (2 * k) % p

def quad_twist(a4, a6, p, c):
    return (a4 * c * c) % p, (a6 * c * c * c) % p

def ell_card(a4, a6, p):
    return int(_pari.ellcard(_pari.ellinit([int(a4), int(a6)], int(p))))

def two_torsion_x(a4, a6, p):
    cubic = _pari.Pol([1, 0, int(a4) % int(p), int(a6) % int(p)])
    return [mpz(int(r)) for r in _pari.polrootsmod(cubic, int(p))]


def weierstrass_to_edwards(a4, a6, p, alpha):
    delta = (3 * alpha * alpha + a4) % p
    if delta == 0 or legendre(delta, p) != 1:
        return None
    s = invert(sqrt_mod(delta, p), p)
    A = (3 * alpha * s) % p
    B = s
    Binv = invert(B, p)
    a = ((A + 2) * Binv) % p
    d = ((A - 2) * Binv) % p
    return (A, B, a, d)


def complete_edwards(a4, a6, p):
    for alpha in two_torsion_x(a4, a6, p):
        r = weierstrass_to_edwards(a4, a6, p, alpha)
        if not r:
            continue
        A, B, a, d = r
        la, ld = legendre(a, p), legendre(d, p)
        if la * ld == -1:
            if la == 1:
                return a, d, A, B
            return d, a, (-A) % p, (-B) % p
    return None


def ed_add(P, Q, a, d, p):
    x1, y1 = P; x2, y2 = Q
    t = (d * x1 * x2 * y1 * y2) % p
    x3 = ((x1 * y2 + x2 * y1) * invert((1 + t) % p, p)) % p
    y3 = ((y1 * y2 - a * x1 * x2) * invert((1 - t) % p, p)) % p
    return (x3, y3)

def ed_mul(k, P, a, d, p):
    k = int(k); R = NEUTRAL; Q = P
    while k > 0:
        if k & 1:
            R = ed_add(R, Q, a, d, p)
        Q = ed_add(Q, Q, a, d, p)
        k >>= 1
    return R

def ed_on_curve(P, a, d, p):
    x, y = P
    return (a * x * x + y * y - 1 - d * x * x * y * y) % p == 0

def ed_random_point(a, d, p, randbits):
    while True:
        x = mpz(randbits(p.bit_length())) % p
        den = (1 - d * x * x) % p
        if den == 0:
            continue
        rhs = ((1 - a * x * x) % p * invert(den, p)) % p
        if legendre(rhs, p) == 1:
            return (x, sqrt_mod(rhs, p))


def build_disc_list(h_min, count, residues=(7, 11), d_start=60000, verbose=False):
    L = []; d = d_start
    while len(L) < count:
        if d % 12 in residues and _pari.moebius(int(d)) != 0:
            D = mpz(-4 * d)
            if class_number(D) >= h_min:
                L.append((d, D))
        d += 1
    if verbose:
        print(f"[disc] {len(L)} discriminantes de conductor 2, |∆| de "
              f"{abs(int(L[0][1]))} a {abs(int(L[-1][1]))}", flush=True)
    return L


def clasificar_vs2(r, alpha, beta):
    r = mpz(r)
    if not is_prime(r):
        return False, r.bit_length()
    return bool((mpz(1) << alpha) < r < (mpz(1) << beta)), r.bit_length()


def generate(alpha, beta, B, h_min=500, cof_max=8,
             residues=(7,), disc_count=2000, d_start=60000,
             seed=None, timeout_s=None, verbose=True,
             save_candidates_dir=None, alpha_twist=None,
             max_primos=None, vs2_regla="intervalo"):
    rng = random.Random(seed)
    atw = alpha if alpha_twist is None else alpha_twist
    if vs2_regla not in ("intervalo", "prefiltro"):
        raise ValueError("vs2_regla debe ser 'intervalo' o 'prefiltro'")
    t0 = time.time()
    L = build_disc_list(h_min, disc_count, residues, d_start, verbose)
    Hcache = {}
    f = dict(p=0, solv=0, cof=0, qsafe=0, built=0, complete=0, vs2=0)

    while True:
        if max_primos is not None and f['p'] >= max_primos:
            if verbose:
                print(f"BUSQUEDA AGOTADA: {f['p']} primos seguros muestreados "
                      f"(cota max_primos). Embudo: {f}", flush=True)
            return dict(agotada=True, motivo="max_primos", primos=f['p'],
                        funnel=dict(f), seed=seed,
                        seconds=round(time.time() - t0, 2))
        if timeout_s is not None and time.time() - t0 >= timeout_s:
            if verbose:
                print(f"BUSQUEDA AGOTADA: se alcanzo el limite de tiempo "
                      f"({timeout_s} s). Embudo: {f}", flush=True)
            return dict(agotada=True, motivo="timeout", primos=f['p'],
                        funnel=dict(f), seed=seed,
                        seconds=round(time.time() - t0, 2))

        while True:
            p = mpz(rng.getrandbits(beta)) | (mpz(1) << beta) | 1
            p = p - (p % 12) + 11
            if p.bit_length() == beta + 1 and is_safe_prime(p):
                break
        f['p'] += 1
        nonres = next(c for c in range(2, 1000) if legendre(mpz(c), p) == -1)

        for d, D in L:
            sol = cornacchia_4p(D, p)
            if not sol:
                continue
            f['solv'] += 1
            x = sol[0]
            for m in (p + 1 - x, p + 1 + x):
                if m == p:
                    continue
                h, q = strip_cofactor(m)
                if h % 4 != 0 or h > cof_max:
                    continue
                f['cof'] += 1
                if not (mpz(1) << alpha < q < mpz(1) << beta):
                    continue
                if not is_safe_prime(q):
                    continue
                f['qsafe'] += 1

                if D not in Hcache:
                    Hcache[D] = hilbert_poly(int(D))
                roots = roots_mod(Hcache[D], p)
                chosen = None
                for j in roots:
                    if j in (mpz(0), mpz(1728) % p):
                        continue
                    a4, a6 = curve_from_j(j, p)
                    c = ell_card(a4, a6, p)
                    if c != int(m):
                        a4, a6 = quad_twist(a4, a6, p, mpz(nonres))
                        if ell_card(a4, a6, p) != int(m):
                            continue
                    if len(two_torsion_x(a4, a6, p)) != 1:
                        if verbose and p % 4 == 3:
                            print("  [AVISO] 2-Sylow no ciclico con conductor "
                                  f"dos y p ≡ 3 (mod 4): D={int(d)}, j={int(j)}. "
                                  "Contradice la Proposicion; revisar el codigo.",
                                  flush=True)
                        continue
                    ce = complete_edwards(a4, a6, p)
                    if ce is None:
                        continue
                    chosen = (a4, a6, ce, j)
                    break
                if chosen is None:
                    continue
                a4, a6, (a_ed, d_ed, A, Bm), j = chosen
                f['built'] += 1; f['complete'] += 1

                if save_candidates_dir:
                    os.makedirs(save_candidates_dir, exist_ok=True)
                    _fn = os.path.join(save_candidates_dir,
                                       f"candidata_{f['complete']:03d}.json")
                    with open(_fn, "w") as _fh:
                        json.dump({k: str(v) for k, v in dict(
                            p=p, a=a_ed, d=d_ed, q=q, cofactor=h, m=m,
                            twist_m=2*(p+1)-m, j_invariante=j,
                            D_librecuadrados=d, Delta_o_D=D,
                            alpha=alpha, beta=beta,
                            nota=("curva de Edwards torcida COMPLETA de "
                                  f"{int(p).bit_length()} bits; cumple C1-C4, "
                                  "VS1 y completitud; pendiente C5/VS2")
                        ).items()}, _fh, indent=2)

                pe = mpz(1); ok = True
                for _t in range(1, B + 1):
                    pe = (pe * p) % q
                    if pe == 1:
                        ok = False; break
                if not ok:
                    continue

                T = 2 * (p + 1) - m
                ht, rt = strip_cofactor(T)
                if not (is_prime(rt) and rt > (mpz(1) << atw)):
                    continue
                vs2_ok, bits_r = clasificar_vs2(rt, alpha, beta)
                if vs2_regla == "intervalo" and not vs2_ok:
                    if verbose:
                        print(f"  [VS2] r de {bits_r} bits supera el prefiltro "
                              f"2^{atw} pero no el intervalo (2^{alpha}, 2^{beta}); "
                              "se descarta.", flush=True)
                    continue
                f['vs2'] += 1

                R = ed_random_point(a_ed, d_ed, p, rng.getrandbits)
                G = ed_mul(h, R, a_ed, d_ed, p)
                if G == NEUTRAL or ed_mul(q, G, a_ed, d_ed, p) != NEUTRAL:
                    continue

                return dict(
                    p=p, a=a_ed, d=d_ed, q=q, Gx=G[0], Gy=G[1],
                    cofactor=int(h), D=int(D), conductor=2, d_fund=int(d),
                    h_class=class_number(int(D)), j=int(j),
                    A=int(A), B_mont=int(Bm),
                    twist_order=int(T), twist_prime=int(rt), twist_cofactor=int(ht),
                    seed=seed, alpha=alpha, alpha_twist=int(atw), beta=beta,
                    B_mov=B, a4=int(a4), a6=int(a6),
                    bits_twist_prime=int(bits_r),
                    VS2=bool(vs2_ok),
                    vs2_regla=vs2_regla,
                    clasificacion=("muy fuerte (C1-C5, VS1, VS2)" if vs2_ok
                                   else "fuerte (C1-C5, VS1); NO cumple VS2"),
                    D_mod_8=int(d) % 8,
                    v2_orden=int(valuation_2(m)),
                    v2_previsto=("= 2" if int(d) % 8 == 3 else
                                 ">= 3" if int(d) % 8 == 7 else "sin prediccion"),
                    funnel=dict(f), seconds=round(time.time() - t0, 2))

        if verbose and f['p'] % 100 == 0:
            print(f"  [{time.time()-t0:5.0f}s] p={f['p']:5d}  {f}", flush=True)

    if verbose:
        print("Sin curva dentro del timeout. Embudo:", f, flush=True)
    return None


def verify_domain_params(P, B_mov_check=None):
    p = mpz(P['p']); a = mpz(P['a']); d = mpz(P['d']); q = mpz(P['q'])
    G = (mpz(P['Gx']), mpz(P['Gy']))
    a4 = mpz(P['a4']); a6 = mpz(P['a6']); cof = mpz(P['cofactor'])
    B = B_mov_check if B_mov_check is not None else P['B_mov']
    r = {}
    r['p_safe_prime']       = is_safe_prime(p)
    r['p_mod_12_eq_11']     = (p % 12 == 11)
    m = ell_card(a4, a6, p)
    r['order_eq_cof_q']     = (m == int(cof * q))
    r['C1_order_neq_p']     = (m != int(p))
    r['cofactor_div_4']     = (cof % 4 == 0)
    r['two_Sylow_cyclic']   = (len(two_torsion_x(a4, a6, p)) == 1)
    j = (mpz(1728) * 4 * a4**3 * invert((4*a4**3 + 27*a6**2) % p, p)) % p
    r['C3_j_neq_0_1728']    = (j not in (mpz(0), mpz(1728) % p))
    r['C4_q_safe_prime']    = is_safe_prime(q)
    r['C4_q_in_range']      = (mpz(1) << P['alpha'] < q < mpz(1) << P['beta'])
    pe = mpz(1); mov = True
    for _ in range(1, B + 1):
        pe = (pe * p) % q
        if pe == 1:
            mov = False; break
    r['C5_MOV']             = mov
    r['VS1_h_class_ge_500'] = (class_number(int(P['D'])) >= 500)

    _t = int(p) + 1 - m
    _dpi = _t * _t - 4 * int(p)
    _Delta = int(P['D'])
    _compat = (_Delta < 0 and _dpi < 0 and _dpi % _Delta == 0
               and gmpy2.is_square(mpz(_dpi // _Delta)))
    r['Delta_compatible_con_traza'] = bool(_compat)

    if _compat:
        _v = int(isqrt(mpz(_dpi // _Delta)))
        _u = _t // 2
        _D = int(P.get('d_fund', -_Delta // 4))
        r['traza_par_u_bien_definido'] = (_t % 2 == 0)
        r['prop_u_par_v_impar']        = (_u % 2 == 0 and _v % 2 == 1)
        r['prop_p_igual_u2_mas_Dv2']   = (_u * _u + _D * _v * _v == int(p))
        _v2 = 0
        _mm = m
        while _mm % 2 == 0:
            _mm //= 2; _v2 += 1
        r['prop_D_mod_8_predice_cofactor'] = (
            (_v2 == 2) if _D % 8 == 3 else (_v2 >= 3) if _D % 8 == 7 else True)

    _alpha, _beta = int(P['alpha']), int(P['beta'])
    _atw = int(P.get('alpha_twist', _alpha))
    _rt = mpz(P['twist_prime'])
    r['VS2_twist_prime'] = (is_prime(_rt)
                            and (mpz(1) << _alpha) < _rt < (mpz(1) << _beta))
    r['prefiltro_alpha_twist'] = bool(is_prime(_rt) and _rt > (mpz(1) << _atw))

    r['cond3_a_is_QR']      = (legendre(a, p) == 1)
    r['cond3_d_is_nonQR']   = (legendre(d, p) == -1)
    r['G_on_curve']         = ed_on_curve(G, a, d, p)
    r['G_not_neutral']      = (G != NEUTRAL)
    r['G_order_q']          = (ed_mul(q, G, a, d, p) == NEUTRAL)
    rng = random.Random(12345); Pt = G; chain = True
    for _ in range(200):
        Qt = ed_random_point(a, d, p, rng.getrandbits)
        Pt = ed_add(Pt, Qt, a, d, p)
        if not ed_on_curve(Pt, a, d, p):
            chain = False; break
    r['completeness_200_adds'] = chain
    return all(r.values()), r


PRESETS = {
    "demo": dict(alpha=28, beta=43, B=20, h_min=500, cof_max=24,
                 residues=(7, 11), disc_count=2500, d_start=60000,
                 timeout_s=900),

    "prod": dict(alpha=250, beta=255, B=200, h_min=500, cof_max=8,
                 residues=(7,), disc_count=4000, d_start=200000,
                 timeout_s=None),
}


def main():
    ap = argparse.ArgumentParser(
        description="Generador de curvas de Edwards torcidas muy fuertes y completas.")
    ap.add_argument("preset", nargs="?", default="demo", choices=list(PRESETS))
    ap.add_argument("--seed", type=int, default=2024)
    ap.add_argument("--out", default="curva_nesterenko.json")
    ap.add_argument("--alpha-twist", type=int, default=None,
                    help="PREFILTRO de busqueda sobre la torcida (por defecto = alpha). "
                         "No redefine VS2: la clasificacion usa siempre (alpha, beta)")
    ap.add_argument("--max-primos", type=int, default=20_000_000,
                    help="cota de primos seguros a muestrear; al alcanzarla se "
                         "devuelve 'busqueda agotada'. 0 = sin cota (entonces la "
                         "terminacion deja de estar garantizada)")
    ap.add_argument("--vs2", choices=["intervalo", "prefiltro"], default="intervalo",
                    help="regla de ACEPTACION: 'intervalo' exige 2^alpha < r < 2^beta "
                         "(Definicion 2); 'prefiltro' acepta con r > 2^alpha_twist y "
                         "solo etiqueta el resultado (reproduce corridas antiguas)")
    a = ap.parse_args()
    cfg = dict(PRESETS[a.preset]); cfg["seed"] = a.seed
    cfg["alpha_twist"] = a.alpha_twist
    cfg["max_primos"] = a.max_primos if a.max_primos > 0 else None
    cfg["vs2_regla"] = a.vs2
    if cfg["max_primos"] is None:
        print("aviso: sin cota de primos; la terminacion no queda garantizada",
              flush=True)
    _base = os.path.splitext(os.path.basename(a.out))[0]
    cfg["save_candidates_dir"] = os.path.join(
        os.path.dirname(a.out) or ".", f"candidatas_{_base}")
    print(f"== preset '{a.preset}'  alpha={cfg['alpha']} beta={cfg['beta']} "
          f"h_min={cfg['h_min']} cofactor<={cfg['cof_max']} residuos={cfg['residues']} ==",
          flush=True)
    res = generate(**cfg)
    if not res:
        print("No se encontro curva."); return 1
    if res.get("agotada"):
        print(f"\n========== BUSQUEDA AGOTADA ({res['seconds']} s) ==========")
        print(f"  motivo  = {res['motivo']}")
        print(f"  primos  = {res['primos']}")
        print(f"  embudo  = {res['funnel']}")
        print("\n  El procedimiento termino sin curva: se alcanzo una cota "
              "explicita de recursos.")
        with open(a.out, "w") as fh:
            json.dump(res, fh, indent=2, default=str)
        print(f"  Guardado en {a.out}")
        return 4
    print(f"\n========== CURVA ENCONTRADA ({res['seconds']} s) ==========")
    print(f"  clasificacion = {res['clasificacion']}")
    print(f"  r de {res['bits_twist_prime']} bits; VS2 sobre "
          f"(2^{res['alpha']}, 2^{res['beta']}) = {res['VS2']}")
    print(f"  D mod 8 = {res['D_mod_8']}  ->  v_2(|E|) {res['v2_previsto']}"
          f"  (observado {res['v2_orden']})")
    for k in ("p", "a", "d", "q", "cofactor", "Gx", "Gy",
              "D", "d_fund", "h_class", "twist_prime"):
        print(f"  {k:11s}= {res[k]}")
    print(f"  embudo     = {res['funnel']}")
    ok, rep = verify_domain_params(res)
    print("\n---------- VERIFICACION INDEPENDIENTE ----------")
    for k, v in rep.items():
        print(f"  [{'OK ' if v else 'FALLA'}] {k}")
    print(f"\n  RESULTADO: {'TODAS LAS CONDICIONES OK' if ok else 'HAY FALLAS'}")
    res["verification"] = {k: bool(v) for k, v in rep.items()}
    res["all_ok"] = bool(ok)
    with open(a.out, "w") as fh:
        json.dump({k: (str(v) if isinstance(v, mpz) else v) for k, v in res.items()},
                  fh, indent=2, default=str)
    print(f"\n  Guardado en {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
