#!/usr/bin/env python3
"""Fusiona data/games.json con la página publicada del artefacto.

Uso: python3 scripts/merge.py PAGINA_ACTUAL.html data/games.json SALIDA.html REPORTE.md

- Conserva el título de cada juego existente (las calificaciones y notas
  compartidas del artefacto se asocian por título).
- Quita los juegos que ya no están o ya no son cooperativos y agrega los nuevos.
- Actualiza fechas y conteos de las notas y escribe un resumen de cambios.
Fila: [t,p,co,k,f,st,g,pct,rn,rel,v1,pr,po,pd,aid,gp]
"""
import json
import re
import sys

MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sept", "oct", "nov", "dic"]


def cop(n):
    return "$" + f"{n:,}".replace(",", ".")


def fmt_int(n):
    return f"{n:,}".replace(",", ".")


def main(page_path, games_path, out_path, report_path):
    html = open(page_path, encoding="utf-8").read()
    m = re.search(r"const DATA = (\[.*?\]);\n", html, re.S)
    if not m:
        sys.exit("No encontré `const DATA = [...]` en la página.")
    old = json.loads(m.group(1).replace("<\\/", "</"))
    feed = json.load(open(games_path, encoding="utf-8"))
    new_by = {g["aid"]: g for g in feed["games"]}
    if len(new_by) < 0.7 * len(old):
        sys.exit(f"Datos nuevos sospechosos ({len(new_by)} vs {len(old)} juegos); no se publica.")

    rows, removed, pairs, seen = [], [], [], set()
    for r in old:
        g = new_by.get(r[14])
        if not g:
            removed.append(r[0])
            continue
        seen.add(r[14])
        nr = list(r)
        nr[1] = g["p"]; nr[2] = 1 if g["p"] == "R" else 0; nr[3] = g["k"]; nr[4] = g["f"]
        nr[7] = g["pct"]; nr[8] = g["rn"]
        if not nr[9] and g["rel"]:
            nr[9] = g["rel"]
        nr[10] = g["v1"]
        nr[11] = g["pr"]; nr[12] = g["po"]; nr[13] = g["pd"]; nr[15] = g["gp"]
        rows.append(nr)
        pairs.append((r, nr))
    added = []
    for aid, g in new_by.items():
        if aid in seen:
            continue
        nr = [g["t"], g["p"], 1 if g["p"] == "R" else 0, g["k"], g["f"], g["st"], g["g"],
              g["pct"], g["rn"], g["rel"], g["v1"], g["pr"], g["po"], g["pd"], aid, g["gp"]]
        rows.append(nr)
        added.append(nr)
    rows.sort(key=lambda r: r[0].lower())

    # Página nueva
    data_js = json.dumps(rows, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    out = html[:m.start(1)] + data_js + html[m.end(1):]
    y, mo, d = (int(x) for x in feed["date"].split("-"))
    fecha = f"{d} {MESES[mo - 1]}. {y}"
    out = re.sub(r"(catálogo al |onsultado el )\d{1,2} [a-z]{3,4}\. \d{4}", r"\g<1>" + fecha, out)
    dig = feed.get("digevo") or feed["ready"]
    out = re.sub(r"tiene [\d.]+ juegos, y coinciden uno a uno con los [\d.]+ “listos",
                 f"tiene {fmt_int(dig)} juegos, y coinciden uno a uno con los "
                 f"{fmt_int(feed['ready'])} “listos", out)
    fuera = sum(1 for r in rows if r[1] != "R")
    out = re.sub(r"unos [\d.]+ cooperativos", f"unos {fmt_int(round(fuera, -1))} cooperativos", out)
    open(out_path, "w", encoding="utf-8").write(out)

    # Reporte
    def dg(rs):
        return sum(1 for r in rs if r[1] == "R" and "DEM" not in r[6])
    L = [f"Datos al {fecha}.",
         f"Cooperativos: {fmt_int(len(rows))} (antes {fmt_int(len(old))}); "
         f"en Digevo sin demos: {dg(rows)} (antes {dg(old)}).",
         f"Catálogo Digevo: {fmt_int(dig)} juegos; NVIDIA listos para jugar: {fmt_int(feed['ready'])}"
         + ("" if dig == feed["ready"] else " (NO coinciden, revisar)") + "."]
    if added:
        L.append("Nuevos: " + "; ".join(
            f"{r[0]}{' (Digevo)' if r[1] == 'R' else ''}" for r in added) + ".")
    if removed:
        L.append("Salieron: " + "; ".join(removed) + ".")
    to_r = [nr[0] for r, nr in pairs if r[1] != "R" and nr[1] == "R"]
    to_i = [nr[0] for r, nr in pairs if r[1] == "R" and nr[1] != "R"]
    if to_r:
        L.append("Entraron a Digevo: " + "; ".join(to_r) + ".")
    if to_i:
        L.append("Salieron de Digevo: " + "; ".join(to_i) + ".")
    gp_add = [nr[0] for r, nr in pairs if not r[15] and nr[15]] + [r[0] for r in added if r[15]]
    gp_del = [nr[0] for r, nr in pairs if r[15] and not nr[15]]
    L.append(f"Game Pass: {sum(1 for r in rows if r[15])} juegos"
             + (f"; entran {', '.join(gp_add)}" if gp_add else "")
             + (f"; salen {', '.join(gp_del)}" if gp_del else "") + ".")
    changed = sum(1 for r, nr in pairs if (r[11], r[13]) != (nr[11], nr[13]))
    starts = sorted([nr for r, nr in pairs if not r[13] and nr[13] and nr[1] == "R"],
                    key=lambda r: (-r[13], -r[8]))
    ends = sorted([(r, nr) for r, nr in pairs if r[13] and not nr[13] and nr[1] == "R"],
                  key=lambda x: -x[1][8])
    L.append(f"Precios que cambiaron: {changed}. En oferta ahora: "
             f"{sum(1 for r in rows if r[13])} ({sum(1 for r in rows if r[13] and r[1] == 'R')} en Digevo).")
    if starts:
        L.append("Ofertas nuevas en Digevo (top): " + "; ".join(
            f"{r[0]} {cop(r[11])} (−{r[13]} %)" for r in starts[:8]) + ".")
    if ends:
        L.append("Ofertas que terminaron en Digevo (top): " + "; ".join(
            f"{nr[0]} vuelve a {cop(nr[11])} (estaba a {cop(r[11])})" for r, nr in ends[:6]) + ".")
    open(report_path, "w", encoding="utf-8").write("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    if len(sys.argv) != 5:
        sys.exit(__doc__)
    main(*sys.argv[1:])
