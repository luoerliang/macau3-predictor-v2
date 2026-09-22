import os, re, sqlite3, threading, time
from datetime import datetime, timezone
from flask import Flask, jsonify, render_template_string
import requests
from bs4 import BeautifulSoup
from collections import Counter

app = Flask(__name__)
DB = "draws.db"
SOURCE = "https://macaujc.com/open_video3/"

HTML = r"""<!doctype html><html lang="zh-CN"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>澳门六合彩3分分析</title>
<style>
body{margin:0;background:#f5f5f7;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:#222}
main{max-width:760px;margin:auto;padding:16px}.card{background:#fff;border-radius:18px;padding:18px;margin:12px 0;box-shadow:0 2px 12px #0001}
h1{margin:0 0 5px;font-size:24px}.muted{color:#777;font-size:13px}.balls{display:flex;flex-wrap:wrap;gap:8px}.ball{width:42px;height:42px;border-radius:50%;display:grid;place-items:center;background:#eee;font-weight:700}
button{background:#111;color:#fff;border:0;border-radius:12px;padding:11px 15px}.grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}.big{font-size:22px;font-weight:700}
table{width:100%;border-collapse:collapse;font-size:13px}td,th{padding:8px;border-bottom:1px solid #eee;text-align:left}
.notice{background:#fff7dc;padding:12px;border-radius:12px;font-size:13px}
</style></head><body><main>
<div class="card"><h1>🎯 澳门六合彩3分分析</h1><div class="muted">自动同步 · 统计 · 历史回测（原型）</div><p><button onclick="sync()">立即同步</button> <span id="status"></span></p></div>
<div class="card"><h2>最新开奖</h2><div id="latest">加载中…</div></div>
<div class="card"><h2>📊 统计候选</h2><div class="notice">以下为历史频率评分，不是中奖概率，也不保证下一期结果。</div><p id="cand">加载中…</p></div>
<div class="card"><h2>历史记录</h2><div style="overflow:auto"><table><thead><tr><th>期号</th><th>时间</th><th>正码</th><th>特码</th></tr></thead><tbody id="history"></tbody></table></div></div>
</main>
<script>
async function load(){
 const d=await (await fetch('/api/data')).json();
 if(!d.draws.length){document.getElementById('latest').textContent='暂未抓到数据';return}
 const x=d.draws[0];
 document.getElementById('latest').innerHTML=`<div class="grid"><div><div class="muted">期号</div><div class="big">${x.issue}</div></div><div><div class="muted">开奖时间</div>${x.time}</div></div><p>正码</p><div class="balls">${x.main.map(n=>`<span class="ball">${String(n).padStart(2,'0')}</span>`).join('')}</div><p>特码</p><div class="balls"><span class="ball">${String(x.special).padStart(2,'0')}</span></div>`;
 document.getElementById('cand').innerHTML=d.scores.slice(0,10).map(x=>`<span class="ball" style="display:inline-grid;margin:3px">${String(x.n).padStart(2,'0')}</span>`).join('');
 document.getElementById('history').innerHTML=d.draws.slice(0,50).map(x=>`<tr><td>${x.issue}</td><td>${x.time}</td><td>${x.main.map(n=>String(n).padStart(2,'0')).join(' ')}</td><td>${String(x.special).padStart(2,'0')}</td></tr>`).join('');
}
async function sync(){document.getElementById('status').textContent='同步中…';let r=await fetch('/api/sync');let d=await r.json();document.getElementById('status').textContent=d.ok?`已解析 ${d.parsed} 条`:`失败：${d.error}`;load()}
load();setInterval(load,30000);
</script></body></html>"""

def conn():
    c=sqlite3.connect(DB)
    c.execute("""CREATE TABLE IF NOT EXISTS draws(
      issue TEXT PRIMARY KEY, draw_time TEXT,
      n1 INTEGER,n2 INTEGER,n3 INTEGER,n4 INTEGER,n5 INTEGER,n6 INTEGER,
      special INTEGER, fetched_at TEXT)""")
    c.commit()
    return c

def parse():
    r=requests.get(SOURCE,headers={"User-Agent":"Mozilla/5.0"},timeout=20)
    r.raise_for_status()
    soup=BeautifulSoup(r.text,"html.parser")
    text=" ".join(soup.stripped_strings)
    pat=re.compile(r"第\s*(20\d{7,})\s*期\s*(20\d{2}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})")
    found=[]
    positions=[m for m in pat.finditer(text)]
    for i,m in enumerate(positions):
        block=text[m.end():positions[i+1].start() if i+1<len(positions) else m.end()+500]
        nums=[int(x) for x in re.findall(r"(?<!\d)(0?[1-9]|[1-4]\d)(?!\d)",block)]
        if len(nums)>=7:
            found.append((m.group(1),m.group(2),nums[:7]))
    return found

def sync():
    try:
        rows=parse()
        c=conn()
        for issue,dt,ns in rows:
            c.execute("""INSERT OR REPLACE INTO draws
              VALUES(?,?,?,?,?,?,?,?,?,?)""",
              (issue,dt,*ns,datetime.now(timezone.utc).isoformat()))
        c.commit(); c.close()
        return len(rows),None
    except Exception as e:
        return 0,str(e)

def data():
    c=conn()
    rows=c.execute("SELECT issue,draw_time,n1,n2,n3,n4,n5,n6,special FROM draws ORDER BY issue DESC").fetchall()
    c.close()
    return rows

def scores(rows):
    c=Counter()
    for row in rows[:100]:
        c.update(row[2:9])
    return sorted([(n,c[n]) for n in range(1,50)], key=lambda x:(-x[1],x[0]))

def background():
    while True:
        sync()
        time.sleep(45)

@app.get("/")
def home():
    return render_template_string(HTML)

@app.get("/api/sync")
def api_sync():
    n,e=sync()
    return jsonify({"ok":e is None,"parsed":n,"error":e})

@app.get("/api/data")
def api_data():
    rows=data()
    s=scores(rows)
    out=[]
    for r in rows:
        out.append({"issue":r[0],"time":r[1],"main":list(r[2:8]),"special":r[8]})
    return jsonify({"draws":out,"scores":[{"n":n,"score":v} for n,v in s]})

threading.Thread(target=background,daemon=True).start()

if __name__ == "__main__":
    port=int(os.environ.get("PORT","5000"))
    app.run(host="0.0.0.0",port=port)
