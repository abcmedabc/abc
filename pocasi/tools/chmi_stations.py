#!/usr/bin/env python3
"""Download the latest 10-minute observations of ČHMÚ stations and write one small JSON.

Output: {"generated": ISO time, "stations": [{id, name, lat, lon, elev, time, T, H, F, Fmax, D, P0, R1h, R10}]}
Values with quality flag 1 (suspect), 2 (poor) or 4 (missing) are left out.
"""
import concurrent.futures as cf, datetime as dt, json, math, re, sys, time, urllib.request

BASE = "https://opendata.chmi.cz/meteorology/climate/now/"
BBOX = (48.4, 51.2, 11.9, 19.0)          # lat min/max, lon min/max (Czechia and edges)
BAD = {1.0, 2.0, 4.0}
ELEMS = ("T", "H", "F", "Fmax", "D", "P", "SRA10M")

def get(url, tries=4):
    for k in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "pocasi-app (github.com/abcmedabc/abc)"}), timeout=30) as r:
                return r.read()
        except Exception as e:
            if k == tries - 1: raise
            time.sleep(1 + 2 * k)

def meta(day):
    for d in (day, day - dt.timedelta(days=1)):
        try:
            j = json.loads(get(BASE + "metadata/meta1-%s.json" % d.strftime("%Y%m%d")))
            out = {}
            for wsi, _gh, name, lon, lat, elev, _b in j["data"]["data"]["values"]:
                if BBOX[0] <= lat <= BBOX[1] and BBOX[2] <= lon <= BBOX[3]:
                    out[wsi] = {"name": name, "lat": round(lat, 5), "lon": round(lon, 5), "elev": elev}
            return out
        except Exception as e:
            print("meta", d, e, file=sys.stderr)
    return {}

def station(fname, now):
    j = json.loads(get(BASE + "data/" + fname))
    last, rain = {}, []
    for wsi, el, t, val, _flag, q in j["data"]["data"]["values"]:
        if el not in ELEMS or val is None or q in BAD: continue
        if el == "SRA10M": rain.append((t, val))
        if el not in last or t > last[el][0]: last[el] = (t, val)
    if "T" not in last: return None
    t = last["T"][0]
    tt = dt.datetime.fromisoformat(t.replace("Z", "+00:00"))
    if (now - tt).total_seconds() > 3 * 3600: return None
    r = {"id": wsi, "time": t}
    for el in ("T", "H", "F", "Fmax", "D"):
        if el in last and last[el][0] == t: r[el] = last[el][1]
    if "P" in last and last["P"][0] == t: r["P"] = last["P"][1]
    hour = [v for (ts, v) in rain if 0 <= (tt - dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))).total_seconds() < 3600]
    if hour: r["R1h"] = round(sum(hour), 1)
    if "SRA10M" in last and last["SRA10M"][0] == t: r["R10"] = last["SRA10M"][1]
    return r

def main(out):
    now = dt.datetime.now(dt.timezone.utc)
    st = meta(now.date())
    html = get(BASE + "data/").decode("utf-8", "replace")
    days = {now.strftime("%Y%m%d")}
    if now.hour < 2: days.add((now - dt.timedelta(days=1)).strftime("%Y%m%d"))
    files = {}
    for wsi, day in re.findall(r'href="10m-(0-[0-9-]+?)-(\d{8})\.json"', html):
        if day in days and wsi in st and (wsi not in files or day > files[wsi][1]): files[wsi] = ("10m-%s-%s.json" % (wsi, day), day)
    res = []
    with cf.ThreadPoolExecutor(12) as ex:
        for f in cf.as_completed({ex.submit(station, fn, now): wsi for wsi, (fn, _d) in files.items()}):
            try:
                r = f.result()
            except Exception as e:
                print("station", e, file=sys.stderr); continue
            if not r: continue
            m = st[r["id"]]; r.update(m)
            if "P" in r and "T" in r:   # station pressure -> sea level
                h = m["elev"] or 0
                r["P0"] = round(r.pop("P") * (1 - 0.0065 * h / (r["T"] + 0.0065 * h + 273.15)) ** -5.257, 1)
            else: r.pop("P", None)
            res.append(r)
    res.sort(key=lambda r: r["id"])
    json.dump({"generated": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "source": "ČHMÚ open data", "stations": res},
              open(out, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print(len(res), "stations from", len(files), "files")

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "chmi.json")
