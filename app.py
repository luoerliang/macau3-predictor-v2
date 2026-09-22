import os, re, json, sqlite3, threading, time
from datetime import datetime, timedelta
from collections import Counter
from flask import Flask, jsonify, render_template_string
import requests
from bs4 import BeautifulSoup

app = Flask(__name__)
DB = os.path.join(os.path.dirname(__file__), 'draws.db')
UA = 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Version/17.0 Mobile/15E148 Safari/604.1'
HEADERS = {'User-Agent': UA, 'Accept': 'text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8'}
THREE_MIN_PAGE = 'https://macaujc.com/macaujc3/'
THREE_MIN_LIVE = 'https://macaujc.com/open_video3/'
# The site's public API page documents these endpoints, but its examples are ordinary Macau Mark Six.
# We only accept API records whose issue looks like the 3-minute format (YYYYMMDD + 3 digits).
LATEST_API = 'https://macaumarksix.com/api/macaujc2.com'
HISTORY_API = 'https://history.macaumarksix.com/history/macaujc2/expect/{}'
READER = 'https://r.jina.ai/http://macaujc.com/macaujc3/'

HTML = r'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>澳门六合彩3分分析</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#f5f7fb;color:#172033;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}.wrap{max-width:760px;margin:auto;padding:16px}.hero{background:#111827;color:#fff;border-radius:22px;padding:20px}.hero h1{font-size:25px;margin:0 0 8px}.sub{opacity:.8;font-size:13px;line-height:1.7}.btn{margin-top:15px;border:0;border-radius:14px;padding:13px 18px;background:#fff;color:#111827;font-size:16px;font-weight:800}.status{margin-top:12px;font-size:13px;line-height:1.55}.card{background:#fff;border-radius:20px;padding:17px;margin-top:13px;box-shadow:0 3px 16px #0000000a}.title{font-size:20px;font-weight:850;margin-bottom:10px}.muted{color:#6b7280;font-size:13px;line-height:1.6}.latest{font-weight:800}.nums{display:flex;gap:7px;flex-wrap:wrap;margin-top:11px}.ball{width:39px;height:39px;border-radius:50%;display:flex;align-items:center;justify-content:center;background:#eef2ff;font-weight:850}.special{background:#fff3e8}.special-label{font-size:12px;color:#b45309;margin-top:6px}.tags{margin-top:8px}.tag{display:inline-block;background:#f0fdf4;border-radius:10px;padding:6px 9px;margin:3px;font-weight:750}.tag small{font-weight:500;color:#6b7280}.table-wrap{overflow:auto}table{width:100%;border-collapse:collapse;font-size:13px;min-width:560px}td,th{padding:9px 5px;border-bottom:1px solid #edf0f5;text-align:left;vertical-align:top}th{color:#6b7280}.err{color:#b91c1c}.ok{color:#047857}
</style></head><body><div class="wrap">
<div class="hero"><h1>🎯 澳门六合彩3分分析</h1><div class="sub">自动同步 · 历史统计 · 数据回测<br>只处理“澳门六合彩3分”，正码与特码分开保存，不混入普通澳门六合彩。</div>
<button class="btn" onclick="syncNow()">立即同步</button><div id="status" class="status">正在读取…</div></div>
<div class="card"><div class="title">最新开奖</div><div id="latest" class="muted">加载中…</div></div>
<div class="card"><div class="title">统计候选</div><div class="muted">按最近历史的出现次数排序，仅作统计参考，不代表下一期概率或中奖结果。</div><div id="scores" class="tags">加载中…</div></div>
<div class="card"><div class="title">最近50期</div><div class="table-wrap"><table><thead><tr><th>期号</th><th>开奖时间</th><th>正码1-6</th><th>特码</th></tr></thead><tbody id="history"></tbody></table></div></div>
</div>
<script>
let busy=false;
function esc(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
async function load(){try{const r=await fetch('/api/data',{cache:'no-store'});const d=await r.json();const x=d.draws||[];
const latest=document.getElementById('latest');
if(x.length){const a=x[0];latest.innerHTML=`<div>第${esc(a.issue)}期 · ${esc(a.time)}</div><div class="nums">${a.numbers.map((n,i)=>`<span class="ball ${i===6?'special':''}">${String(n).padStart(2,'0')}</span>`).join('')}</div><div class="special-label">特码：${String(a.special).padStart(2,'0')}</div>`;}else latest.textContent='暂未抓到数据';
document.getElementById('scores').innerHTML=(d.scores||[]).map(a=>`<span class="tag">${String(a[0]).padStart(2,'0')} · ${a[1]}次</span>`).join('')||'暂无统计';
document.getElementById('history').innerHTML=x.map(a=>`<tr><td>${esc(a.issue)}</td><td>${esc(a.time)}</td><td>${a.numbers.slice(0,6).map(n=>String(n).padStart(2,'0')).join(' ')}</td><td><b>${String(a.special).padStart(2,'0')}</b></td></tr>`).join('');
}catch(e){document.getElementById('status').textContent='读取失败：'+e}}
async function syncNow(){if(busy)return;busy=true;const s=document.getElementById('status');s.textContent='正在同步澳门六合彩3分…';try{const r=await fetch('/api/sync?ts='+Date.now(),{cache:'no-store'});const d=await r.json();if(d.ok){s.className='status ok';s.textContent=`同步完成：本次新增/更新 ${d.parsed} 条，数据库共 ${d.total} 条。最新：${d.latest||'未知'}`;}else{s.className='status err';s.textContent='同步失败：'+(d.error||'未知错误');}await load()}catch(e){s.className='status err';s.textContent='同步失败：'+e}finally{busy=false}}
load();
// 页面打开时主动同步；这比依赖 Render 免费实例的后台线程可靠。
syncNow();
setInterval(syncNow,30000);
setInterval(load,10000);
</script></body></html>'''


def init_db():
    with sqlite3.connect(DB) as c:
        c.execute('''CREATE TABLE IF NOT EXISTS draws(issue TEXT PRIMARY KEY, draw_time TEXT NOT NULL, numbers TEXT NOT NULL, special INTEGER, updated_at TEXT NOT NULL)''')
        # Upgrade databases created by older versions.
        cols = {r[1] for r in c.execute('PRAGMA table_info(draws)')}
        if 'special' not in cols:
            c.execute('ALTER TABLE draws ADD COLUMN special INTEGER')
        c.commit()


def issue_ok(x):
    s = re.sub(r'\D', '', str(x))
    return s if len(s) >= 10 else None


def nums7(value):
    if isinstance(value, list): raw = value
    else: raw = re.findall(r'(?<!\d)(0?[1-9]|[1-4]\d)(?!\d)', str(value))
    out=[]
    for v in raw:
        try:
            n=int(v)
            if 1<=n<=49: out.append(n)
        except Exception: pass
    return out[:7] if len(out)>=7 else None


def add(found, issue, dt, nums, special=None):
    issue=issue_ok(issue); nums=nums7(nums)
    if not issue or not dt or not nums or len(nums)!=7: return
    # Never silently replace a clearly supplied special with an arbitrary 7th token.
    sp = int(special) if str(special).isdigit() and 1<=int(special)<=49 else nums[6]
    nums = nums[:6] + [sp]
    found[issue]=(issue,str(dt).strip(),nums,sp)


def parse_json_obj(obj, found):
    if isinstance(obj, list): items=obj
    elif isinstance(obj, dict):
        items=obj.get('data') if isinstance(obj.get('data'),list) else []
        if not items and all(k in obj for k in ('expect','openCode')): items=[obj]
    else: return
    for it in items:
        if not isinstance(it,dict): continue
        issue=it.get('expect') or it.get('issue') or it.get('period')
        dt=it.get('openTime') or it.get('open_time') or it.get('drawTime')
        code=it.get('openCode') or it.get('open_code') or it.get('numbers')
        if issue and dt and code:
            add(found,issue,dt,code)


def parse_json_text(text, found):
    try: parse_json_obj(json.loads(text),found); return
    except Exception: pass
    for m in re.finditer(r'\{[^{}]{0,3000}"(?:expect|issue)"\s*:\s*"?([0-9]{10,})"?.{0,2500}?"(?:openCode|open_code)"\s*:\s*"([^"]+)".{0,1500}?"(?:openTime|open_time)"\s*:\s*"([^"]+)"',text,re.S):
        add(found,m.group(1),m.group(3),m.group(2))


def parse_html(raw, found):
    parse_json_text(raw,found)
    soup=BeautifulSoup(raw,'html.parser')
    # Prefer table rows because a 3-minute history page may render special separately.
    for tr in soup.find_all('tr'):
        cells=[c.get_text(' ',strip=True) for c in tr.find_all(['td','th'])]
        if len(cells)<3: continue
        mi=next((re.search(r'(\d{10,})',c) for c in cells if re.search(r'\d{10,}',c)),None)
        if not mi: continue
        issue=mi.group(1)
        dt=next((re.search(r'20\d{2}[-/]\d{1,2}[-/]\d{1,2}\s+\d{1,2}:\d{2}(?::\d{2})?',c) for c in cells if re.search(r'20\d{2}[-/]\d{1,2}[-/]\d{1,2}\s+\d{1,2}:\d{2}',c)),None)
        if not dt: continue
        nums=nums7(' '.join(cells[2:]))
        if nums: add(found,issue,dt.group(0),nums)
    text=' '.join(soup.stripped_strings).replace('\xa0',' ')
    matches=list(re.finditer(r'第\s*(\d{10,})\s*期',text))
    for i,m in enumerate(matches):
        block=text[m.end():(matches[i+1].start() if i+1<len(matches) else min(len(text),m.end()+5000))]
        dt=re.search(r'(20\d{2}[-/]\d{1,2}[-/]\d{1,2}\s+\d{1,2}:\d{2}(?::\d{2})?)',block)
        if not dt: continue
        tail=block[dt.end():]
        # If the page exposes the label 特碼, use the first number immediately after that label.
        sm=re.search(r'(?:特碼|特码)\s*[:：]?\s*(?:[^0-9]{0,40})((?:0?[1-9]|[1-4]\d))',tail)
        special=int(sm.group(1)) if sm else None
        ns=nums7(tail)
        if ns: add(found,m.group(1),dt.group(1),ns,special)


def get(url):
    r=requests.get(url,headers=HEADERS,timeout=20)
    r.raise_for_status(); return r


def collect():
    found={}; errors=[]
    # 1) Try the documented API, but reject ordinary 7-digit Macau Mark Six records.
    try:
        r=get(LATEST_API); parse_json_text(r.text,found)
    except Exception as e: errors.append('latest-api: '+str(e))
    # 2) Official 3-minute pages.
    for u in (THREE_MIN_PAGE,THREE_MIN_LIVE):
        try:
            r=get(u); parse_html(r.text,found)
        except Exception as e: errors.append(u+': '+str(e))
    # 3) Text proxy fallback.
    try:
        r=get(READER); parse_html(r.text,found)
    except Exception as e: errors.append('reader: '+str(e))
    # 4) If we found a 3-minute issue, ask the documented by-issue endpoint for nearby 3-minute issues.
    if found:
        latest=max(found, key=lambda x: (found[x][1],x))
        m=re.match(r'(\d{8})(\d{3})$',latest)
        if m:
            day,seq=m.group(1),int(m.group(2))
            # Fetch a modest window; only records with 11-digit 3-minute issue format are accepted.
            for k in range(max(1,seq-120),seq+1):
                issue=day+f'{k:03d}'
                if issue in found: continue
                try:
                    r=get(HISTORY_API.format(issue)); parse_json_text(r.text,found)
                except Exception: pass
    return found,errors


def save(found):
    now=datetime.utcnow().isoformat(timespec='seconds')
    with sqlite3.connect(DB) as c:
        for issue,dt,nums,sp in found.values():
            c.execute('''INSERT INTO draws(issue,draw_time,numbers,special,updated_at) VALUES(?,?,?,?,?)
                         ON CONFLICT(issue) DO UPDATE SET draw_time=excluded.draw_time,numbers=excluded.numbers,special=excluded.special,updated_at=excluded.updated_at''',
                      (issue,dt,json.dumps(nums),sp,now))
        c.commit()
        return c.execute('SELECT COUNT(*) FROM draws').fetchone()[0]


def all_rows(limit=200):
    with sqlite3.connect(DB) as c:
        rows=c.execute('SELECT issue,draw_time,numbers,special FROM draws ORDER BY draw_time DESC, issue DESC LIMIT ?', (limit,)).fetchall()
    out=[]
    for issue,dt,raw,sp in rows:
        ns=json.loads(raw)
        sp=sp if sp else ns[6]
        out.append({'issue':issue,'time':dt,'numbers':ns,'special':sp})
    return out


def score_data():
    rs=all_rows(100)
    c=Counter()
    for r in rs: c.update(r['numbers'][:6])
    return sorted(c.items(),key=lambda x:(-x[1],x[0]))[:12]


def count_rows():
    with sqlite3.connect(DB) as c: return c.execute('SELECT COUNT(*) FROM draws').fetchone()[0]


def do_sync():
    found,errors=collect()
    total=save(found) if found else count_rows()
    latest=max(found, key=lambda x:(found[x][1],x)) if found else (all_rows(1)[0]['issue'] if all_rows(1) else None)
    return found,errors,total,latest

@app.route('/')
def index(): return render_template_string(HTML)

@app.route('/api/data')
def api_data(): return jsonify({'draws':all_rows(50),'scores':score_data(),'count':count_rows()})

@app.route('/api/sync')
def api_sync():
    try:
        found,errors,total,latest=do_sync()
        if not found: return jsonify({'ok':False,'parsed':0,'total':total,'latest':latest,'error':'暂时没有解析到新的澳门六合彩3分数据。','details':errors}),502
        return jsonify({'ok':True,'parsed':len(found),'total':total,'latest':latest,'details':errors})
    except Exception as e:
        return jsonify({'ok':False,'parsed':0,'total':count_rows(),'error':str(e)}),500

def background():
    while True:
        try: do_sync()
        except Exception: pass
        time.sleep(45)

init_db()
threading.Thread(target=background,daemon=True).start()

if __name__=='__main__': app.run(host='0.0.0.0',port=int(os.environ.get('PORT',5000)))
