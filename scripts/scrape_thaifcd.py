# scripts/scrape_thaifcd.py
# -*- coding: utf-8 -*-
"""
ดึงรายการจาก ThaiFCD แล้วแปลงเป็น data/ingredients.json
- ไม่คำนวณ/ไม่แก้ค่า → เก็บค่าตามหน้าเว็บ (amount+unit)
- ใช้ชื่อสารอาหาร/หัวข้อ section ให้เหมือนเว็บ 100%
"""
import time, json, re
from pathlib import Path
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup
from nutrients_map_site import map_header_to_site_key

BASE     = "https://thaifcd.anamai.moph.go.th/nss/"
SEARCH   = urljoin(BASE, "search.php")
HEADERS  = {"User-Agent": "Mozilla/5.0 (compatible; NutritionFinder/1.0; +github-pages)"}
TIMEOUT  = 30
DELAY_SEC = 1.5

# คีย์เวิร์ดตัวอย่าง (เพิ่ม/ลดได้)
KEYWORDS = ["ข้าว", "ปลา", "กุ้ง", "หมู", "ไก่", "นม", "ผัก", "ผลไม้", "เต้าหู้", "ซีอิ๊ว", "น้ำปลา", "กะทิ"]

OUT_PATH = Path("data/ingredients.json")

session = requests.Session()
session.headers.update(HEADERS)

def get(url, params=None):
    r = session.get(url, params=params, timeout=TIMEOUT)
    r.raise_for_status()
    return r

def extract_search_rows(html):
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table")
    items = []
    if not table:
        return items
    for tr in table.select("tr")[1:]:
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
    """
    หา "ปริมาณอาหาร ต่อ 100 กรัม/มล." → {"amount":100,"unit":"g"} (ถ้าไม่เจอ คืนค่าว่าง)
    """
    basis = {"amount": None, "unit": None}
    text = soup.get_text(" ", strip=True)
    m = re.search(r"ปริมาณอาหาร\s*ต่อ\s*([\d\.]+)\s*([กมล]\.?|g|ml|กรัม|มล)", text, flags=re.I)
    if m:
        try:
            basis["amount"] = float(m.group(1))
        except:
            pass
        u = m.group(2).lower().replace(".", "")
        basis["unit"] = "g" if u in ("ก","กรัม","g") else ("ml" if u in ("มล","ml") else u)
    return basis

def parse_detail_page(html, url):
    soup = BeautifulSoup(html, "html.parser")

    # ชื่อรายการ
    title_el = soup.find(["h1","h2"])
    item_name = title_el.get_text(strip=True) if title_el else "(ไม่พบชื่อ)"

    # กลุ่มอาหาร (ถ้ามี)
    group_text = None
    gnode = soup.find(string=re.compile(r"กลุ่มอาหาร"))
    if gnode:
        p = gnode.find_parent()
        if p:
            m = re.search(r"กลุ่มอาหาร.*?:\s*([^(|]+)", p.get_text(" ", strip=True))
            if m:
                group_text = m.group(1).strip()

    basis = parse_basis(soup)

    main, minerals, vitamins, extras = {}, {}, {}, {}
    cur_section = None
    table = soup.find("table")
    if table:
        for tr in table.find_all("tr"):
            cells = tr.find_all(["th","td"])
            if not cells:
                continue
            # แถวหัว section
            if len(cells) == 1 or (cells[0].name == "th" and cells[0].get("colspan")):
                sec_name = cells[0].get_text(strip=True)
                if sec_name in ("Main nutrients","Minerals","Vitamins"):
                    cur_section = sec_name
                continue
            if len(cells) < 3:
                continue
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
                if head:
                    extras[head] = value

    return {
        "name": item_name,
        "group": group_text,
        "basis": basis,   # เช่น {"amount":100,"unit":"g"}
        "sections": {
            "Main nutrients": main,
            "Minerals": minerals,
            "Vitamins": vitamins
        },
        "extras": extras,  # คอลัมน์ที่ไม่เข้ากลุ่มด้านบน เก็บไว้เพื่ออ้างอิง
        "source_url": url,
        "attribution": "ข้อมูลจาก ThaiFCD (กรมอนามัย กระทรวงสาธารณสุข) – ใช้เพื่อการศึกษา/อ้างอิง โดยให้เครดิตแหล่งที่มา"
    }

def scrape_keyword(keyword):
    print(f"[+] keyword: {keyword}")
    res = get(SEARCH, params={"keyword": keyword})
    rows = extract_search_rows(res.text)
    time.sleep(DELAY_SEC)

    items = []
    for r in rows:
        if not r.get("detail_url"):
            continue
        try:
            d = get(r["detail_url"])
            item = parse_detail_page(d.text, d.url)
            # เติม type จากหน้าลิสต์ (ถ้ามี)
            item["type"] = r.get("type")
            items.append(item)
        except Exception:
            pass
        time.sleep(DELAY_SEC)
    return items

def main():
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    all_items, seen = [], set()
    for kw in KEYWORDS:
        for it in scrape_keyword(kw):
            key = (it["name"], it["source_url"])
            if key in seen:   # กันซ้ำ
                continue
            seen.add(key)
            all_items.append(it)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(all_items, f, ensure_ascii=False, indent=2)
    print(f"Saved {len(all_items)} items -> {OUT_PATH}")

if __name__ == "__main__":
    main()
