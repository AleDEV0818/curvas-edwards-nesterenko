# Curvas de Edwards torcidas completas con las condiciones de Nesterenko

Código del artículo:

> A. García Gómez, E. Domínguez Fiallo y R. Rodríguez Aulet. *Construcción y
> verificación de modelos de Edwards torcidos completos por multiplicación
> compleja bajo condiciones de Nesterenko*. Enviado a *Ciencias Matemáticas*,
> Número Especial de Criptología.

El generador construye por multiplicación compleja curvas que cumplen las
condiciones de Nesterenko (C1–C5 y VS1–VS2) y admiten un modelo de Edwards
torcido con ley de adición completa. El verificador comprueba esas propiedades
sobre los parámetros publicados, sin usar el generador.

## Contenido

| Ruta | Contenido |
|---|---|
| `generador.py` | Generador, versión 1.6. Usa `edwards_nesterenko.py`, `certificados.py`, `formato_pem.py` y `consola.py`. |
| `verificar_curva.py` | Verificador independiente. |
| `instancia_512/` | Curva de 512 bits del artículo (Apéndice A): parámetros y contadores de la ejecución (`.json`), codificación SEC 1 (`.pem`) y certificados de primalidad (`.gp`). |

## Requisitos

Python 3 con `gmpy2` y `cypari2` (`pip install gmpy2 cypari2`), y PARI/GP
(`gp`) para validar los certificados.

## Verificar la curva del artículo

```bash
python3 verificar_curva.py instancia_512/curva512_s598520127730.json --anillo
gp -q instancia_512/curva512_s598520127730.certificados.gp
```

El verificador toma del JSON la tupla `(p, a, d, q, G)`, el discriminante
declarado y los parámetros del perfil, y recalcula el cardinal por conteo de
puntos. Con `--anillo` efectúa las 28 comprobaciones del Apéndice B del
artículo (26 sin esa opción) y tarda alrededor de un minuto. El programa `.gp`
valida los certificados ECPP de `p`, `(p−1)/2`, `q`, `(q−1)/2` y `r`, y repite
cada prueba por APRCL.

## Reproducir la búsqueda

```bash
python3 generador.py --auto --nivel 2 --vs2 prefiltro --semilla 59852012773038218821463345589668874960109573819430490869558879542715014059695
```

La curva del artículo se obtuvo con la versión 1.5 del generador, que aceptaba
la torcida con el prefiltro `r > 2^α_tw`. La opción `--vs2 prefiltro` aplica
ese mismo criterio; sin ella, el generador exige VS2 en la forma
`2^α < r < 2^β`. En pruebas de 40 bits, la versión 1.5 y esta versión con
`--vs2 prefiltro` produjeron la misma curva con la misma semilla. La ejecución
de 512 bits tomó 22,0 h en un núcleo de un AMD Ryzen 7 7735HS a 3,2 GHz y no
se ha repetido con esta versión. La búsqueda puede interrumpirse y reanudarse
con la misma orden; los contadores por etapa de la ejecución original están en
el JSON (`funnel` y `descartes`).

## Entorno de la ejecución

GNU/Linux (WSL) con Python 3.14.4, `gmpy2` 2.3.1 y `cypari2` 2.2.4, que usa
PARI/GP 2.17.2.
