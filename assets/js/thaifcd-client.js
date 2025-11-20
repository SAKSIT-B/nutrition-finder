const WORKER_BASE = "https://nutrition-thaifcd-proxy.skst-b13.workers.dev/"; // ← ใส่ของคุณ

// แปลงตารางผลค้นหาให้เป็นรายการ {name, group, type, detail_url}
export async function searchThaiFCD(keyword){
  const res = await fetch(`${WORKER_BASE}/api/search?keyword=${encodeURIComponent(keyword)}`);
  const html = await res.text();
  return parseSearchHTML(html);
}

// ดึงหน้ารายละเอียดแล้วแปลงเป็น { name, group, basis, sections:{Main nutrients, Minerals, Vitamins}, source_url }
export async function fetchDetail(urlOrPath){
  const u = encodeURIComponent(urlOrPath);
  const res = await fetch(`${WORKER_BASE}/api/detail?url=${u}`);
  const html = await res.text();
  return parseDetailHTML(html, urlOrPath);
}

/* ---------- PARSERS ---------- */
function parseHTML(html){
  const dom = new DOMParser().parseFromString(html, "text/html");
  return dom;
}

export function parseSearchHTML(html){
  const doc = parseHTML(html);
  const table = doc.querySelector("table");
  const rows = [];
  if(!table) return rows;
  const trs = Array.from(table.querySelectorAll("tr")).slice(1);
  for(const tr of trs){
    const tds = tr.querySelectorAll("td");
    if(tds.length < 3) continue;
    const a = tr.querySelector("a[href]");
    const href = a ? a.getAttribute("href") : null;
    rows.push({
      name: tds[0].textContent.trim(),
      group: tds[1].textContent.trim(),
      type: tds[2].textContent.trim(),
      detail_url: href ? new URL(href, "https://thaifcd.anamai.moph.go.th").toString() : null,
    });
  }
  return rows;
}

export function parseDetailHTML(html, sourceUrl){
  const doc = parseHTML(html);

  const title = (doc.querySelector("h1, h2")?.textContent || "").trim() || "(ไม่พบชื่อ)";

  // กลุ่มอาหาร
  let group = null;
  const texts = doc.body.innerText || "";
  const m = texts.match(/กลุ่มอาหาร\s*:\s*([^\n(]+)/);
  if (m) group = m[1].trim();

  // basis: “ปริมาณอาหาร ต่อ 100 กรัม/มล”
  let basis = { amount: 100, unit: "g" };
  const m2 = texts.match(/ปริมาณอาหาร\s*ต่อ\s*([\d\.]+)\s*(กรัม|ก|g|มล|ml)/i);
  if (m2){
    basis.amount = Number(m2[1]);
    const u = m2[2].toLowerCase();
    basis.unit = (u==="มล"||u==="ml") ? "ml" : "g";
  }

  const sections = { "Main nutrients": {}, "Minerals": {}, "Vitamins": {} };
  let cur = null;
  const table = doc.querySelector("table");
  if (table){
    for (const tr of table.querySelectorAll("tr")){
      const cells = tr.querySelectorAll("th,td");
      if (!cells.length) continue;

      if (cells.length === 1 || (cells[0].tagName==="TH" && cells[0].hasAttribute("colspan"))){
        const sec = cells[0].textContent.trim();
        if (["Main nutrients","Minerals","Vitamins"].includes(sec)) cur = sec;
        continue;
      }
      if (cells.length < 3) continue;

      const head = cells[0].textContent.trim();
      const amt  = cells[1].textContent.trim();
      const unit = cells[2].textContent.trim();

      const map = mapHeaderToSiteKey(head, cur);
      if (map && cur){
        sections[cur][map] = { amount: amt, unit: unit || null };
      }
    }
  }

  return {
    name: title,
    group,
    basis,
    sections,
    source_url: sourceUrl
  };
}

/* mapping หัวตาราง → คีย์มาตรฐานเหมือนหน้าต้นทาง */
function mapHeaderToSiteKey(head, section){
  const h = head.toLowerCase();
  const eq = (s) => h === s;
  // Main nutrients
  if (eq("energy") || head==="Energy") return "Energy";
  if (eq("water")  || head==="Water")  return "Water";
  if (eq("protein")|| head==="Protein")return "Protein";
  if (eq("fat")    || head==="Fat")    return "Fat";
  if (h.startsWith("carbohydrate"))    return "Carbohydrate";
  if (h.includes("dietary fibre")||h.includes("dietary fiber")) return "Dietary fibre";
  if (eq("ash")) return "Ash";

  // Minerals
  if (eq("sodium")) return "Sodium";
  if (eq("potassium")) return "Potassium";
  if (eq("calcium")) return "Calcium";
  if (eq("iron")) return "Iron";
  if (eq("iodine")) return "Iodine";
  // ...เติมได้ตามที่คุณต้องการ

  // Vitamins
  if (eq("retinol")) return "Retinol";
  if (h.includes("total vitamin a")) return "Total vitamin A (RAE)";
  if (eq("thiamin")||eq("thiamine")) return "Thiamin";
  if (eq("riboflavin")) return "Riboflavin";
  if (eq("niacin")) return "Niacin";
  if (eq("vitamin e")) return "Vitamin E";
  // ...เติม mapping เพิ่มได้

  // ถ้าไม่รู้จัก ให้คืน null เพื่อลงใน extras ได้ถ้าต้องการ
  return null;
}

