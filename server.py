#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
מחולל סידור עבודה — שרת אינטרנט
=================================
הרצה:    python3 server.py
עובדים:  http://localhost:5050
מנהל:   http://localhost:5050/admin
"""

import os, sys, json, socket, threading, webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, unquote_plus
from datetime import datetime, timedelta
from collections import defaultdict

BASE   = os.path.dirname(os.path.abspath(__file__))
# On cloud (Railway etc.) use /tmp for writable storage; locally use BASE
STORAGE = os.environ.get('DATA_DIR', '/tmp' if not os.access(BASE, os.W_OK) else BASE)
DATA_F = os.path.join(STORAGE, 'data.json')
PORT   = int(os.environ.get('PORT', 5050))

sys.path.insert(0, BASE)
try:
    from schedule_gen import (auto_schedule, make_pdf,
                               parse_preferences, get_week_dates, fmt_date)
    PDF_OK = True
except Exception:
    PDF_OK = False

# ── constants ─────────────────────────────────────────────────
DAYS      = ['ראשון','שני','שלישי','רביעי','חמישי','שישי','שבת']
SHIFTS    = ['בוקר','צהריים','לילה']
HRS       = {'בוקר':'06:00–14:00','צהריים':'14:00–22:00','לילה':'22:00–06:00'}
WEEKEND   = {'שישי','שבת'}
MIN_ALL   = 10
MIN_NIGHT = 2
MIN_WKND  = 2

# ── helpers ────────────────────────────────────────────────────
def load():
    if os.path.exists(DATA_F):
        with open(DATA_F, encoding='utf-8') as f:
            return json.load(f)
    return {'week_start': '', 'preferences': '', 'submissions': {}}

def save(d):
    with open(DATA_F, 'w', encoding='utf-8') as f:
        json.dump(d, f, ensure_ascii=False, indent=2)

def get_ip():
    # On Railway use the public domain
    railway = os.environ.get('RAILWAY_PUBLIC_DOMAIN', '')
    if railway:
        return railway
    try:
        s = socket.socket()
        s.settimeout(1)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return '127.0.0.1'

def sub_to_avail(sub):
    avail = defaultdict(list)
    for key, val in sub.get('shifts', {}).items():
        if val and '__' in key:
            day, shift = key.split('__', 1)
            avail[day].append(shift)
    return dict(avail)

def week_label(wk):
    if not wk or not PDF_OK:
        return ''
    try:
        dates = get_week_dates(wk)
        return '{} – {}'.format(fmt_date(dates[0]), fmt_date(dates[6]))
    except Exception:
        return ''

def week_dates_json(wk):
    if not wk or not PDF_OK:
        return [''] * 7
    try:
        return [fmt_date(d) for d in get_week_dates(wk)]
    except Exception:
        return [''] * 7

# ══════════════════════════════════════════════════════════════
# EMPLOYEE FORM
# ══════════════════════════════════════════════════════════════
def employee_page(name_hint, wk):
    wlabel  = week_label(wk)
    dates   = week_dates_json(wk)

    subtitle = ('שבוע: ' + wlabel) if wlabel else 'מלא/י את הזמינות שלך לשבוע הקרוב'

    days_json   = json.dumps(DAYS,   ensure_ascii=False)
    shifts_json = json.dumps(SHIFTS, ensure_ascii=False)
    hrs_json    = json.dumps(HRS,    ensure_ascii=False)
    dates_json  = json.dumps(dates,  ensure_ascii=False)
    wknd_list   = json.dumps(list(WEEKEND), ensure_ascii=False)

    return '''<!DOCTYPE html>
<html dir="rtl" lang="he">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>טופס זמינות משמרות</title>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{
  --navy:#1a365d;--blue:#2b6cb0;--slate:#2d3748;
  --green:#276749;--red:#c53030;--gray:#718096;
  --mint:#f0fff4;--amber:#fffbeb;--ice:#ebf4ff;
  --dg:#48bb78;--da:#d69e2e;--dn:#4299e1;
  --border:#e2e8f0;
}
body{font-family:'Segoe UI',Arial,sans-serif;background:#edf2f7;color:var(--slate);direction:rtl;padding-bottom:40px}
.hdr{background:linear-gradient(135deg,var(--navy),#2c5282);color:white;padding:18px 20px;text-align:center}
.hdr h1{font-size:20px} .hdr p{font-size:12px;opacity:.75;margin-top:4px}
.card{background:white;border-radius:14px;padding:20px 22px;margin:18px auto;max-width:800px;box-shadow:0 2px 12px rgba(0,0,0,.08)}
label{display:block;font-weight:600;font-size:13px;color:var(--slate);margin-bottom:6px}
.hint{color:var(--gray);font-weight:400;font-size:11px}
input[type=text],textarea{width:100%;padding:10px 12px;border:1.5px solid var(--border);border-radius:8px;font-size:14px;font-family:inherit;direction:rtl}
input[type=text]:focus,textarea:focus{outline:none;border-color:var(--blue)}
textarea{min-height:80px;resize:vertical}
/* grid */
.grid-wrap{overflow-x:auto;margin-top:8px}
.sg{width:100%;border-collapse:collapse;min-width:540px}
.sg th,.sg td{border:1px solid var(--border)}
.th-day{background:var(--blue);color:white;text-align:center;padding:7px 4px;font-size:12px;font-weight:700}
.th-day .dd{font-size:9px;opacity:.78;font-weight:400;display:block;margin-top:2px}
.th-sh{background:var(--slate);color:white;text-align:center;padding:8px 6px;width:75px;font-size:11px}
.sh-hrs{font-size:9px;opacity:.72;display:block;margin-top:2px}
.cm{background:var(--mint)} .ca{background:var(--amber)} .cn{background:var(--ice)}
.cb-wrap{display:flex;align-items:center;justify-content:center;padding:6px 4px}
.cb-wrap input[type=checkbox]{width:20px;height:20px;cursor:pointer;accent-color:var(--blue)}
/* validation bar */
.vbar{display:flex;gap:10px;flex-wrap:wrap;margin-top:16px;padding:12px 14px;background:#f7fafc;border-radius:8px;border:1px solid var(--border)}
.vi{display:flex;align-items:center;gap:5px;font-size:12px;font-weight:600}
.badge{display:inline-flex;align-items:center;justify-content:center;min-width:26px;height:22px;padding:0 6px;border-radius:11px;font-size:11px;font-weight:700;transition:.2s}
.ok{background:#c6f6d5;color:#276749} .err{background:#fed7d7;color:#c53030}
.ico-ok{color:#48bb78;font-size:15px} .ico-err{color:#fc8181;font-size:15px}
/* submit */
.btn-sub{display:block;width:100%;padding:14px;background:var(--blue);color:white;border:none;border-radius:10px;font-size:16px;font-weight:700;cursor:pointer;font-family:inherit;margin-top:16px;transition:.2s}
.btn-sub:disabled{background:#a0aec0;cursor:not-allowed}
.btn-sub:not(:disabled):hover{background:#2c5282}
/* success */
.success{display:none;text-align:center;padding:30px 20px}
.success .big{font-size:56px;margin-bottom:12px}
.success h2{color:var(--green);font-size:22px}
.success p{color:var(--gray);margin-top:8px;font-size:14px}
.btn-again{display:inline-block;margin-top:20px;padding:10px 24px;background:var(--blue);color:white;border:none;border-radius:8px;font-size:14px;cursor:pointer;font-family:inherit}
</style>
</head>
<body>
<div class="hdr">
  <h1>&#128203; טופס זמינות משמרות</h1>
  <p>''' + subtitle + '''</p>
</div>

<div class="card" id="form-card">

  <div style="margin-bottom:16px">
    <label>&#128100; שמך המלא</label>
    <input type="text" id="emp-name" value="''' + name_hint + '''"
           placeholder="שם פרטי + משפחה" oninput="validate()">
  </div>

  <label>&#128197; בחר/י את המשמרות שאת/ה יכול/ה לעבוד
    <span class="hint">(לפחות ''' + str(MIN_ALL) + ''' משמרות)</span></label>

  <div class="grid-wrap">
    <table class="sg" id="grid">
      <thead id="grid-head"></thead>
      <tbody id="grid-body"></tbody>
    </table>
  </div>

  <div class="vbar">
    <div class="vi">
      <span id="ico-t" class="ico-err">&#10007;</span>
      <span>סה"כ: <span class="badge err" id="b-t">0</span>/''' + str(MIN_ALL) + '''+</span>
    </div>
    <div class="vi">
      <span id="ico-n" class="ico-err">&#10007;</span>
      <span>לילה: <span class="badge err" id="b-n">0</span>/''' + str(MIN_NIGHT) + '''+</span>
    </div>
    <div class="vi">
      <span id="ico-w" class="ico-err">&#10007;</span>
      <span>סופ"ש: <span class="badge err" id="b-w">0</span>/''' + str(MIN_WKND) + '''+
        <span class="hint" style="font-weight:400">&nbsp;(ש"ו–ש"ב)</span>
      </span>
    </div>
  </div>

  <div style="margin-top:16px">
    <label>&#128172; הערות / בקשות מיוחדות
      <span class="hint">(אופציונלי)</span></label>
    <textarea id="notes"
      placeholder="לדוגמה: מבקש לא לסדר ביום ד׳, מעדיף משמרות בוקר..."></textarea>
  </div>

  <button class="btn-sub" id="sub-btn" disabled onclick="doSubmit()">
    &#10003; שלח זמינות
  </button>
</div>

<div class="card success" id="ok-card">
  <div class="big">&#9989;</div>
  <h2>הזמינות נשלחה בהצלחה!</h2>
  <p id="ok-msg">תודה! הזמינות שלך נשמרה.</p>
  <button class="btn-again" onclick="location.reload()">&#128203; עדכן שוב</button>
</div>

<script>
const DAYS  = ''' + days_json + ''';
const SHFTS = ''' + shifts_json + ''';
const HRS   = ''' + hrs_json + ''';
const DATES = ''' + dates_json + ''';
const WKND  = new Set(''' + wknd_list + ''');
const CLS   = {'\u05d1\u05d5\u05e7\u05e8':'cm','\u05e6\u05d4\u05e8\u05d9\u05d9\u05dd':'ca','\u05dc\u05d9\u05dc\u05d4':'cn'};

// build grid
const head = document.getElementById('grid-head');
const body = document.getElementById('grid-body');

const hr = document.createElement('tr');
hr.innerHTML = '<th class="th-sh"></th>' +
  DAYS.map((d,i)=>'<th class="th-day">'+d+'<span class="dd">'+DATES[i]+'</span></th>').join('');
head.appendChild(hr);

SHFTS.forEach(sh=>{
  const tr = document.createElement('tr');
  let cells = '<td class="th-sh">'+sh+'<span class="sh-hrs">'+HRS[sh]+'</span></td>';
  DAYS.forEach(d=>{
    const id = d+'__'+sh;
    cells += '<td class="'+CLS[sh]+'">'
           + '<div class="cb-wrap"><input type="checkbox" id="'+id+'"'
           + ' data-day="'+d+'" data-shift="'+sh+'" onchange="validate()"></div></td>';
  });
  tr.innerHTML = cells;
  body.appendChild(tr);
});

function validate(){
  const cbs   = [...document.querySelectorAll('#grid input:checked')];
  const total = cbs.length;
  const nights= cbs.filter(c=>c.dataset.shift==='\u05dc\u05d9\u05dc\u05d4').length;
  const wknds = cbs.filter(c=>WKND.has(c.dataset.day)).length;
  const name  = document.getElementById('emp-name').value.trim();

  function upd(bid,iid,val,min){
    const ok=val>=min;
    const b=document.getElementById(bid);
    b.textContent=val; b.className='badge '+(ok?'ok':'err');
    const ic=document.getElementById(iid);
    ic.textContent=ok?'\u2713':'\u2717'; ic.className=ok?'ico-ok':'ico-err';
    return ok;
  }
  const t=upd('b-t','ico-t',total,''' + str(MIN_ALL) + ''');
  const n=upd('b-n','ico-n',nights,''' + str(MIN_NIGHT) + ''');
  const w=upd('b-w','ico-w',wknds,''' + str(MIN_WKND) + ''');
  document.getElementById('sub-btn').disabled=!(t&&n&&w&&name.length>1);
}

function doSubmit(){
  const name  = document.getElementById('emp-name').value.trim();
  const notes = document.getElementById('notes').value.trim();
  const shifts={};
  document.querySelectorAll('#grid input[type=checkbox]').forEach(cb=>{
    shifts[cb.id]=cb.checked;
  });
  fetch('/submit',{
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({name,shifts,notes})
  })
  .then(r=>r.json())
  .then(r=>{
    if(r.ok){
      document.getElementById('form-card').style.display='none';
      const ok=document.getElementById('ok-card');
      ok.style.display='block';
      document.getElementById('ok-msg').textContent='תודה '+name+'! '+r.count+' משמרות נשמרו.';
    }else alert('שגיאה: '+r.error);
  })
  .catch(()=>alert('שגיאת חיבור'));
}
validate();
</script>
</body>
</html>'''

# ══════════════════════════════════════════════════════════════
# ADMIN PAGE
# ══════════════════════════════════════════════════════════════
def admin_page(data, flash=''):
    subs  = data.get('submissions', {})
    wk    = data.get('week_start', '')
    prefs = data.get('preferences', '')
    ip    = get_ip()
    wl    = week_label(wk)

    # flash message
    flash_html = ''
    if flash:
        flash_html = ('<div style="background:#c6f6d5;color:#276749;padding:10px 14px;'
                      'border-radius:8px;margin-bottom:16px;font-weight:600">'
                      + flash + '</div>')

    # week label span
    wl_span = ''
    if wl:
        wl_span = ('<span style="font-size:13px;margin-right:12px;'
                   'color:#276749;font-weight:600">&#10003; ' + wl + '</span>')

    # submissions table rows
    rows = ''
    for name, sub in sorted(subs.items()):
        avail  = sub_to_avail(sub)
        total  = sum(len(v) for v in avail.values())
        nights = sum(1 for ss in avail.values() for s in ss if s == 'לילה')
        wknds  = sum(1 for d, ss in avail.items() for s in ss if d in WEEKEND)
        valid  = total >= MIN_ALL and nights >= MIN_NIGHT and wknds >= MIN_WKND

        def col(v, ok):
            c = '#276749' if ok else '#c53030'
            return '<span style="font-weight:700;color:{}">{}</span>'.format(c, v)

        # compact shift dots
        dots = ''
        for day in DAYS:
            ss = avail.get(day, [])
            if ss:
                lbl = ''.join({'בוקר':'ב','צהריים':'צ','לילה':'ל'}[s] for s in ss)
                dots += ('<span title="{}" style="font-size:9px;background:#ebf4ff;'
                         'border-radius:3px;padding:1px 3px;margin:1px">'
                         '{} {}</span>').format(day, day[:2], lbl)

        notes_txt = sub.get('notes','') or '—'
        ts        = sub.get('submitted_at','')[:16].replace('T',' ')
        icon      = '&#9989;' if valid else '&#9888;&#65039;'
        del_url   = '/admin/delete/' + name.replace(' ', '+')

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
        clear_btn = ('<form method="POST" action="/admin/clear" style="margin-top:12px">'
                     '<button class="btn btn-red" '
                     'onclick="return confirm(\'מחק את כל ההגשות?\');">'
                     '&#128465; נקה הכל</button></form>')

    # generate section
    if not PDF_OK:
        gen_html = '<p style="color:#c53030;font-weight:600">&#9888; schedule_gen.py לא נמצא</p>'
    elif not wk:
        gen_html = '<p style="color:#c53030;font-weight:600">&#9888; הגדר תאריך שבוע תחילה</p>'
    else:
        gen_html = ('<div style="display:flex;gap:10px;flex-wrap:wrap">'
                    '<a href="/admin/generate" class="btn btn-green">'
                    '&#128203; צור סידור + הורד PDFs</a></div>'
                    '<p style="font-size:11px;color:#718096;margin-top:8px">'
                    'יוצר 2 קבצי PDF: אחד למנהל (עם זמינויות) ואחד לעובדים</p>')

    return '''<!DOCTYPE html>
<html dir="rtl" lang="he">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ניהול סידור עבודה</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Segoe UI',Arial,sans-serif;background:#edf2f7;color:#2d3748;direction:rtl}
.hdr{background:linear-gradient(135deg,#1a365d,#2c5282);color:white;padding:14px 24px;
     display:flex;justify-content:space-between;align-items:center}
.hdr h1{font-size:18px}
.hdr a{color:white;font-size:13px;text-decoration:none;opacity:.8}
.con{max-width:1100px;margin:0 auto;padding:20px}
.card{background:white;border-radius:12px;padding:20px 22px;margin-bottom:18px;
      box-shadow:0 2px 10px rgba(0,0,0,.07)}
.card h2{font-size:15px;margin-bottom:14px;color:#2d3748;
         border-bottom:1px solid #e2e8f0;padding-bottom:8px}
label{font-size:13px;font-weight:600;margin-bottom:5px;display:block}
input[type=date],input[type=text],textarea{
  width:100%;padding:9px 11px;border:1.5px solid #e2e8f0;border-radius:7px;
  font-size:13px;font-family:inherit;direction:rtl}
input:focus,textarea:focus{outline:none;border-color:#2b6cb0}
textarea{min-height:75px;resize:vertical}
.btn{display:inline-block;padding:9px 20px;border:none;border-radius:7px;
     font-size:13px;font-weight:700;cursor:pointer;font-family:inherit;
     text-decoration:none;transition:.15s}
.btn-blue{background:#2b6cb0;color:white} .btn-blue:hover{background:#2c5282}
.btn-green{background:#276749;color:white} .btn-green:hover{background:#22543d}
.btn-red{background:#c53030;color:white} .btn-red:hover{background:#9b2c2c}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.link-box{background:#ebf8ff;border:1px solid #90cdf4;border-radius:8px;
          padding:10px 14px;font-size:13px;word-break:break-all;margin-bottom:8px}
.link-box strong{display:block;font-size:11px;color:#2b6cb0;margin-bottom:3px}
table{width:100%;border-collapse:collapse}
th{background:#2d3748;color:white;padding:8px;text-align:right;
   font-size:11px;font-weight:600}
td{padding:8px;border-bottom:1px solid #f0f4f8;font-size:12px;vertical-align:middle}
tr:hover td{background:#f7fafc}
.nbig{font-size:22px;font-weight:800;color:#2b6cb0}
@media(max-width:640px){.grid2{grid-template-columns:1fr}}
</style>
</head>
<body>
<div class="hdr">
  <h1>&#9881;&#65039; לוח ניהול סידור עבודה</h1>
  <a href="/" target="_blank">&#128203; טופס עובדים &#8599;</a>
</div>
<div class="con">
''' + flash_html + '''
<!-- setup -->
<div class="card">
  <h2>&#128197; הגדרות שבוע</h2>
  <form method="POST" action="/admin/setup">
    <div class="grid2">
      <div>
        <label>תאריך יום ראשון של השבוע</label>
        <input type="date" name="week_start" value="''' + wk + '''" required>
      </div>
      <div>
        <label>העדפות עובדים (אופציונלי)</label>
        <textarea name="preferences"
          placeholder="דביר יונה: מעדיף לילה&#10;שרה כהן: מעדיפה בוקר">''' + prefs + '''</textarea>
      </div>
    </div>
    <div style="margin-top:12px;display:flex;align-items:center;gap:12px">
      <button type="submit" class="btn btn-blue">&#128190; שמור הגדרות</button>
      ''' + wl_span + '''
    </div>
  </form>
</div>

<!-- links -->
<div class="card">
  <h2>&#128279; קישורים לשיתוף עם עובדים</h2>
  <div class="link-box">
    <strong>קישור כללי (העובד מזין שמו):</strong>
    http://''' + ip + ':' + str(PORT) + '''/
  </div>
  <p style="font-size:11px;color:#718096">
    &#128161; קישור אישי עם שם מולא מראש:
    <code>http://''' + ip + ':' + str(PORT) + '''/?name=שם+העובד</code>
  </p>
  <p style="font-size:11px;color:#718096;margin-top:4px">
    &#128241; וודא שהמחשב והעובדים מחוברים לאותה רשת Wi-Fi
  </p>
</div>

<!-- submissions -->
<div class="card">
  <h2>&#128203; הגשות שהתקבלו &nbsp;<span class="nbig">''' + str(len(subs)) + '''</span></h2>
  <table>
    <thead>
      <tr>
        <th>עובד</th>
        <th style="text-align:center">סה"כ</th>
        <th style="text-align:center">לילות</th>
        <th style="text-align:center">סופ"ש</th>
        <th>בחירות</th>
        <th>הערות</th>
        <th>זמן</th>
        <th>&#128465;</th>
      </tr>
    </thead>
    <tbody>''' + rows + '''</tbody>
  </table>
  ''' + clear_btn + '''
</div>

<!-- generate -->
<div class="card">
  <h2>&#9889; יצירת סידור</h2>
  ''' + gen_html + '''
</div>

</div>
</body>
</html>'''

# ══════════════════════════════════════════════════════════════
# HTTP HANDLER
# ══════════════════════════════════════════════════════════════
class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def send_html(self, html, code=200):
        enc = html.encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(enc)))
        self.end_headers()
        self.wfile.write(enc)

    def _send_file(self, filepath, download_name):
        if not os.path.exists(filepath):
            self.send_html('<h2>קובץ לא נמצא — צור סידור תחילה</h2>', 404)
            return
        with open(filepath, 'rb') as f:
            data = f.read()
        self.send_response(200)
        self.send_header('Content-Type', 'application/pdf')
        self.send_header('Content-Disposition', f'attachment; filename="{download_name}"')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_json(self, obj, code=200):
        enc = json.dumps(obj, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(enc)))
        self.end_headers()
        self.wfile.write(enc)

    def redirect(self, loc):
        self.send_response(302)
        self.send_header('Location', loc)
        self.end_headers()

    def read_body(self):
        n = int(self.headers.get('Content-Length', 0))
        return self.rfile.read(n)

    # ── GET ──────────────────────────────────────
    def do_GET(self):
        parsed = urlparse(self.path)
        path   = parsed.path.rstrip('/')
        qs     = parse_qs(parsed.query)

        if path in ('', '/'):
            name = unquote_plus(qs.get('name', [''])[0])
            data = load()
            self.send_html(employee_page(name, data.get('week_start', '')))

        elif path == '/admin':
            flash = unquote_plus(qs.get('msg', [''])[0])
            self.send_html(admin_page(load(), flash))

        elif path.startswith('/admin/delete/'):
            name = unquote_plus(path[len('/admin/delete/'):])
            data = load()
            data['submissions'].pop(name, None)
            save(data)
            self.redirect('/admin')

        elif path == '/admin/generate':
            data = load()
            wk   = data.get('week_start', '')
            subs = data.get('submissions', {})
            if not wk or not PDF_OK:
                self.redirect('/admin?msg=שגיאה+—+הגדר+תאריך')
                return
            avail = {n: sub_to_avail(s) for n, s in subs.items()}
            prefs = parse_preferences(data.get('preferences', ''))
            sched, hrs, nh = auto_schedule(avail, prefs)
            out_m = os.path.join('/tmp', 'סידור_עבודה_מנהל.pdf')
            out_e = os.path.join('/tmp', 'סידור_עבודה_לעובדים.pdf')
            make_pdf(sched, avail, hrs, nh, prefs, wk, out_m, mode='manager')
            make_pdf(sched, avail, hrs, nh, prefs, wk, out_e, mode='employee')
            self.redirect('/admin/downloads')

        elif path == '/admin/downloads':
            m_ok = os.path.exists('/tmp/סידור_עבודה_מנהל.pdf')
            e_ok = os.path.exists('/tmp/סידור_עבודה_לעובדים.pdf')
            html = '''<!DOCTYPE html><html dir="rtl" lang="he"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>הורדת קבצים</title>
<style>body{font-family:"Segoe UI",Arial,sans-serif;background:#edf2f7;color:#2d3748;direction:rtl;padding:40px 20px}
.card{background:white;border-radius:14px;padding:30px;max-width:500px;margin:0 auto;box-shadow:0 2px 12px rgba(0,0,0,.1);text-align:center}
h2{color:#276749;margin-bottom:8px} p{color:#718096;font-size:14px;margin-bottom:24px}
.btn{display:block;width:100%;padding:14px;margin:10px 0;border:none;border-radius:10px;
     font-size:15px;font-weight:700;cursor:pointer;text-decoration:none;font-family:inherit}
.btn-blue{background:#2b6cb0;color:white} .btn-green{background:#276749;color:white}
.btn-back{background:#e2e8f0;color:#2d3748;margin-top:20px}
</style></head><body><div class="card">
<div style="font-size:52px">📄</div>
<h2>הסידור נוצר בהצלחה!</h2>
<p>לחץ/י להורדה:</p>
''' + (f'<a href="/download/manager" class="btn btn-blue">⬇ סידור מנהל (עם זמינויות)</a>' if m_ok else '') + \
    (f'<a href="/download/employee" class="btn btn-green">⬇ סידור עובדים</a>' if e_ok else '') + \
    '<a href="/admin" class="btn btn-back">← חזרה לניהול</a></div></body></html>'
            self.send_html(html)

        elif path == '/download/manager':
            self._send_file('/tmp/סידור_עבודה_מנהל.pdf', 'סידור_עבודה_מנהל.pdf')

        elif path == '/download/employee':
            self._send_file('/tmp/סידור_עבודה_לעובדים.pdf', 'סידור_עבודה_לעובדים.pdf')

        else:
            self.send_html('<h1 style="font-family:sans-serif">404</h1>', 404)

    # ── POST ─────────────────────────────────────
    def do_POST(self):
        parsed = urlparse(self.path)
        path   = parsed.path.rstrip('/')
        body   = self.read_body()

        if path == '/submit':
            try:
                form   = json.loads(body.decode('utf-8'))
                name   = form.get('name', '').strip()
                if not name:
                    self.send_json({'ok': False, 'error': 'שם חסר'}, 400)
                    return
                data   = load()
                shifts = form.get('shifts', {})
                avail  = defaultdict(list)
                for key, val in shifts.items():
                    if val and '__' in key:
                        day, shift = key.split('__', 1)
                        avail[day].append(shift)
                count = sum(len(v) for v in avail.values())
                data['submissions'][name] = {
                    'shifts':       {k: v for k, v in shifts.items() if v},
                    'notes':        form.get('notes', ''),
                    'submitted_at': datetime.now().isoformat(),
                }
                save(data)
                self.send_json({'ok': True, 'count': count})
            except Exception as e:
                self.send_json({'ok': False, 'error': str(e)}, 500)

        elif path == '/admin/setup':
            params = parse_qs(body.decode('utf-8'))
            data   = load()
            data['week_start']  = params.get('week_start', [''])[0]
            data['preferences'] = params.get('preferences', [''])[0]
            save(data)
            self.redirect('/admin')

        elif path == '/admin/clear':
            data = load()
            data['submissions'] = {}
            save(data)
            self.redirect('/admin')

        else:
            self.send_html('<h1>404</h1>', 404)

# ══════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════
if __name__ == '__main__':
    ip     = get_ip()
    server = HTTPServer(('0.0.0.0', PORT), Handler)

    print('''
╔══════════════════════════════════════════════════╗
║  שרת סידור עבודה פעיל!                          ║
╠══════════════════════════════════════════════════╣
║                                                  ║
║  טופס עובדים (שתף קישור זה):                    ║
║  http://{}:{}                         ║
║                                                  ║
║  לוח ניהול (למנהל בלבד):                        ║
║  http://localhost:{}/admin               ║
║                                                  ║
║  עצירה: Ctrl+C                                   ║
╚══════════════════════════════════════════════════╝
'''.format(ip, PORT, PORT))

    threading.Timer(
        0.6,
        lambda: webbrowser.open('http://localhost:{}/admin'.format(PORT))
    ).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nשרת נעצר.')
