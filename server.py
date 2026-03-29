#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
מחולל סידור עבודה — שרת אינטרנט (multi-team)
"""

import os, sys, json, socket, hashlib
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, unquote_plus, quote_plus
from datetime import datetime, timedelta
from collections import defaultdict

BASE    = os.path.dirname(os.path.abspath(__file__))
STORAGE = os.environ.get('DATA_DIR', '/tmp' if not os.access(BASE, os.W_OK) else BASE)
DATA_F  = os.path.join(STORAGE, 'data.json')
PORT    = int(os.environ.get('PORT', 5050))

sys.path.insert(0, BASE)
try:
    from schedule_gen import (auto_schedule, make_pdf,
                               parse_preferences, get_week_dates, fmt_date)
    PDF_OK = True
except Exception:
    PDF_OK = False

DAYS    = ['ראשון','שני','שלישי','רביעי','חמישי','שישי','שבת']
SHIFTS  = ['בוקר','צהריים','לילה']
HRS     = {'בוקר':'06:00–14:00','צהריים':'14:00–22:00','לילה':'22:00–06:00'}
WEEKEND = {'שישי','שבת'}
MIN_ALL   = 10
MIN_NIGHT = 2
MIN_WKND  = 2

# ── data helpers ───────────────────────────────────────────────
def load_all():
    if os.path.exists(DATA_F):
        with open(DATA_F, encoding='utf-8') as f:
            d = json.load(f)
        if 'teams' not in d:
            d = {'teams': {'כללי': d}}
        return d
    return {'teams': {}}

def save_all(d):
    with open(DATA_F, 'w', encoding='utf-8') as f:
        json.dump(d, f, ensure_ascii=False, indent=2)

def load_team(team):
    return load_all().get('teams', {}).get(team,
           {'week_start': '', 'preferences': '', 'submissions': {},
            'shift_mode': '3x8', 'admin_password': ''})

def save_team(team, tdata):
    d = load_all()
    d.setdefault('teams', {})[team] = tdata
    save_all(d)

def all_teams():
    return list(load_all().get('teams', {}).keys())

def get_public_base():
    railway = os.environ.get('RAILWAY_PUBLIC_DOMAIN', '')
    if railway:
        return 'https://' + railway
    try:
        s = socket.socket(); s.settimeout(1)
        s.connect(('8.8.8.8', 80)); ip = s.getsockname()[0]; s.close()
        return 'http://{}:{}'.format(ip, PORT)
    except Exception:
        return 'http://localhost:{}'.format(PORT)

def sub_to_avail(sub):
    avail = defaultdict(list)
    for key, val in sub.get('shifts', {}).items():
        if val and '__' in key:
            day, shift = key.split('__', 1)
            avail[day].append(shift)
    return dict(avail)

def _normalize_wk(wk):
    """Convert YYYY-MM-DD to DD.MM.YYYY if needed."""
    if wk and '-' in wk:
        try:
            return datetime.strptime(wk, '%Y-%m-%d').strftime('%d.%m.%Y')
        except Exception:
            pass
    return wk

def week_label(wk):
    if not wk or not PDF_OK: return ''
    try:
        dates = get_week_dates(_normalize_wk(wk))
        return '{} – {}'.format(fmt_date(dates[0]), fmt_date(dates[6]))
    except Exception: return ''

def week_dates_json(wk):
    if not wk or not PDF_OK: return [''] * 7
    try: return [fmt_date(d) for d in get_week_dates(_normalize_wk(wk))]
    except Exception: return [''] * 7

def cookie_name(team):
    return 'admin_' + hashlib.md5(team.encode()).hexdigest()[:8]

def is_authenticated(handler, team, admin_password):
    """Check if the current request has a valid admin cookie."""
    if not admin_password:
        return False
    cookie_val = handler.get_cookie(cookie_name(team))
    hashed_pwd = hashlib.md5(admin_password.encode()).hexdigest()
    return cookie_val == hashed_pwd

# ══════════════════════════════════════════════════════════════
# LANDING PAGE
# ══════════════════════════════════════════════════════════════
def landing_page():
    teams      = all_teams()
    teams_opts = ''.join(f'<option value="{t}">{t}</option>' for t in teams)
    return '''<!DOCTYPE html>
<html dir="rtl" lang="he"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>מערכת סידור עבודה</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:"Segoe UI",Arial,sans-serif;background:linear-gradient(135deg,#1a365d,#2b6cb0);
     min-height:100vh;display:flex;align-items:center;justify-content:center;padding:20px}
.wrap{width:100%;max-width:460px}
.logo{text-align:center;color:white;margin-bottom:32px}
.logo h1{font-size:26px;margin-bottom:6px}
.logo p{font-size:14px;opacity:.75}
.card{background:white;border-radius:18px;padding:30px 28px;box-shadow:0 8px 32px rgba(0,0,0,.2)}
h2{font-size:16px;color:#2d3748;margin-bottom:18px;text-align:center}
label{display:block;font-size:13px;font-weight:600;color:#4a5568;margin-bottom:6px}
select,input[type=text]{width:100%;padding:11px 13px;border:1.5px solid #e2e8f0;border-radius:9px;
  font-size:14px;font-family:inherit;direction:rtl;margin-bottom:16px;color:#2d3748}
select:focus,input:focus{outline:none;border-color:#2b6cb0}
.btns{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:4px}
.btn{padding:13px;border:none;border-radius:10px;font-size:14px;font-weight:700;
     cursor:pointer;font-family:inherit;transition:.15s}
.btn-mgr{background:#1a365d;color:white} .btn-mgr:hover{background:#2c5282}
.btn-emp{background:#276749;color:white} .btn-emp:hover{background:#22543d}
.divider{border:none;border-top:1px solid #e2e8f0;margin:22px 0}
.btn-new{width:100%;padding:11px;background:#f7fafc;border:1.5px solid #e2e8f0;
         border-radius:9px;font-size:13px;font-weight:600;color:#4a5568;cursor:pointer;
         font-family:inherit;margin-top:12px}
.btn-new:hover{background:#edf2f7}
</style></head>
<body><div class="wrap">
<div class="logo">
  <h1>&#128203; מערכת סידור עבודה</h1>
  <p>בחר/י צוות וסוג כניסה</p>
</div>
<!-- עובד -->
<div class="card" style="margin-bottom:16px">
  <h2>&#128203; כניסת עובד</h2>
  <label>בחר/י צוות</label>
  <select id="team-emp" required>
    <option value="">-- בחר צוות --</option>
    ''' + teams_opts + '''
  </select>
  <button type="button" class="btn btn-emp" style="width:100%" onclick="goEmp()">&#10132; כניסה</button>
</div>

<!-- מנהל -->
<div class="card">
  <h2>&#9881;&#65039; כניסת מנהל</h2>
  <label>בחר/י צוות קיים</label>
  <select id="team-mgr">
    <option value="">-- בחר צוות --</option>
    ''' + teams_opts + '''
  </select>
  <button type="button" class="btn btn-mgr" style="width:100%;margin-bottom:18px" onclick="goMgr()">&#10132; כניסה לניהול</button>

  <hr class="divider" style="margin:0 0 18px">

  <label>&#10133; או צור צוות חדש</label>
  <input type="text" id="new-team" placeholder="לדוגמה: אקליפטוס, רוז, מנהלים...">
  <button class="btn-new" onclick="createTeam()">&#10133; צור צוות חדש</button>
</div>
</div>
<script>
function goEmp(){
  const t=document.getElementById('team-emp').value;
  if(!t){alert('בחר/י צוות תחילה');return;}
  window.location.href='/form?team='+encodeURIComponent(t);
}
function goMgr(){
  const t=document.getElementById('team-mgr').value;
  if(!t){alert('בחר/י צוות תחילה');return;}
  window.location.href='/admin?team='+encodeURIComponent(t);
}
function createTeam(){
  const name=document.getElementById('new-team').value.trim();
  if(!name){alert('הזן/י שם צוות');return;}
  fetch('/create-team',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({team:name})})
  .then(r=>r.json()).then(r=>{
    if(r.ok) window.location.href='/admin?team='+encodeURIComponent(name);
    else alert('שגיאה: '+r.error);
  });
}
</script>
</body></html>'''

# ══════════════════════════════════════════════════════════════
# EMPLOYEE FORM
# ══════════════════════════════════════════════════════════════
def employee_page(name_hint, wk, team, shift_mode='3x8'):
    wlabel   = week_label(wk)
    dates    = week_dates_json(wk)
    subtitle = ('שבוע: ' + wlabel) if wlabel else 'מלא/י את הזמינות שלך לשבוע הקרוב'
    team_tag = (' | צוות: ' + team) if team else ''

    if shift_mode == '2x12':
        shifts = ['בוקר', 'לילה']
        hrs = {'בוקר': '06:00–18:00', 'לילה': '18:00–06:00'}
        min_all = 6
        min_night = 2
    else:
        shifts = ['בוקר', 'צהריים', 'לילה']
        hrs = {'בוקר': '06:00–14:00', 'צהריים': '14:00–22:00', 'לילה': '22:00–06:00'}
        min_all = 10
        min_night = 2

    days_json   = json.dumps(DAYS,   ensure_ascii=False)
    shifts_json = json.dumps(shifts, ensure_ascii=False)
    hrs_json    = json.dumps(hrs,    ensure_ascii=False)
    dates_json  = json.dumps(dates,  ensure_ascii=False)
    wknd_list   = json.dumps(list(WEEKEND), ensure_ascii=False)
    team_js     = json.dumps(team, ensure_ascii=False)

    return '''<!DOCTYPE html>
<html dir="rtl" lang="he"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>טופס זמינות משמרות</title>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{--navy:#1a365d;--blue:#2b6cb0;--slate:#2d3748;--green:#276749;--red:#c53030;
  --gray:#718096;--mint:#f0fff4;--amber:#fffbeb;--ice:#ebf4ff;--dg:#48bb78;
  --da:#d69e2e;--dn:#4299e1;--border:#e2e8f0}
body{font-family:"Segoe UI",Arial,sans-serif;background:#edf2f7;color:var(--slate);
     direction:rtl;padding-bottom:40px}
.hdr{background:linear-gradient(135deg,var(--navy),#2c5282);color:white;
     padding:18px 20px;text-align:center}
.hdr h1{font-size:20px}.hdr p{font-size:12px;opacity:.75;margin-top:4px}
.card{background:white;border-radius:14px;padding:20px 22px;margin:18px auto;
      max-width:800px;box-shadow:0 2px 12px rgba(0,0,0,.08)}
label{display:block;font-weight:600;font-size:13px;color:var(--slate);margin-bottom:6px}
.hint{color:var(--gray);font-weight:400;font-size:11px}
input[type=text],textarea{width:100%;padding:10px 12px;border:1.5px solid var(--border);
  border-radius:8px;font-size:14px;font-family:inherit;direction:rtl}
input[type=text]:focus,textarea:focus{outline:none;border-color:var(--blue)}
textarea{min-height:80px;resize:vertical}
.grid-wrap{overflow-x:auto;margin-top:8px}
.sg{width:100%;border-collapse:collapse;min-width:540px}
.sg th,.sg td{border:1px solid var(--border)}
.th-day{background:var(--blue);color:white;text-align:center;padding:7px 4px;
        font-size:12px;font-weight:700}
.th-day .dd{font-size:10px;opacity:.9;font-weight:600;display:block;margin-top:3px;
            background:rgba(255,255,255,.2);border-radius:4px;padding:1px 4px}
.th-sh{background:var(--slate);color:white;text-align:center;padding:8px 6px;
       width:75px;font-size:11px}
.sh-hrs{font-size:9px;opacity:.72;display:block;margin-top:2px}
.cm{background:var(--mint)}.ca{background:var(--amber)}.cn{background:var(--ice)}
.cb-wrap{display:flex;align-items:center;justify-content:center;padding:6px 4px}
.cb-wrap input[type=checkbox]{width:20px;height:20px;cursor:pointer;accent-color:var(--blue)}
.vbar{display:flex;gap:10px;flex-wrap:wrap;margin-top:16px;padding:12px 14px;
      background:#f7fafc;border-radius:8px;border:1px solid var(--border)}
.vi{display:flex;align-items:center;gap:5px;font-size:12px;font-weight:600}
.badge{display:inline-flex;align-items:center;justify-content:center;min-width:26px;
       height:22px;padding:0 6px;border-radius:11px;font-size:11px;font-weight:700;transition:.2s}
.ok{background:#c6f6d5;color:#276749}.err{background:#fed7d7;color:#c53030}
.ico-ok{color:#48bb78;font-size:15px}.ico-err{color:#fc8181;font-size:15px}
.btn-sub{display:block;width:100%;padding:14px;background:var(--blue);color:white;border:none;
         border-radius:10px;font-size:16px;font-weight:700;cursor:pointer;font-family:inherit;
         margin-top:16px;transition:.2s}
.btn-sub:disabled{background:#a0aec0;cursor:not-allowed}
.btn-sub:not(:disabled):hover{background:#2c5282}
.success{display:none;text-align:center;padding:30px 20px}
.success .big{font-size:56px;margin-bottom:12px}
.success h2{color:var(--green);font-size:22px}
.success p{color:var(--gray);margin-top:8px;font-size:14px}
.btn-again{display:inline-block;margin-top:20px;padding:10px 24px;background:var(--blue);
           color:white;border:none;border-radius:8px;font-size:14px;cursor:pointer;font-family:inherit}
@media(max-width:600px){
  .card{padding:14px 10px}
  .hdr h1{font-size:17px}
  .cb-wrap input[type=checkbox]{width:24px;height:24px}
  .btn-sub{min-height:56px;font-size:15px}
  input[type=text],textarea{font-size:16px}
}
</style></head>
<body>
<div class="hdr">
  <h1>&#128203; טופס זמינות משמרות</h1>
  <p>''' + subtitle + team_tag + '''</p>
</div>
<div class="card" id="form-card">
  <div style="margin-bottom:16px">
    <label>&#128100; שמך המלא</label>
    <input type="text" id="emp-name" value="''' + name_hint + '''"
           placeholder="שם פרטי + משפחה" oninput="validate()">
  </div>
  <label>&#128197; בחר/י את המשמרות שאת/ה יכול/ה לעבוד
    <span class="hint">(לפחות ''' + str(min_all) + ''' משמרות)</span></label>
  <div class="grid-wrap">
    <table class="sg" id="grid">
      <thead id="grid-head"></thead>
      <tbody id="grid-body"></tbody>
    </table>
  </div>
  <div class="vbar">
    <div class="vi"><span id="ico-t" class="ico-err">&#10007;</span>
      <span>סה"כ: <span class="badge err" id="b-t">0</span>/''' + str(min_all) + '''+</span></div>
    <div class="vi"><span id="ico-n" class="ico-err">&#10007;</span>
      <span>לילה: <span class="badge err" id="b-n">0</span>/''' + str(min_night) + '''+</span></div>
    <div class="vi"><span id="ico-w" class="ico-err">&#10007;</span>
      <span>סופ"ש: <span class="badge err" id="b-w">0</span>/''' + str(MIN_WKND) + '''+
        <span class="hint">&nbsp;(ש"ו–ש"ב)</span></span></div>
  </div>
  <div style="margin-top:16px">
    <label>&#128172; הערות / בקשות מיוחדות <span class="hint">(אופציונלי)</span></label>
    <textarea id="notes" placeholder="לדוגמה: מבקש לא לסדר ביום ד׳, מעדיף משמרות בוקר..."></textarea>
  </div>
  <button class="btn-sub" id="sub-btn" disabled onclick="doSubmit()">&#10003; שלח זמינות</button>
</div>
<div class="card success" id="ok-card">
  <div class="big">&#9989;</div>
  <h2>הזמינות נשלחה בהצלחה!</h2>
  <p id="ok-msg">תודה! הזמינות שלך נשמרה.</p>
  <button class="btn-again" onclick="location.reload()">&#128203; עדכן שוב</button>
</div>
<script>
const DAYS=''' + days_json + ''';const SHFTS=''' + shifts_json + ''';
const HRS=''' + hrs_json + ''';const DATES=''' + dates_json + ''';
const WKND=new Set(''' + wknd_list + ''');const TEAM=''' + team_js + ''';
const CLS={'\u05d1\u05d5\u05e7\u05e8':'cm','\u05e6\u05d4\u05e8\u05d9\u05d9\u05dd':'ca','\u05dc\u05d9\u05dc\u05d4':'cn'};
const head=document.getElementById('grid-head');
const body=document.getElementById('grid-body');
const hr=document.createElement('tr');
hr.innerHTML='<th class="th-sh"></th>'+
  DAYS.map((d,i)=>{
    const dateStr=DATES[i]?'<span class="dd">'+DATES[i]+'</span>':'';
    return '<th class="th-day">'+d+dateStr+'</th>';
  }).join('');
head.appendChild(hr);
SHFTS.forEach(sh=>{
  const tr=document.createElement('tr');
  let cells='<td class="th-sh">'+sh+'<span class="sh-hrs">'+HRS[sh]+'</span></td>';
  DAYS.forEach(d=>{
    const id=d+'__'+sh;
    cells+='<td class="'+(CLS[sh]||'')+'"><div class="cb-wrap"><input type="checkbox" id="'+id+'"'+
           ' data-day="'+d+'" data-shift="'+sh+'" onchange="validate()"></div></td>';
  });
  tr.innerHTML=cells;body.appendChild(tr);
});
function validate(){
  const cbs=[...document.querySelectorAll('#grid input:checked')];
  const total=cbs.length;
  const nights=cbs.filter(c=>c.dataset.shift==='\u05dc\u05d9\u05dc\u05d4').length;
  const wknds=cbs.filter(c=>WKND.has(c.dataset.day)).length;
  const name=document.getElementById('emp-name').value.trim();
  function upd(bid,iid,val,min){
    const ok=val>=min;const b=document.getElementById(bid);
    b.textContent=val;b.className='badge '+(ok?'ok':'err');
    const ic=document.getElementById(iid);
    ic.textContent=ok?'\u2713':'\u2717';ic.className=ok?'ico-ok':'ico-err';return ok;
  }
  const t=upd('b-t','ico-t',total,''' + str(min_all) + ''');
  const n=upd('b-n','ico-n',nights,''' + str(min_night) + ''');
  const w=upd('b-w','ico-w',wknds,''' + str(MIN_WKND) + ''');
  document.getElementById('sub-btn').disabled=!(t&&n&&w&&name.length>1);
}
function doSubmit(){
  const name=document.getElementById('emp-name').value.trim();
  const notes=document.getElementById('notes').value.trim();
  const shifts={};
  document.querySelectorAll('#grid input[type=checkbox]').forEach(cb=>{shifts[cb.id]=cb.checked;});
  fetch('/submit?team='+encodeURIComponent(TEAM),{
    method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({name,shifts,notes})
  }).then(r=>r.json()).then(r=>{
    if(r.ok){
      document.getElementById('form-card').style.display='none';
      const ok=document.getElementById('ok-card');ok.style.display='block';
      document.getElementById('ok-msg').textContent='תודה '+name+'! '+r.count+' משמרות נשמרו.';
    }else alert('שגיאה: '+r.error);
  }).catch(()=>alert('שגיאת חיבור'));
}
validate();
</script></body></html>'''

# ══════════════════════════════════════════════════════════════
# PASSWORD PAGES
# ══════════════════════════════════════════════════════════════
def password_login_page(team, error=''):
    err_html = ''
    if error:
        err_html = '<div style="background:#fed7d7;color:#c53030;padding:10px 14px;border-radius:8px;margin-bottom:14px;font-weight:600">&#10007; ' + error + '</div>'
    return '''<!DOCTYPE html>
<html dir="rtl" lang="he"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>כניסה למנהל</title>
<style>
body{font-family:"Segoe UI",Arial,sans-serif;background:linear-gradient(135deg,#1a365d,#2b6cb0);
     display:flex;align-items:center;justify-content:center;min-height:100vh;padding:20px}
.card{background:white;border-radius:18px;padding:40px 30px;max-width:400px;width:100%;
      box-shadow:0 8px 32px rgba(0,0,0,.2);text-align:center}
h2{color:#1a365d;margin-bottom:6px;font-size:22px}
.sub{color:#718096;font-size:13px;margin-bottom:24px}
input[type=password]{width:100%;padding:12px 14px;border:1.5px solid #e2e8f0;
  border-radius:8px;font-size:15px;margin-bottom:16px;font-family:inherit;direction:rtl;text-align:right}
input:focus{outline:none;border-color:#2b6cb0}
.btn{width:100%;padding:13px;background:#1a365d;color:white;border:none;border-radius:9px;
     font-size:15px;font-weight:700;cursor:pointer;font-family:inherit}
.btn:hover{background:#2c5282}
.back{margin-top:16px;display:block;color:#718096;font-size:13px;text-decoration:none}
.back:hover{color:#2b6cb0}
</style></head>
<body><div class="card">
<div style="font-size:48px;margin-bottom:12px">&#128272;</div>
<h2>כניסת מנהל</h2>
<p class="sub">צוות: ''' + team + '''</p>
''' + err_html + '''
<form method="POST" action="/admin/login?team=''' + quote_plus(team) + '''">
  <input type="password" name="password" placeholder="הזן סיסמת מנהל" required autofocus>
  <button type="submit" class="btn">&#10132; כניסה</button>
</form>
<a href="/" class="back">&#8592; חזרה לעמוד הראשי</a>
</div></body></html>'''


def set_password_page(team, error=''):
    err_html = ''
    if error:
        err_html = '<div style="background:#fed7d7;color:#c53030;padding:10px 14px;border-radius:8px;margin-bottom:14px;font-weight:600">&#10007; ' + error + '</div>'
    return '''<!DOCTYPE html>
<html dir="rtl" lang="he"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>הגדרת סיסמה</title>
<style>
body{font-family:"Segoe UI",Arial,sans-serif;background:linear-gradient(135deg,#1a365d,#2b6cb0);
     display:flex;align-items:center;justify-content:center;min-height:100vh;padding:20px}
.card{background:white;border-radius:18px;padding:40px 30px;max-width:420px;width:100%;
      box-shadow:0 8px 32px rgba(0,0,0,.2)}
h2{color:#1a365d;margin-bottom:6px;font-size:20px;text-align:center}
.sub{color:#718096;font-size:13px;margin-bottom:24px;text-align:center}
.info{background:#ebf8ff;border:1px solid #90cdf4;border-radius:8px;padding:12px 14px;
      font-size:13px;color:#2b6cb0;margin-bottom:20px;line-height:1.5}
label{display:block;font-size:13px;font-weight:600;color:#4a5568;margin-bottom:6px}
input[type=password]{width:100%;padding:12px 14px;border:1.5px solid #e2e8f0;
  border-radius:8px;font-size:15px;margin-bottom:16px;font-family:inherit;direction:rtl}
input:focus{outline:none;border-color:#2b6cb0}
.btn{width:100%;padding:13px;background:#276749;color:white;border:none;border-radius:9px;
     font-size:15px;font-weight:700;cursor:pointer;font-family:inherit}
.btn:hover{background:#22543d}
.back{margin-top:16px;display:block;color:#718096;font-size:13px;text-decoration:none;text-align:center}
</style></head>
<body><div class="card">
<div style="font-size:48px;margin-bottom:12px;text-align:center">&#128274;</div>
<h2>הגדרת סיסמת מנהל</h2>
<p class="sub">צוות: ''' + team + '''</p>
<div class="info">
  &#128161; צוות חדש דורש הגדרת סיסמה לפני הכניסה.<br>
  הסיסמה תגן על דף הניהול של הצוות שלך.
</div>
''' + err_html + '''
<form method="POST" action="/admin/set-password?team=''' + quote_plus(team) + '''">
  <label>סיסמה חדשה</label>
  <input type="password" name="password" placeholder="הזן סיסמה (לפחות 4 תווים)" required autofocus minlength="4">
  <label>אמת סיסמה</label>
  <input type="password" name="password2" placeholder="הזן שוב את הסיסמה" required>
  <button type="submit" class="btn">&#10003; שמור סיסמה וכנס</button>
</form>
<a href="/" class="back">&#8592; חזרה לעמוד הראשי</a>
</div></body></html>'''

# ══════════════════════════════════════════════════════════════
# ADMIN PAGE  (simplified)
# ══════════════════════════════════════════════════════════════
def admin_page(team, data, flash=''):
    subs       = data.get('submissions', {})
    wk         = data.get('week_start', '')
    prefs      = data.get('preferences', '')
    shift_mode = data.get('shift_mode', '3x8')
    admin_password = data.get('admin_password', '')
    base       = get_public_base()
    wl         = week_label(wk)
    emp_link   = base + '/form?team=' + quote_plus(team)
    last_sched = data.get('last_schedule', {})

    flash_html = ''
    if flash:
        flash_html = ('<div style="background:#c6f6d5;color:#276749;padding:12px 16px;'
                      'border-radius:10px;margin-bottom:18px;font-weight:600;font-size:14px">'
                      '&#9989; ' + flash + '</div>')

    # Week display
    if wl:
        week_display = '<div style="background:#c6f6d5;color:#276749;padding:8px 14px;border-radius:7px;font-weight:700;font-size:14px;margin-top:10px">&#10003; שבוע נבחר: ' + wl + '</div>'
    else:
        week_display = '<div style="background:#fffbeb;color:#b7791f;padding:8px 14px;border-radius:7px;font-size:13px;margin-top:10px">&#9888; טרם נבחר תאריך שבוע</div>'

    # Submissions summary
    n_subs = len(subs)
    if n_subs == 0:
        subs_info = '<span style="color:#718096">טרם התקבלו הגשות מעובדים</span>'
    else:
        subs_info = '<span style="color:#276749;font-weight:700;font-size:18px">' + str(n_subs) + '</span> <span style="color:#4a5568">עובדים מילאו את הטופס</span>'

    # Generate button
    if not wk:
        gen_btn = '<button disabled style="width:100%;padding:14px;background:#a0aec0;color:white;border:none;border-radius:10px;font-size:15px;font-weight:700;cursor:not-allowed;font-family:inherit">&#128203; צור סידור עבודה</button><p style="font-size:12px;color:#718096;margin-top:8px;text-align:center">יש לבחור תאריך שבוע תחילה</p>'
    elif n_subs == 0:
        gen_btn = '<button disabled style="width:100%;padding:14px;background:#a0aec0;color:white;border:none;border-radius:10px;font-size:15px;font-weight:700;cursor:not-allowed;font-family:inherit">&#128203; צור סידור עבודה</button><p style="font-size:12px;color:#718096;margin-top:8px;text-align:center">אין הגשות עדיין</p>'
    else:
        gen_btn = '<a href="/admin/generate?team=' + quote_plus(team) + '" style="display:block;width:100%;padding:14px;background:#276749;color:white;border:none;border-radius:10px;font-size:15px;font-weight:700;cursor:pointer;text-decoration:none;text-align:center;box-sizing:border-box">&#9889; צור סידור עבודה אוטומטי</a>'

    # If schedule already generated
    view_sched = ''
    if last_sched:
        view_sched = ('<div style="margin-top:10px">'
                     '<a href="/admin/schedule?team=' + quote_plus(team) + '" '
                     'style="display:block;width:100%;padding:12px;background:#ebf8ff;color:#2b6cb0;'
                     'border:1.5px solid #90cdf4;border-radius:10px;font-size:14px;font-weight:700;'
                     'text-decoration:none;text-align:center;box-sizing:border-box">'
                     '&#128203; צפה/ערוך סידור שנוצר</a></div>')

    # Submissions table rows
    rows = ''
    for name, sub in sorted(subs.items()):
        avail  = sub_to_avail(sub)
        total  = sum(len(v) for v in avail.values())
        nights = sum(1 for ss in avail.values() for s in ss if s == 'לילה')
        wknds  = sum(1 for d, ss in avail.items() for s in ss if d in WEEKEND)
        valid  = total >= MIN_ALL and nights >= MIN_NIGHT and wknds >= MIN_WKND
        def col(v, ok): return '<span style="font-weight:700;color:{}">{}</span>'.format('#276749' if ok else '#c53030', v)
        dots = ''
        for day in DAYS:
            ss = avail.get(day, [])
            if ss:
                lbl = ''.join({'בוקר':'ב','צהריים':'צ','לילה':'ל'}[s] for s in ss if s in {'בוקר','צהריים','לילה'})
                dots += ('<span style="font-size:9px;background:#ebf4ff;border-radius:3px;'
                         'padding:1px 3px;margin:1px">{} {}</span>').format(day[:2], lbl)
        notes_txt = sub.get('notes','') or '—'
        ts = sub.get('submitted_at','')[:16].replace('T',' ')
        icon = '&#9989;' if valid else '&#9888;&#65039;'
        del_url = '/admin/delete/' + quote_plus(name) + '?team=' + quote_plus(team)
        rows += ('<tr>'
                 '<td style="font-weight:700;padding:10px 8px">' + icon + ' ' + name + '</td>'
                 '<td style="text-align:center">' + col(total,  total  >= MIN_ALL)   + '</td>'
                 '<td style="text-align:center">' + col(nights, nights >= MIN_NIGHT) + '</td>'
                 '<td style="text-align:center">' + col(wknds,  wknds  >= MIN_WKND)  + '</td>'
                 '<td style="font-size:10px;line-height:1.7">' + dots + '</td>'
                 '<td style="font-size:11px;color:#718096;max-width:180px">' + notes_txt + '</td>'
                 '<td style="font-size:10px;color:#a0aec0">' + ts + '</td>'
                 '<td><a href="' + del_url + '" onclick="return confirm(\'מחק?\');"'
                 ' style="color:#c53030;font-size:12px;text-decoration:none">&#128465;</a></td>'
                 '</tr>')
    if not rows:
        rows = '<tr><td colspan="8" style="text-align:center;padding:30px;color:#a0aec0">טרם התקבלו הגשות</td></tr>'

    clear_btn = ''
    if subs:
        clear_btn = ('<form method="POST" action="/admin/clear?team=' + quote_plus(team) + '" style="margin-top:12px">'
                     '<button class="btn btn-red" onclick="return confirm(\'מחק את כל ההגשות?\');">'
                     '&#128465; נקה הכל</button></form>')

    return '''<!DOCTYPE html>
<html dir="rtl" lang="he"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ניהול — ''' + team + '''</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:"Segoe UI",Arial,sans-serif;background:#edf2f7;color:#2d3748;direction:rtl}
.hdr{background:linear-gradient(135deg,#1a365d,#2c5282);color:white;padding:14px 24px;
     display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px}
.hdr h1{font-size:18px}
.hdr-links{display:flex;gap:14px;align-items:center}
.hdr a{color:white;font-size:13px;text-decoration:none;opacity:.85}
.hdr a:hover{opacity:1}
.con{max-width:900px;margin:0 auto;padding:20px 16px}
.card{background:white;border-radius:14px;padding:22px 24px;margin-bottom:18px;
      box-shadow:0 2px 10px rgba(0,0,0,.07)}
.card-title{font-size:16px;font-weight:700;color:#2d3748;margin-bottom:16px;
            display:flex;align-items:center;gap:8px}
.step-num{background:#2b6cb0;color:white;border-radius:50%;width:26px;height:26px;
          display:inline-flex;align-items:center;justify-content:center;font-size:13px;font-weight:800}
label{font-size:13px;font-weight:600;margin-bottom:5px;display:block}
input[type=date],input[type=text],input[type=password],textarea{
  width:100%;padding:10px 12px;border:1.5px solid #e2e8f0;border-radius:8px;
  font-size:14px;font-family:inherit;direction:rtl}
input:focus,textarea:focus{outline:none;border-color:#2b6cb0}
textarea{min-height:75px;resize:vertical}
.btn{display:inline-block;padding:10px 22px;border:none;border-radius:8px;
     font-size:13px;font-weight:700;cursor:pointer;font-family:inherit;text-decoration:none;transition:.15s}
.btn-blue{background:#2b6cb0;color:white}.btn-blue:hover{background:#2c5282}
.btn-green{background:#276749;color:white}.btn-green:hover{background:#22543d}
.btn-red{background:#c53030;color:white}.btn-red:hover{background:#9b2c2c}
.link-box{background:#ebf8ff;border:1px solid #90cdf4;border-radius:10px;
          padding:14px 16px;font-size:13px;word-break:break-all;margin-bottom:10px;line-height:1.6}
.link-box strong{display:block;font-size:11px;color:#2b6cb0;margin-bottom:4px}
.copy-btn{padding:8px 18px;background:#2b6cb0;color:white;border:none;
          border-radius:7px;font-size:13px;cursor:pointer;font-family:inherit;font-weight:600}
.adv-toggle{color:#2b6cb0;font-size:13px;cursor:pointer;background:none;border:none;
            font-family:inherit;padding:0;text-decoration:underline;display:block;margin:0 auto}
.adv-section{display:none}
table{width:100%;border-collapse:collapse}
th{background:#2d3748;color:white;padding:8px;text-align:right;font-size:11px;font-weight:600}
td{padding:8px;border-bottom:1px solid #f0f4f8;font-size:12px;vertical-align:middle}
tr:hover td{background:#f7fafc}
.radio-group label{display:flex;align-items:center;font-weight:500;margin-bottom:8px;gap:8px}
.radio-group input[type=radio]{margin:0;cursor:pointer}
@media(max-width:640px){.con{padding:12px 10px}}
</style></head>
<body>
<div class="hdr">
  <h1>&#9881;&#65039; ''' + team + ''' — ניהול סידור</h1>
  <div class="hdr-links">
    <a href="/form?team=''' + quote_plus(team) + '''" target="_blank">&#128203; טופס עובדים &#8599;</a>
    <a href="/">&#8592; כל הצוותות</a>
  </div>
</div>
<div class="con">
''' + flash_html + '''

<!-- שלב 1: תאריך שבוע -->
<div class="card">
  <div class="card-title"><span class="step-num">1</span> בחר תאריכי שבוע</div>
  <form method="POST" action="/admin/setup?team=''' + quote_plus(team) + '''">
    <label>יום ראשון של השבוע</label>
    <input type="date" name="week_start" value="''' + wk + '''" required style="max-width:220px">
    <input type="hidden" name="preferences" value="''' + prefs.replace('"','&quot;') + '''">
    <input type="hidden" name="shift_mode" value="''' + shift_mode + '''">
    <input type="hidden" name="admin_password" value="''' + admin_password.replace('"','&quot;') + '''">
    <div style="margin-top:12px">
      <button type="submit" class="btn btn-blue">&#128190; שמור תאריך</button>
    </div>
  </form>
  ''' + week_display + '''
</div>

<!-- שלב 2: לינק לעובדים -->
<div class="card">
  <div class="card-title"><span class="step-num">2</span> שלח לינק לעובדים</div>
  <div class="link-box">
    <strong>&#128279; שלח לינק זה לעובדי צוות ''' + team + ''':</strong>
    ''' + emp_link + '''
  </div>
  <button class="copy-btn" onclick="navigator.clipboard.writeText(''' + json.dumps(emp_link) + ''').then(()=>{this.textContent='✓ הועתק!';setTimeout(()=>this.textContent='📋 העתק לינק',2000)})">
    &#128203; העתק לינק
  </button>
</div>

<!-- שלב 3: צור סידור -->
<div class="card">
  <div class="card-title"><span class="step-num">3</span> צור סידור עבודה</div>
  <div style="margin-bottom:14px">''' + subs_info + '''</div>
  ''' + gen_btn + '''
  ''' + view_sched + '''
</div>

<!-- הגדרות מתקדמות -->
<div style="text-align:center;margin-bottom:8px">
  <button class="adv-toggle" onclick="toggleAdv()">&#9660; הגדרות מתקדמות</button>
</div>
<div class="adv-section" id="adv-section">

  <!-- הגשות -->
  <div class="card">
    <div class="card-title">&#128203; הגשות שהתקבלו &nbsp;
      <span style="background:#2b6cb0;color:white;border-radius:50%;width:26px;height:26px;
            display:inline-flex;align-items:center;justify-content:center;font-size:13px;font-weight:800">
        ''' + str(n_subs) + '''</span>
    </div>
    <div style="overflow-x:auto">
    <table>
      <thead><tr>
        <th>עובד</th><th style="text-align:center">סה"כ</th>
        <th style="text-align:center">לילות</th><th style="text-align:center">סופ"ש</th>
        <th>בחירות</th><th>הערות</th><th>זמן</th><th>&#128465;</th>
      </tr></thead>
      <tbody>''' + rows + '''</tbody>
    </table>
    </div>
    ''' + clear_btn + '''
  </div>

  <!-- הגדרות נוספות -->
  <div class="card">
    <div class="card-title">&#9881;&#65039; הגדרות נוספות</div>
    <form method="POST" action="/admin/setup?team=''' + quote_plus(team) + '''">
      <input type="hidden" name="week_start" value="''' + wk + '''">
      <div style="margin-bottom:14px">
        <label>סוג משמרות</label>
        <div class="radio-group">
          <label><input type="radio" name="shift_mode" value="3x8" ''' + ('checked' if shift_mode == '3x8' else '') + '''>
            3 משמרות של 8 שעות (בוקר, צהריים, לילה)</label>
          <label><input type="radio" name="shift_mode" value="2x12" ''' + ('checked' if shift_mode == '2x12' else '') + '''>
            2 משמרות של 12 שעות (בוקר, לילה)</label>
        </div>
      </div>
      <div style="margin-bottom:14px">
        <label>העדפות עובדים <span style="font-weight:400;color:#718096">(אופציונלי)</span></label>
        <textarea name="preferences"
          placeholder="דביר יונה: מעדיף לילה&#10;שרה כהן: מעדיפה בוקר">''' + prefs + '''</textarea>
      </div>
      <div style="margin-bottom:14px">
        <label>שינוי סיסמת מנהל</label>
        <input type="password" name="admin_password" placeholder="הזן סיסמה חדשה (השאר ריק לשמירת הנוכחית)">
        <p style="font-size:11px;color:#718096;margin-top:4px">&#128274; השאר ריק אם אינך רוצה לשנות את הסיסמה הנוכחית</p>
      </div>
      <button type="submit" class="btn btn-blue">&#128190; שמור הגדרות</button>
    </form>
  </div>

</div>

</div>
<script>
function toggleAdv(){
  const s=document.getElementById('adv-section');
  const btn=document.querySelector('.adv-toggle');
  if(s.style.display==='block'){s.style.display='none';btn.textContent='▼ הגדרות מתקדמות';}
  else{s.style.display='block';btn.textContent='▲ הסתר הגדרות מתקדמות';}
}
</script>
</body></html>'''

# ══════════════════════════════════════════════════════════════
# SCHEDULE EDIT PAGE
# ══════════════════════════════════════════════════════════════
def schedule_edit_page(team, data):
    sched      = data.get('last_schedule', {})
    subs       = data.get('submissions', {})
    wk         = data.get('week_start', '')
    shift_mode = data.get('shift_mode', '3x8')
    wl         = week_label(wk)
    dates      = week_dates_json(wk)

    if shift_mode == '2x12':
        shifts_list = ['בוקר', 'לילה']
        hrs_map = {'בוקר': '06:00–18:00', 'לילה': '18:00–06:00'}
    else:
        shifts_list = ['בוקר', 'צהריים', 'לילה']
        hrs_map = {'בוקר': '06:00–14:00', 'צהריים': '14:00–22:00', 'לילה': '22:00–06:00'}

    shift_colors = {'בוקר': '#f0fff4', 'צהריים': '#fffbeb', 'לילה': '#ebf4ff'}
    shift_border = {'בוקר': '#48bb78', 'צהריים': '#d69e2e', 'לילה': '#4299e1'}

    # Build employee list per shift per day
    all_employees = sorted(subs.keys())
    avail_map = {n: sub_to_avail(s) for n, s in subs.items()}

    # Build the table rows
    table_rows = ''
    for sh in shifts_list:
        bg = shift_colors.get(sh, '#f7fafc')
        border_col = shift_border.get(sh, '#e2e8f0')
        cells = ''
        for i, day in enumerate(DAYS):
            current = sched.get(day, {}).get(sh, '') or ''
            # employees available for this shift on this day
            avail_emps = [e for e in all_employees if sh in avail_map.get(e, {}).get(day, [])]
            # build select options
            opts = '<option value="">— לא שובץ —</option>'
            for e in all_employees:
                sel = 'selected' if e == current else ''
                avail_note = '' if e in avail_emps else ' ⚠'
                opts += f'<option value="{e}" {sel}>{e}{avail_note}</option>'
            field_name = f'sched__{day}__{sh}'
            cells += (f'<td style="padding:6px 4px;background:{bg};border:1px solid #e2e8f0">'
                      f'<select name="{field_name}" '
                      f'style="width:100%;padding:5px 4px;border:1.5px solid {border_col};'
                      f'border-radius:6px;font-size:12px;font-family:inherit;direction:rtl;'
                      f'background:white;cursor:pointer">'
                      f'{opts}</select></td>')
        table_rows += (f'<tr>'
                       f'<td style="background:#2d3748;color:white;text-align:center;'
                       f'padding:8px 4px;font-size:12px;font-weight:700;white-space:nowrap">'
                       f'{sh}<span style="display:block;font-size:9px;opacity:.7">{hrs_map.get(sh,"")}</span></td>'
                       + cells + '</tr>')

    # Build day headers
    day_headers = ''
    for i, day in enumerate(DAYS):
        date_str = (' <span style="font-size:10px;background:rgba(255,255,255,.25);'
                    'border-radius:4px;padding:1px 5px">' + dates[i] + '</span>') if dates[i] else ''
        day_headers += f'<th style="background:#2b6cb0;color:white;padding:9px 4px;font-size:12px;text-align:center;border:1px solid #1a365d">{day}{date_str}</th>'

    return '''<!DOCTYPE html>
<html dir="rtl" lang="he"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>עריכת סידור — ''' + team + '''</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:"Segoe UI",Arial,sans-serif;background:#edf2f7;color:#2d3748;direction:rtl}
.hdr{background:linear-gradient(135deg,#1a365d,#2c5282);color:white;padding:14px 20px;
     display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px}
.hdr h1{font-size:17px}.hdr a{color:white;font-size:13px;text-decoration:none;opacity:.85}
.con{max-width:1200px;margin:0 auto;padding:20px 16px}
.card{background:white;border-radius:14px;padding:20px;margin-bottom:18px;box-shadow:0 2px 10px rgba(0,0,0,.07)}
.btn{display:inline-block;padding:11px 22px;border:none;border-radius:8px;font-size:14px;
     font-weight:700;cursor:pointer;font-family:inherit;text-decoration:none;transition:.15s}
.btn-green{background:#276749;color:white}.btn-green:hover{background:#22543d}
.btn-blue{background:#2b6cb0;color:white}.btn-blue:hover{background:#2c5282}
.btn-gray{background:#e2e8f0;color:#2d3748}.btn-gray:hover{background:#cbd5e0}
.tbl-wrap{overflow-x:auto}
table{width:100%;border-collapse:collapse;min-width:700px}
</style></head>
<body>
<div class="hdr">
  <h1>&#9998; עריכת סידור — ''' + team + ((' | ' + wl) if wl else '') + '''</h1>
  <a href="/admin?team=''' + quote_plus(team) + '''">&#8592; חזרה לניהול</a>
</div>
<div class="con">
<div class="card">
  <p style="font-size:14px;color:#4a5568;margin-bottom:16px">
    &#128203; עיין בסידור שנוצר אוטומטית ובצע שינויים לפי הצורך. לחץ <strong>שמור וצור PDF</strong> לסיום.
    <br><span style="font-size:12px;color:#718096">⚠ = עובד לא סימן זמינות למשמרת זו</span>
  </p>

  <form method="POST" action="/admin/schedule/save?team=''' + quote_plus(team) + '''">
    <div class="tbl-wrap">
    <table>
      <thead><tr>
        <th style="background:#1a365d;color:white;padding:9px 6px;width:85px;font-size:11px">משמרת</th>
        ''' + day_headers + '''
      </tr></thead>
      <tbody>''' + table_rows + '''</tbody>
    </table>
    </div>

    <div style="display:flex;gap:12px;margin-top:20px;flex-wrap:wrap">
      <button type="submit" class="btn btn-green">&#128196; שמור וצור PDF</button>
      <a href="/admin?team=''' + quote_plus(team) + '''" class="btn btn-gray">&#8592; חזרה ללא שמירה</a>
    </div>
  </form>
</div>
</div></body></html>'''

# ══════════════════════════════════════════════════════════════
# HTTP HANDLER
# ══════════════════════════════════════════════════════════════
class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args): pass

    def send_html(self, html, code=200):
        enc = html.encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(enc)))
        self.end_headers()
        self.wfile.write(enc)

    def send_json(self, obj, code=200):
        enc = json.dumps(obj, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(enc)))
        self.end_headers()
        self.wfile.write(enc)

    def _send_file(self, filepath, download_name):
        if not os.path.exists(filepath):
            self.send_html('<h2>קובץ לא נמצא — צור סידור תחילה</h2>', 404); return
        with open(filepath, 'rb') as f: data = f.read()
        self.send_response(200)
        self.send_header('Content-Type', 'application/pdf')
        self.send_header('Content-Disposition', f'attachment; filename="{download_name}"')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def redirect(self, loc):
        self.send_response(302)
        self.send_header('Location', loc)
        self.end_headers()

    def read_body(self):
        n = int(self.headers.get('Content-Length', 0))
        return self.rfile.read(n)

    def set_cookie(self, name, value, max_age=86400):
        self.send_header('Set-Cookie', f'{name}={value}; Path=/; Max-Age={max_age}; HttpOnly')

    def get_cookie(self, name):
        cookies = self.headers.get('Cookie', '')
        for part in cookies.split(';'):
            part = part.strip()
            if '=' in part:
                k, v = part.split('=', 1)
                if k.strip() == name:
                    return v.strip()
        return None

    def check_admin_auth(self, team, data):
        """Returns True if authenticated. If not, sends response and returns False."""
        admin_password = data.get('admin_password', '')
        if not admin_password:
            # No password set yet → redirect to set-password
            self.redirect('/admin/set-password?team=' + quote_plus(team))
            return False
        if not is_authenticated(self, team, admin_password):
            self.send_html(password_login_page(team))
            return False
        return True

    def do_GET(self):
        parsed = urlparse(self.path)
        path   = parsed.path.rstrip('/')
        qs     = parse_qs(parsed.query)
        team   = unquote_plus(qs.get('team', [''])[0])

        if path in ('', '/'):
            self.send_html(landing_page())

        elif path == '/form':
            if not team:
                self.redirect('/'); return
            name = unquote_plus(qs.get('name', [''])[0])
            data = load_team(team)
            shift_mode = data.get('shift_mode', '3x8')
            self.send_html(employee_page(name, data.get('week_start', ''), team, shift_mode))

        elif path == '/admin':
            if not team:
                self.redirect('/'); return
            data = load_team(team)
            if not self.check_admin_auth(team, data):
                return
            flash = unquote_plus(qs.get('msg', [''])[0])
            self.send_html(admin_page(team, data, flash))

        elif path == '/admin/set-password':
            if not team:
                self.redirect('/'); return
            data = load_team(team)
            # If password already set, require old password or admin cookie
            if data.get('admin_password', ''):
                if not is_authenticated(self, team, data.get('admin_password', '')):
                    self.send_html(password_login_page(team))
                    return
            self.send_html(set_password_page(team))

        elif path == '/admin/schedule':
            if not team:
                self.redirect('/'); return
            data = load_team(team)
            if not self.check_admin_auth(team, data):
                return
            if not data.get('last_schedule'):
                self.redirect('/admin?team=' + quote_plus(team)); return
            self.send_html(schedule_edit_page(team, data))

        elif path.startswith('/admin/delete/'):
            name = unquote_plus(path[len('/admin/delete/'):])
            if not team: self.redirect('/'); return
            data = load_team(team)
            if not self.check_admin_auth(team, data):
                return
            data['submissions'].pop(name, None)
            save_team(team, data)
            self.redirect('/admin?team=' + quote_plus(team))

        elif path == '/admin/generate':
            if not team: self.redirect('/'); return
            data = load_team(team)
            if not self.check_admin_auth(team, data):
                return
            wk   = data.get('week_start', '')
            subs = data.get('submissions', {})
            shift_mode = data.get('shift_mode', '3x8')
            if not wk or not PDF_OK:
                self.redirect('/admin?team=' + quote_plus(team) + '&msg=שגיאה+—+הגדר+תאריך'); return
            avail = {n: sub_to_avail(s) for n, s in subs.items()}
            prefs = parse_preferences(data.get('preferences', ''))
            sched, hrs, nh = auto_schedule(avail, prefs, shift_mode=shift_mode)
            data['last_schedule'] = sched
            data['last_hrs'] = hrs
            data['last_nh'] = nh
            save_team(team, data)
            # Go to edit page instead of downloading directly
            self.redirect('/admin/schedule?team=' + quote_plus(team))

        elif path == '/admin/downloads':
            if not team: self.redirect('/'); return
            data = load_team(team)
            if not self.check_admin_auth(team, data):
                return
            team_safe = ''.join(c if c.isalnum() or c in '-_' else '_' for c in team)
            m_ok = os.path.exists('/tmp/mgr_{}.pdf'.format(team_safe))
            e_ok = os.path.exists('/tmp/emp_{}.pdf'.format(team_safe))
            html = ('''<!DOCTYPE html><html dir="rtl" lang="he"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>הורדת קבצים</title>
<style>body{font-family:"Segoe UI",Arial,sans-serif;background:#edf2f7;color:#2d3748;
direction:rtl;padding:40px 20px}
.card{background:white;border-radius:14px;padding:30px;max-width:500px;margin:0 auto;
      box-shadow:0 2px 12px rgba(0,0,0,.1);text-align:center}
h2{color:#276749;margin-bottom:8px}p{color:#718096;font-size:14px;margin-bottom:24px}
.btn{display:block;width:100%;padding:14px;margin:10px 0;border:none;border-radius:10px;
     font-size:15px;font-weight:700;cursor:pointer;text-decoration:none;font-family:inherit}
.btn-blue{background:#2b6cb0;color:white}.btn-green{background:#276749;color:white}
.btn-back{background:#e2e8f0;color:#2d3748;margin-top:10px}</style></head>
<body><div class="card"><div style="font-size:52px">&#128196;</div>
<h2>&#9989; הסידור נוצר בהצלחה!</h2><p>לחץ/י להורדה:</p>'''
+ (f'<a href="/download/manager?team={quote_plus(team)}" class="btn btn-blue">&#8659; סידור מנהל (PDF)</a>' if m_ok else '')
+ (f'<a href="/download/employee?team={quote_plus(team)}" class="btn btn-green">&#8659; סידור עובדים (PDF)</a>' if e_ok else '')
+ f'<a href="/admin/schedule?team={quote_plus(team)}" class="btn btn-back">&#9998; חזרה לעריכת סידור</a>'
+ f'<a href="/admin?team={quote_plus(team)}" class="btn btn-back">&#8592; חזרה לניהול</a>'
+ '</div></body></html>')
            self.send_html(html)

        elif path == '/download/manager':
            team_safe = ''.join(c if c.isalnum() or c in '-_' else '_' for c in team)
            self._send_file('/tmp/mgr_{}.pdf'.format(team_safe), 'sidur_menahel.pdf')

        elif path == '/download/employee':
            team_safe = ''.join(c if c.isalnum() or c in '-_' else '_' for c in team)
            self._send_file('/tmp/emp_{}.pdf'.format(team_safe), 'sidur_ovdim.pdf')

        else:
            self.send_html('<h1 style="font-family:sans-serif">404</h1>', 404)

    def do_POST(self):
        parsed = urlparse(self.path)
        path   = parsed.path.rstrip('/')
        qs     = parse_qs(parsed.query)
        team   = unquote_plus(qs.get('team', [''])[0])
        body   = self.read_body()

        if path == '/submit':
            try:
                form   = json.loads(body.decode('utf-8'))
                name   = form.get('name', '').strip()
                if not name:
                    self.send_json({'ok': False, 'error': 'שם חסר'}, 400); return
                if not team:
                    self.send_json({'ok': False, 'error': 'צוות חסר'}, 400); return
                data   = load_team(team)
                shifts = form.get('shifts', {})
                avail  = defaultdict(list)
                for key, val in shifts.items():
                    if val and '__' in key:
                        day, shift = key.split('__', 1)
                        avail[day].append(shift)
                count = sum(len(v) for v in avail.values())
                data.setdefault('submissions', {})[name] = {
                    'shifts': {k: v for k, v in shifts.items() if v},
                    'notes': form.get('notes', ''),
                    'submitted_at': datetime.now().isoformat(),
                }
                save_team(team, data)
                self.send_json({'ok': True, 'count': count})
            except Exception as e:
                self.send_json({'ok': False, 'error': str(e)}, 500)

        elif path == '/admin/login':
            try:
                params = parse_qs(body.decode('utf-8'))
                password = params.get('password', [''])[0]
                if not team: self.redirect('/'); return
                data = load_team(team)
                admin_password = data.get('admin_password', '')
                if not admin_password:
                    # No password set yet, redirect to set-password
                    self.redirect('/admin/set-password?team=' + quote_plus(team)); return
                if password == admin_password:
                    hashed = hashlib.md5(admin_password.encode()).hexdigest()
                    self.send_response(302)
                    self.set_cookie(cookie_name(team), hashed, max_age=86400 * 7)
                    self.send_header('Location', f'/admin?team={quote_plus(team)}')
                    self.end_headers()
                else:
                    self.send_html(password_login_page(team, error='סיסמה שגויה, נסה שוב'))
            except Exception:
                self.send_html('<h2 style="color:red;text-align:center">שגיאה</h2>', 500)

        elif path == '/admin/set-password':
            try:
                params = parse_qs(body.decode('utf-8'))
                password  = params.get('password',  [''])[0]
                password2 = params.get('password2', [''])[0]
                if not team: self.redirect('/'); return
                if len(password) < 4:
                    self.send_html(set_password_page(team, error='הסיסמה חייבת להיות לפחות 4 תווים')); return
                if password != password2:
                    self.send_html(set_password_page(team, error='הסיסמאות אינן תואמות')); return
                data = load_team(team)
                data['admin_password'] = password
                save_team(team, data)
                hashed = hashlib.md5(password.encode()).hexdigest()
                self.send_response(302)
                self.set_cookie(cookie_name(team), hashed, max_age=86400 * 7)
                self.send_header('Location', f'/admin?team={quote_plus(team)}')
                self.end_headers()
            except Exception as e:
                self.send_html('<h2 style="color:red;text-align:center">שגיאה: ' + str(e) + '</h2>', 500)

        elif path == '/admin/setup':
            params = parse_qs(body.decode('utf-8'))
            if not team: self.redirect('/'); return
            data = load_team(team)
            if not self.check_admin_auth(team, data):
                return
            data['week_start']  = params.get('week_start', [''])[0]
            data['preferences'] = params.get('preferences', [''])[0]
            data['shift_mode']  = params.get('shift_mode', ['3x8'])[0]
            # Only update password if a new one was provided
            new_pwd = params.get('admin_password', [''])[0]
            if new_pwd:
                data['admin_password'] = new_pwd
                # Update auth cookie for new password
                hashed = hashlib.md5(new_pwd.encode()).hexdigest()
                self.send_response(302)
                self.set_cookie(cookie_name(team), hashed, max_age=86400 * 7)
                self.send_header('Location', '/admin?team=' + quote_plus(team))
                self.end_headers()
                save_team(team, data)
            else:
                save_team(team, data)
                self.redirect('/admin?team=' + quote_plus(team))

        elif path == '/admin/schedule/save':
            if not team: self.redirect('/'); return
            data = load_team(team)
            if not self.check_admin_auth(team, data):
                return
            # Parse the edited schedule from form
            params = parse_qs(body.decode('utf-8'))
            wk = data.get('week_start', '')
            shift_mode = data.get('shift_mode', '3x8')
            subs = data.get('submissions', {})
            avail = {n: sub_to_avail(s) for n, s in subs.items()}
            prefs = parse_preferences(data.get('preferences', ''))

            # Rebuild schedule from form fields
            sched = {d: {} for d in DAYS}
            if shift_mode == '2x12':
                shifts_list = ['בוקר', 'לילה']
            else:
                shifts_list = ['בוקר', 'צהריים', 'לילה']
            for day in DAYS:
                for sh in shifts_list:
                    field = f'sched__{day}__{sh}'
                    val = params.get(field, [''])[0].strip()
                    sched[day][sh] = val if val else None

            data['last_schedule'] = sched
            # Recalculate hours
            hrs = {emp: 0 for emp in avail}
            nh  = {emp: 0 for emp in avail}
            shift_hrs_map = {'בוקר': 12, 'לילה': 12} if shift_mode == '2x12' else {'בוקר': 8, 'צהריים': 8, 'לילה': 8}
            for day in DAYS:
                for sh, emp in sched[day].items():
                    if emp and emp in hrs:
                        hrs[emp] = hrs.get(emp, 0) + shift_hrs_map.get(sh, 8)
                        if sh == 'לילה':
                            nh[emp] = nh.get(emp, 0) + shift_hrs_map.get(sh, 8)
            save_team(team, data)

            # Generate PDFs
            if PDF_OK and wk:
                try:
                    wk_fmt = _normalize_wk(wk)
                    team_safe = ''.join(c if c.isalnum() or c in '-_' else '_' for c in team)
                    out_m = '/tmp/mgr_{}.pdf'.format(team_safe)
                    out_e = '/tmp/emp_{}.pdf'.format(team_safe)
                    make_pdf(sched, avail, hrs, nh, prefs, wk_fmt, out_m, mode='manager', shift_mode=shift_mode)
                    make_pdf(sched, avail, hrs, nh, prefs, wk_fmt, out_e, mode='employee', shift_mode=shift_mode)
                except Exception as e:
                    self.redirect('/admin?team=' + quote_plus(team) + '&msg=שגיאה+ביצירת+PDF'); return
            self.redirect('/admin/downloads?team=' + quote_plus(team))

        elif path == '/admin/clear':
            if not team: self.redirect('/'); return
            data = load_team(team)
            if not self.check_admin_auth(team, data):
                return
            data['submissions'] = {}
            save_team(team, data)
            self.redirect('/admin?team=' + quote_plus(team))

        elif path == '/create-team':
            try:
                form = json.loads(body.decode('utf-8'))
                name = form.get('team', '').strip()
                if not name:
                    self.send_json({'ok': False, 'error': 'שם ריק'}); return
                d = load_all()
                if name in d.get('teams', {}):
                    self.send_json({'ok': False, 'error': 'צוות כבר קיים'}); return
                d.setdefault('teams', {})[name] = {
                    'week_start': '',
                    'preferences': '',
                    'submissions': {},
                    'shift_mode': '3x8',
                    'admin_password': '',
                    'last_schedule': {},
                    'last_hrs': {},
                    'last_nh': {}
                }
                save_all(d)
                self.send_json({'ok': True})
            except Exception as e:
                self.send_json({'ok': False, 'error': str(e)})

        else:
            self.send_html('<h1>404</h1>', 404)

# ══════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════
if __name__ == '__main__':
    server = HTTPServer(('0.0.0.0', PORT), Handler)
    print('שרת פעיל על פורט', PORT)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('שרת נעצר.')
