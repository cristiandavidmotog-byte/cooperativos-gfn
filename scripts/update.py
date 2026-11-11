#!/usr/bin/env python3
"""Recolecta los juegos cooperativos de GeForce NOW (Digevo, Colombia).

Fuentes (todas públicas, solo lectura):
  - NVIDIA: catálogo de GeForce NOW (API GraphQL que usa nvidia.com).
  - Digevo: página del catálogo, solo para comprobar el conteo.
  - Steam: modos de juego, reseñas, precio para Colombia y fechas.
  - Microsoft: catálogo de PC Game Pass para Colombia.

Escribe data/games.json. Solo usa la biblioteca estándar de Python.
"""
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")
NV_URL = "https://api-prod.nvidia.com/services/gfngames/v1/gameList"
STEAM_URL = "https://api.steampowered.com/IStoreBrowseService/GetItems/v1/"
GP_URL = ("https://catalog.gamepass.com/sigls/v2?id=609d944c-d395-4c0a-9ea4-e9f39b52c1ad"
          "&language=es-co&market=CO")
DIGEVO_URL = "https://geforcenow.digevo.com/catalogo/"

GENRES = {"ACTION": "Acc", "ADVENTURE": "Ave", "INDIE": "Ind", "ROLE_PLAYING": "RPG",
          "SIMULATION": "Sim", "STRATEGY": "Est", "CASUAL": "Cas",
          "FIRST_PERSON_SHOOTER": "FPS", "RACING": "Car", "SPORTS": "Dep",
          "MASSIVELY_MULTIPLAYER_ONLINE": "MMO", "PUZZLE": "Puz", "PLATFORMER": "Pla",
          "ARCADE": "Arc", "FAMILY": "Fam", "MULTIPLAYER_ONLINE_BATTLE_ARENA": "MOBA",
          "FIGHTING": "FIG", "DEMO": "DEM"}
STORES = {"STEAM": "St", "EPIC": "Ep", "XBOX": "Xb", "BATTLENET": "Bn", "UPLAY": "Ub",
          "GOG": "Go", "EA_APP": "EA", "GAIJIN": "GAIJIN", "WARGAMING": "WARGAMING"}


def http(url, data=None, headers=None, tries=4, timeout=60):
    h = {"User-Agent": UA, "Accept": "application/json, text/plain, */*"}
    h.update(headers or {})
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, data=data, headers=h)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8")
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"No se pudo leer {url}: {last}")


def clean_title(t):
    t = re.sub(r"[®™©]", "", t or "")
    return re.sub(r"\s+", " ", t).strip()


def nvidia_catalog():
    items, after = [], ""
    for _ in range(40):
        q = ('{ apps(country:"US" language:"en_US" first:500 after:"%s") '
             '{ pageInfo { endCursor hasNextPage } items { id title genres '
             'gfn { playType } variants { appStore storeId } } } }' % after)
        body = http(NV_URL, data=q.encode(), headers={
            "Content-Type": "text/plain;charset=UTF-8",
            "Origin": "https://www.nvidia.com",
            "Referer": "https://www.nvidia.com/"})
        j = json.loads(body)
        apps = (j.get("data") or {}).get("apps")
        if not apps:
            raise RuntimeError("Respuesta inesperada de NVIDIA: " + body[:300])
        items += apps["items"]
        if not apps["pageInfo"]["hasNextPage"]:
            break
        after = apps["pageInfo"]["endCursor"]
    return items


def digevo_count():
    try:
        html = http(DIGEVO_URL, headers={"Accept": "text/html"})
    except Exception as e:  # noqa: BLE001
        print("Aviso: no se pudo leer Digevo:", e, file=sys.stderr)
        return None
    # La página trae el catálogo como un JSON embebido: un objeto por juego.
    counts = [len(set(re.findall(r'\{"id":"([0-9a-f-]{36})","title":', html))),
              len(re.findall(r'flex flex-col mb-4', html))]
    print("Digevo: conteos", counts, file=sys.stderr)
    best = max(counts)
    # El catálogo tiene más de 2.000 juegos; un conteo bajo significa que la
    # página cambió o se carga con JavaScript, y entonces no se usa.
    return best if best > 1000 else None


def game_pass_ids():
    j = json.loads(http(GP_URL))
    return {x["id"] for x in j if isinstance(x, dict) and x.get("id")}


def steam_items(appids):
    info = {}
    ids = sorted(appids)
    for i in range(0, len(ids), 200):
        inp = {"ids": [{"appid": a} for a in ids[i:i + 200]],
               "context": {"language": "english", "country_code": "CO"},
               "data_request": {"include_reviews": True,
                                "include_all_purchase_options": True,
                                "include_release": True}}
        url = STEAM_URL + "?input_json=" + urllib.parse.quote(json.dumps(inp))
        try:
            j = json.loads(http(url))
        except Exception as e:  # noqa: BLE001
            print("Aviso: lote de Steam falló:", e, file=sys.stderr)
            continue
        for it in (j.get("response") or {}).get("store_items") or []:
            if it.get("success") != 1:
                continue
            rel = it.get("release") or {}
            rv = (it.get("reviews") or {}).get("summary_filtered") or {}
            b = it.get("best_purchase_option")
            pr, po, pd = -1, 0, 0
            if it.get("is_free"):
                pr = 0
            elif b and b.get("final_price_in_cents") is not None:
                pr = round(int(b["final_price_in_cents"]) / 100)
                if b.get("discount_pct"):
                    po = round(int(b.get("original_price_in_cents") or 0) / 100)
                    pd = int(b["discount_pct"])
            first = (rel.get("original_release_date") or rel.get("original_steam_release_date")
                     or rel.get("steam_release_date") or 0)
            v1 = rel.get("release_from_early_access_date") or 0
            info[it["appid"]] = {
                "c": (it.get("categories") or {}).get("supported_player_categoryids") or [],
                "f": 1 if it.get("is_free") else 0,
                "pct": rv.get("percent_positive", -1) if rv.get("review_count") else -1,
                "rn": rv.get("review_count") or 0,
                "pr": pr, "po": po, "pd": pd,
                "rel": first // 86400 if first else 0,
                "v1": v1 // 86400 if v1 and v1 > first + 86400 * 30 else 0,
            }
        time.sleep(1)
    return info


def coop_kind(cats):
    s = set(cats)
    if 38 in s:
        return "E"
    if 20 in s:
        return "M"
    if 9 in s and 39 not in s and 48 not in s:
        return "U"
    return None


def main():
    apps = nvidia_catalog()
    if len(apps) < 3000:
        sys.exit(f"Catálogo de NVIDIA sospechosamente corto ({len(apps)}); no se guarda nada.")
    ready = sum(1 for a in apps if (a.get("gfn") or {}).get("playType") == "READY_TO_PLAY")
    by_sid = {}
    for a in apps:
        sid = next((v["storeId"] for v in a["variants"] if v["appStore"] == "STEAM"), None)
        if not sid or not str(sid).isdigit():
            continue
        by_sid.setdefault(int(sid), []).append(a)
    info = steam_items(by_sid.keys())
    if len(info) < 0.8 * len(by_sid):
        sys.exit(f"Steam respondió muy pocos juegos ({len(info)}/{len(by_sid)}); no se guarda nada.")
    gp = game_pass_ids()
    games = []
    for sid, rs in by_sid.items():
        x = info.get(sid)
        if not x:
            continue
        k = coop_kind(x["c"])
        if not k:
            continue
        r = next((q for q in rs if (q.get("gfn") or {}).get("playType") == "READY_TO_PLAY"), rs[0])
        xbox = {v["storeId"] for q in rs for v in q["variants"] if v["appStore"] == "XBOX"}
        stores = []
        for q in rs:
            for v in q["variants"]:
                s = STORES.get(v["appStore"])
                if s and s not in stores:
                    stores.append(s)
        genres = []
        for g in r.get("genres") or []:
            s = GENRES.get(g)
            if s and s not in genres:
                genres.append(s)
        games.append({
            "t": clean_title(r["title"]),
            "p": "R" if any((q.get("gfn") or {}).get("playType") == "READY_TO_PLAY" for q in rs) else "I",
            "k": k, "f": x["f"], "st": stores, "g": genres,
            "pct": x["pct"], "rn": x["rn"], "rel": x["rel"], "v1": x["v1"],
            "pr": x["pr"], "po": x["po"], "pd": x["pd"], "aid": sid,
            "gp": 1 if xbox & gp else 0,
        })
    games.sort(key=lambda g: g["aid"])
    now = datetime.now(timezone(timedelta(hours=-5)))
    out = {"date": now.strftime("%Y-%m-%d"), "nvidia_total": len(apps), "ready": ready,
           "digevo": digevo_count(), "gamepass_ids": len(gp), "games": games}
    with open("data/games.json", "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, separators=(",", ":"))
    print(f"OK {out['date']}: {len(games)} cooperativos, {ready} listos para jugar, "
          f"Digevo {out['digevo']}, Game Pass {len(gp)}")


if __name__ == "__main__":
    main()
