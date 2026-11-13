"""TİTCK Ruhsatlı Beşeri Tıbbi Ürünler Listesi'nden index.html içindeki ilaç sözlüğünü günceller.

Kullanım:  python tools/update_titck.py index.html
Yalnızca Python standart kütüphanesi kullanır. Liste beklenenden küçükse veya
indirilemezse hata verip çıkar; sayfa değiştirilmez.
"""
import collections, io, json, re, sys, urllib.request, zipfile
import xml.etree.ElementTree as ET

PAGE = "https://www.titck.gov.tr/dinamikmodul/85"
UA = "Mozilla/5.0 (compatible; sigarabirakma-site-updater)"
MIN_PRODUCTS = 15000


def get(url, timeout=120):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "tr"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def latest_xlsx():
    html = get(PAGE).decode("utf-8", "ignore")
    found = {}
    for m in re.finditer(r'storage/[^"\']*?RuhsatlBeeriTbbirnlerListesi(\d{2})\.(\d{2})\.(\d{4})_[^"\']*?\.xlsx', html):
        d, mo, y = m.group(1), m.group(2), m.group(3)
        found[(y, mo, d)] = "https://titck.gov.tr/" + m.group(0)
    if not found:
        sys.exit("TİTCK sayfasında liste bağlantısı bulunamadı")
    key = max(found)
    return found[key], f"{key[2]}.{key[1]}.{key[0]}"


def read_rows(data):
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    z = zipfile.ZipFile(io.BytesIO(data))
    ss = []
    if "xl/sharedStrings.xml" in z.namelist():
        for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", ns):
            ss.append("".join(t.text or "" for t in si.iter("{%s}t" % ns["m"])))

    def col(ref):
        n = 0
        for ch in re.match(r"[A-Z]+", ref).group():
            n = n * 26 + ord(ch) - 64
        return n - 1

    rows = []
    for r in ET.fromstring(z.read("xl/worksheets/sheet1.xml")).iter("{%s}row" % ns["m"]):
        row = {}
        for c in r.findall("m:c", ns):
            v, t = c.find("m:v", ns), c.get("t")
            if t == "inlineStr":
                val = "".join(e.text or "" for e in c.iter("{%s}t" % ns["m"]))
            elif v is None:
                continue
            elif t == "s":
                val = ss[int(v.text)]
            else:
                val = v.text
            row[col(c.get("r"))] = val
        if row:
            rows.append([row.get(i, "") for i in range(max(row) + 1)])
    return rows


def norm(s):
    s = s.replace("İ", "i").replace("I", "ı").lower()
    for a, b in zip("ıığüşöçâîû", "iigusocaiu"):
        s = s.replace(a, b)
    return re.sub(r"\s+", " ", s.replace("\xa0", " ")).strip()


FORM = set("tablet tb tab film kapli kapsul sert yumusak surup enjeksiyonluk enjektabl ampul flakon krem merhem jel pomad damla sprey solusyon cozelti suspansiyon toz granul sase efervesan fort forte plus retard sr xr xl cr la mr ped pediatrik oral iv im inhaler inhalasyon nazal goz kulak vajinal rektal supozituvar ovul transdermal flaster bant pastil sakiz".split())


def build(rows):
    # Başlık satırını bul (SIRA NO, BARKOD, ÜRÜN ADI, ETKİN MADDE, ATC KODU ...)
    start = next(i for i, r in enumerate(rows[:20]) if r and norm(r[0]).startswith("sira")) + 1
    brand, ing, ings, ingidx = collections.defaultdict(set), {}, [], {}
    n = 0
    for r in rows[start:]:
        if len(r) < 5 or not r[2]:
            continue
        name, etk, atc = r[2], r[3].strip(), r[4].replace("\xa0", "").strip()
        if not etk or not atc:
            continue
        k = (etk.lower(), atc)
        if k not in ingidx:
            ingidx[k] = len(ings)
            ings.append([etk.lower(), atc])
        i = ingidx[k]
        n += 1
        toks = norm(name.replace(",", " , ").replace("%", " % ")).split()
        while toks and re.match(r"^[%\d.,/+-]+$", toks[0]):
            toks.pop(0)
        base = []
        for t in toks:
            if re.search(r"\d", t) or t in FORM or t in {",", "-", "(", "/", "%"} or t.startswith("("):
                break
            base.append(t)
        b = re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 -]", " ", " ".join(base[:4]))).strip(" .-/")
        if len(b) >= 3:
            brand[b].add(i)
        e = re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", norm(etk))).strip()
        for key in {e, e.split(" ")[0]}:
            if len(key) >= 4:
                ing.setdefault(key, set()).add(i)
    data = {"I": ings, "B": {k: sorted(v) for k, v in sorted(brand.items())},
            "E": {k: sorted(v)[:3] for k, v in sorted(ing.items())}}
    return json.dumps(data, ensure_ascii=False, separators=(",", ":")), n


def main(path):
    url, date = latest_xlsx()
    print("Liste:", date, url)
    rows = read_rows(get(url, 300))
    data, n = build(rows)
    print("Ürün:", n)
    if n < MIN_PRODUCTS:
        sys.exit(f"Beklenenden az ürün ({n}); sayfa güncellenmedi")
    if "</" in data:
        sys.exit("Veride beklenmeyen '</' dizisi; sayfa güncellenmedi")
    html = open(path, encoding="utf-8").read()
    new, k = re.subn(r'(<script id="titck-data" type="application/json">)[\s\S]*?(</script>)',
                     lambda m: m.group(1) + data + m.group(2), html, count=1)
    if k != 1:
        sys.exit("Sayfada titck-data bloğu bulunamadı")
    count = f"{n:,}".replace(",", ".")
    new = re.sub(r'(<span class="titck-date">)[^<]*(</span>)', lambda m: m.group(1) + date + m.group(2), new)
    new = re.sub(r'(<span class="titck-count">)[^<]*(</span>)', lambda m: m.group(1) + count + m.group(2), new)
    if new == html:
        print("Değişiklik yok")
        return
    open(path, "w", encoding="utf-8", newline="").write(new)
    print("Sayfa güncellendi")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "index.html")
