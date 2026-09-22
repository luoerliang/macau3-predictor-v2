
import os, re, sqlite3, threading, time, json
from datetime import datetime
from collections import Counter
from flask import Flask, jsonify, render_template_string
import requests
from bs4 import BeautifulSoup

app = Flask(__name__)
DB = os.path.join(os.path.dirname(__file__), "draws.db")

SOURCE_URLS = [
    "https://macaujc.com/open_video3/",
    "https://macaujc.com/macaujc3/",
]
READER_URLS = [
    "https://r.jina.ai/https://macaujc.com/open_video3/",
    "https://r.jina.ai/https://macaujc.com/macaujc3/",
]
UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Version/17.0 Mobile/15E148 Safari/604.1"
HEADERS = {"User-Agent": UA, "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}

HTML = """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>澳门六合彩3分分析</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#f5f7fb;color:#172033;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
.wrap{max-width:760px;margin:auto;padding:16px}.hero{background:#111827;color:#fff;border-radius:20px;padding:20px}
h1{font-size:24px;margin:0 0 7px}.sub{opacity:.78;font-size:13px;line-height:1.6}.btn{margin-top:14px;border:0;border-radius:12px;padding:12px 16px;background:#fff;color:#111827;font-size:15px;font-weight:700}
.card{background:#fff;border-radius:18px;padding:16px;margin-top:12px;box-shadow:0 3px 14px #0000000a}.title{font-weight:800;margin-bottom:10px}.muted{color:#6b7280;font-size:13px}
.latest{font-size:18px;font-weight:800}.nums{display:flex;gap:7px;flex-wrap:wrap;margin-top:10px}.ball{width:38px;height:38px;border-radius:50%;display:flex;align-items:center;justify-content:center;background:#eef2ff;font-weight:800}
table{width:100%;border-collapse:collapse;font-size:13px}td,th{padding:9px 4px;border-bottom:1px solid #edf0f5;text-align:left}th{color:#6b7280}.tag{display:inline-block;background:#f0fdf4;border-radius:9px;padding:5px 8px;margin:3px;font-weight:700}.status{margin-top:10px;font-size:13px;line-height:1.5}
</style></head><body><div class="wrap">
<div class="hero"><h1>🎯 澳门六合彩3分分析</h1><div class="sub">自动同步 · 历史统计 · 简单回测<br>数据源固定为“澳门六合彩3分”，不混入普通澳门六合彩。</div>
<button class="btn" onclick="sync()">立即同步</button><div id="status" class="status">准备就绪</div></div>
<div class="card"><div class="title">最新开奖</div><div id="latest" class="muted">加载中…</div></div>
<div class="card"><div class="title">统计候选</div><div class="muted">按历史出现次数排序，仅作统计参考，不代表下一期概率。</div><div id="scores">加载中…</div></div>
<div class="card"><div class="title">最近50期</div><div style="overflow:auto"><table><thead><tr><th>期号</th><th>开奖时间</th><th>号码</th></tr></thead><tbody id="history"></tbody></table></div></div>
</div>
<script>
async function load(){
 try{const r=await fetch('/api/data');const d=await r.json();
 let x=d.draws||[];
 document.getElementById('latest').innerHTML=x.length?`第${x[0].issue}期 · ${x[0].time}<div class="nums">${x[0].numbers.map(n=>`<span class="ball">${String(n).padStart(2,'0')}</span>`).join('')}</div>`:'暂未抓到数据';
 document.getElementById('scores').innerHTML=(d.scores||[]).map(x=>`<span class="tag">${String(x[0]).padStart(2,'0')} · ${x[1]}次</span>`).join('')||'暂无统计';
 document.getElementById('history').innerHTML=x.map(r=>`<tr><td>${r.issue}</td><td>${r.time}</td><td>${r.numbers.map(n=>String(n).padStart(2,'0')).join(' ')}</td></tr>`).join('');
 }catch(e){document.getElementById('status').textContent='读取失败：'+e}
}
async function sync(){
 const s=document.getElementById('status');s.textContent='正在同步澳门六合彩3分数据…';
 try{const r=await fetch('/api/sync');const d=await r.json();s.textContent=d.ok?`同步完成：本次解析 ${d.parsed} 条，数据库共 ${d.total} 条。${d.source?'来源：'+d.source:''}`:'同步失败：'+(d.error||'未知错误');await load()}catch(e){s.textContent='同步失败：'+e}
}
load(); setInterval(load,30000);
</script></body></html>"""

def init_db():
    with sqlite3.connect(DB) as c:
        c.execute("""CREATE TABLE IF NOT EXISTS draws(
            issue TEXT PRIMARY KEY,
            draw_time TEXT NOT NULL,
            numbers TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )""")
        c.commit()

def clean_issue(x):
    m = re.search(r"\d{8,}", str(x))
    return m.group(0) if m else None

def clean_numbers(value):
    if isinstance(value, list):
        raw = value
    else:
        raw = re.findall(r"(?<!\d)(?:0?[1-9]|[1-4]\d)(?!\d)", str(value))
    nums = []
    for x in raw:
        try:
            n = int(x)
            if 1 <= n <= 49:
                nums.append(n)
        except:
            pass
    return nums[:7] if len(nums) >= 7 else None

def add_record(found, issue, draw_time, numbers):
    issue = clean_issue(issue)
    numbers = clean_numbers(numbers)
    if not issue or not draw_time or not numbers or len(numbers) != 7:
        return
    # 3分彩期号通常为11位；不强制长度，兼容站点调整。
    found[issue] = (issue, str(draw_time).strip(), numbers)

def parse_structured(text, found):
    # 兼容页面里可能嵌入的 JSON 数据
    for m in re.finditer(r'["\']expect["\']\s*:\s*["\'](\d{8,})["\'].*?["\']openCode["\']\s*:\s*["\']([^"\']+)["\'].*?["\']openTime["\']\s*:\s*["\']([^"\']+)["\']', text, re.S):
        add_record(found, m.group(1), m.group(3), m.group(2))

def parse_text(text, found):
    text = text.replace("\xa0"," ")
    # 每个“第XXXX期”到下一期之间，找日期后的7个号码。
    matches = list(re.finditer(r"第\s*(\d{8,})\s*期", text))
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i+1].start() if i+1 < len(matches) else min(len(text), start+2500)
        block = text[start:end]
        dt = re.search(r"(20\d{2}[-/]\d{1,2}[-/]\d{1,2}\s+\d{1,2}:\d{2}(?::\d{2})?)", block)
        if not dt:
            continue
        after = block[dt.end():]
        # 截断到明显的下一段说明，减少把其他数字带进来
        nums = re.findall(r"(?<!\d)(0?[1-9]|[1-4]\d)(?!\d)", after)
        nums = [int(x) for x in nums[:7]]
        if len(nums) == 7:
            add_record(found, m.group(1), dt.group(1), nums)

def parse_html(raw, found):
    soup = BeautifulSoup(raw, "html.parser")
    parse_structured(raw, found)
    parse_text(" ".join(soup.stripped_strings), found)
    parse_text(soup.get_text(" ", strip=True), found)

def fetch(url):
    r = requests.get(url, headers=HEADERS, timeout=25)
    r.raise_for_status()
    return r.text

def collect():
    found = {}
    errors = []
    for url in SOURCE_URLS:
        try:
            raw = fetch(url)
            parse_html(raw, found)
            if len(found) >= 5:
                return found, url, errors
        except Exception as e:
            errors.append(f"{url}: {e}")
    # 动态页面兜底：使用只读网页转文本服务，不改变数据源。
    for url in READER_URLS:
        try:
            raw = fetch(url)
            parse_text(raw, found)
            parse_structured(raw, found)
            if len(found) >= 5:
                return found, url, errors
        except Exception as e:
            errors.append(f"{url}: {e}")
    return found, "", errors

def save(found):
    now = datetime.utcnow().isoformat(timespec="seconds")
    with sqlite3.connect(DB) as c:
        for issue, dt, nums in found.values():
            c.execute("INSERT OR REPLACE INTO draws(issue,draw_time,numbers,updated_at) VALUES(?,?,?,?)",
                      (issue, dt, json.dumps(nums, ensure_ascii=False), now))
        c.commit()
        total = c.execute("SELECT COUNT(*) FROM draws").fetchone()[0]
    return total

def sync():
    found, source, errors = collect()
    total = save(found) if found else count_rows()
    return found, source, errors, total

def count_rows():
    with sqlite3.connect(DB) as c:
        return c.execute("SELECT COUNT(*) FROM draws").fetchone()[0]

def rows(limit=100):
    with sqlite3.connect(DB) as c:
        data = c.execute("SELECT issue,draw_time,numbers FROM draws ORDER BY draw_time DESC, issue DESC LIMIT ?", (limit,)).fetchall()
    return [{"issue":a,"time":b,"numbers":json.loads(c)} for a,b,c in data]

def score_data():
    rs = rows(100)
    counter = Counter()
    for r in rs:
        counter.update(r["numbers"])
    return sorted(counter.items(), key=lambda x:(-x[1], x[0]))[:12]

@app.route("/")
def index():
    return render_template_string(HTML)

@app.route("/api/data")
def api_data():
    return jsonify({"draws":rows(100), "scores":score_data(), "count":count_rows()})

@app.route("/api/sync")
def api_sync():
    try:
        found, source, errors, total = sync()
        if not found:
            return jsonify({"ok":False,"parsed":0,"total":total,
                            "error":"没有解析到澳门六合彩3分数据。请稍后再试。","details":errors}), 502
        return jsonify({"ok":True,"parsed":len(found),"total":total,"source":source})
    except Exception as e:
        return jsonify({"ok":False,"parsed":0,"total":count_rows(),"error":str(e)}), 500

def background():
    while True:
        try:
            sync()
        except Exception:
            pass
        time.sleep(45)

init_db()
threading.Thread(target=background, daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
