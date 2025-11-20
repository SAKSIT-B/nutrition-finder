# scripts/scrape_thaifcd.py
# -*- coding: utf-8 -*-
"""
Scrape ThaiFCD -> data/ingredients.json (atomic write)
- ถ้าดึงไม่ได้เลย: ไม่เขียนทับไฟล์เดิม และ exit 0 เพื่อไม่ทำให้ workflow แดง
- เก็บ key/section ตามหน้าเว็บจริง (Main nutrients, Minerals, Vitamins)
"""
import os, time, json, re, random, sys
from pathlib import Path
from urllib.parse import urljoin

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup

from nutrients_map_site import map_header_to_site_key

BASE   = "https://thaifcd.anamai.moph.go.th/nss/"
SEARCH = urljoin(BASE, "search.php")

# --- Network settings (เพิ่มเวลาให้เยอะขึ้น) ---
CONNECT_TIMEOUT = float(os.getenv("CONNECT_TIMEOUT", "30"))
READ_TIMEOUT    = float(os.getenv("READ_TIMEOUT", "120"))
TIMEOUT = (CONNECT_TIMEOUT, READ_TIMEOUT)

MAX_TOTAL_RETRIES = int(os.getenv("MAX_TOTAL_RETRIES", "6"))
BACKOFF_FACTOR    = float(os.getenv("BACKOFF_FACTOR", "2.0"))
STATUS_FORCELIST  = [429, 500, 502, 503, 504]
ALLOWED_METHODS   = frozenset({"GET"})

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) NutritionFinder/1.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

DEFAULT_KEYWORDS = ["ข้าว","ปลา","กุ้ง","หมู","ไก่","นม","ผัก","ผลไม้","เต้าหู้","ซีอิ๊ว","น้ำปลา","กะทิ"]
_env_keywords = [s.strip() for s in os.getenv("KEYWORDS","").split(",") if s.strip()]
KEYWORDS = _env_keywords or DEFAULT_KEYWORDS

OUT_PATH = Path("data/ingredients.json")
TMP_PATH = Path("data/ingredients.json.tmp")
OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

def sleep_jitter(base=2.0, spread=2.0):
    time.sleep(base + random.random()*spread)

def build_session():
    s = requests.Session()
    s.headers.update(HEADERS)
    retry = Retry(
        total=MAX_TOTAL_RETRIES,
        connect=MAX_TOTAL_RETRIES,
        read=MAX_TOTAL_RETRIES,
        backoff_factor=BACKOFF_FACTOR,
        status_forcelist=STATUS_FORCELIST,
        allowed_methods=ALLOWED_METHODS,
        raise_on_status=False,
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    return s

session = build_session()

def get(url, params=None):
    r = session.get(url, params=params, timeout=TIMEOUT)
    r.raise_for_status()
    return r

def extract_search_rows(html):
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table")
    items = []
    if not table: return items
    trs = table.select("tr")
    for tr in trs[1:]:
        tds = tr.find_all("td")
        if len(tds) < 3: 
            continue
        name  = tds[0].get_text(strip=True)
        group = tds[1].get_text(strip=True)
        ftype = tds[2].get_text(strip=True)
        a = tr.find("a", href=True)
        detail = urljoin(BASE, a["href"]) if a else None
        items.append({"name": name, "group": group, "type": ftype, "detail_url": detail})
    return items

def parse_basis(soup):
    basis = {"amount": None, "unit": None}
    text = soup.get_text(" ", strip=True)
    m = re.search(r"ปริมาณอาหาร\s*ต่อ\s*([\d\.]+)\s*([กมล]\.?|g|ml|กรัม|มล)", text, flags=re.I)
    if m:
        try: basis["amount"] = float(m.group(1))
        except: pass
        u = m.group(2).lower().replace(".","")
        basis["unit"] = "g" if u in ("ก","กรัม","g") else ("ml" if u in ("มล","ml") else u)
    return basis

def parse_detail_page(html, url):
    soup = BeautifulSoup(html, "html.parser")
    title_el = soup.find(["h1","h2"])
    item_name = title_el.get_text(strip=True) if title_el else "(ไม่พบชื่อ)"

    group_text = None
    gnode = soup.find(string=re.compile(r"กลุ่มอาหาร"))
    if gnode:
        p = gnode.find_parent()
        if p:
            m = re.search(r"กลุ่มอาหาร.*?:\s*([^(|]+)", p.get_text(" ", strip=True))
            if m: group_text = m.group(1).strip()

    basis = parse_basis(soup)

    main, minerals, vitamins, extras = {}, {}, {}, {}
    cur_section = None
    table = soup.find("table")
    if table:
        for tr in table.find_all("tr"):
            cells = tr.find_all(["th","td"])
            if not cells: continue
            # section header
            if len(cells) == 1 or (cells[0].name == "th" and cells[0].get("colspan")):
                sec_name = cells[0].get_text(strip=True)
                if sec_name in ("Main nutrients","Minerals","Vitamins"):
                    cur_section = sec_name
                continue
            if len(cells) < 3: continue

            head = cells[0].get_text(" ", strip=True)
            amt  = cells[1].get_text(" ", strip=True)
            unit = cells[2].get_text(" ", strip=True)

            site_key, mapped_sec = map_header_to_site_key(head)
            section = mapped_sec or cur_section
            value = {"amount": amt, "unit": unit or None}

            if site_key and section == "Main nutrients":
                main[site_key] = value
            elif site_key and section == "Minerals":
                minerals[site_key] = value
            elif site_key and section == "Vitamins":
                vitamins[site_key] = value
            else:
                if head: extras[head] = value

    return {
        "name": item_name,
        "group": group_text,
        "basis": basis,
        "sections": {
            "Main nutrients": main,
            "Minerals": minerals,
            "Vitamins": vitamins
        },
        "extras": extras,
        "source_url": url,
        "attribution": "ข้อมูลจาก ThaiFCD (กรมอนามัย กระทรวงสาธารณสุข) – ใช้เพื่อการศึกษา/อ้างอิง โดยให้เครดิตแหล่งที่มา"
    }

def scrape_keyword(keyword):
    print(f"[+] keyword: {keyword}", flush=True)
    try:
        res = get(SEARCH, params={"keyword": keyword})
    except Exception as e:
        print(f"[!] search failed for '{keyword}': {e}", file=sys.stderr)
        return []

    rows = extract_search_rows(res.text)
    sleep_jitter()

    items = []
    for r in rows:
        if not r.get("detail_url"): continue
        try:
            d = get(r["detail_url"])
            item = parse_detail_page(d.text, d.url)
            item["type"] = r.get("type")
            items.append(item)
        except Exception as e:
            print(f"[!] detail failed: {r.get('detail_url')} : {e}", file=sys.stderr)
        sleep_jitter()
    return items

def main():
    all_items, seen = [], set()

    # preflight: ถ้าฐานไม่ติด อย่าล้มงาน
    try:
        _ = get(BASE)
    except Exception as e:
        print(f"[!] preflight warning: base not reachable now: {e}", file=sys.stderr)

    for kw in KEYWORDS:
        batch = scrape_keyword(kw)
        for it in batch:
            key = (it["name"], it["source_url"])
            if key in seen: 
                continue
            seen.add(key); all_items.append(it)

        # incremental save
        TMP_PATH.write_text(json.dumps(all_items, ensure_ascii=False, indent=2), encoding="utf-8")
        TMP_PATH.replace(OUT_PATH)

    if len(all_items) == 0:
        # ไม่มีข้อมูลใหม่เลย -> ไม่เขียนทับไฟล์เดิม (ถ้ามี) และจบแบบ exit 0
        if TMP_PATH.exists():
            try: TMP_PATH.unlink()
            except: pass
        print("[!] No items scraped. Keep previous data/ingredients.json as-is.")
        sys.exit(0)

    print(f"Saved {len(all_items)} items -> {OUT_PATH}")
    sys.exit(0)

if __name__ == "__main__":
    main()
