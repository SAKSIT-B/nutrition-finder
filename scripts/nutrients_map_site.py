# scripts/nutrients_map_site.py
import re

# ใช้ชื่อสารอาหาร "ตรงตามเว็บ" เพื่อให้ JSON เหมือนหน้า ThaiFCD
MAIN = {
    r"Energy": "Energy",
    r"Water|Moisture": "Water",
    r"Protein": "Protein",
    r"Fat(?!.*saturated)": "Fat",
    r"Carbohydrate(s)?": "Carbohydrate",
    r"Dietary\s*fibre|Dietary\s*fiber|Fiber": "Dietary fibre",
    r"Ash": "Ash",
}

MINERALS = {
    r"Iodine": "Iodine",
    r"Sodium": "Sodium",
    r"Potassium": "Potassium",
    r"Calcium": "Calcium",
    r"Magnesium": "Magnesium",
    r"Phosphorus": "Phosphorus",
    r"Iron": "Iron",
    r"Zinc": "Zinc",
    r"Copper": "Copper",
    r"Manganese": "Manganese",
    r"Selenium": "Selenium",
}

VITAMINS = {
    r"Retinol": "Retinol",
    r"Total\s*vitamin\s*A\s*\(RAE\)|Vitamin\s*A\s*\(RAE\)": "Total vitamin A (RAE)",
    r"Thiamin(e)?": "Thiamin",
    r"Riboflavin": "Riboflavin",
    r"Niacin": "Niacin",
    r"Vitamin\s*E": "Vitamin E",
    r"Vitamin\s*C|Ascorbic": "Vitamin C",
    r"Vitamin\s*D": "Vitamin D",
    r"Vitamin\s*K": "Vitamin K",
    r"Vitamin\s*B6|Pyridox(ine|al)": "Vitamin B6",
    r"Folate|Folic\s*acid": "Folate",
    r"Vitamin\s*B12|Cobalamin": "Vitamin B12",
    r"Beta-?carotene|β-?carotene": "Beta-carotene",
}

ALL = []
for secname, mapping in (
    ("Main nutrients", MAIN),
    ("Minerals", MINERALS),
    ("Vitamins", VITAMINS),
):
    for pat, site_key in mapping.items():
        ALL.append((re.compile(pat, re.I), site_key, secname))

def map_header_to_site_key(header_text: str):
    """หัวคอลัมน์ → (site_key, section) ตามชื่อบนเว็บ; ไม่เจอคืน (None, None)"""
    h = (header_text or "").strip()
    for pat, site_key, sec in ALL:
        if pat.fullmatch(h):
            return site_key, sec
    return None, None

