#!/usr/bin/env python3
"""
מחולל סידור עבודה שבועי  v2
Weekly Work Schedule Generator

Format:  שם עובד: א-ב,צ, ב-ב,ל, ג-צ,ל
Days:    א=ראשון  ב=שני  ג=שלישי  ד=רביעי  ה=חמישי  ו=שישי  ש=שבת
Shifts:  ב=בוקר(06-14)  צ=צהריים(14-22)  ל=לילה(22-06)
"""

import re, os
from collections import defaultdict
from datetime import datetime, timedelta
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import landscape, A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# ─────────────────────────────────────────────
# FONT SETUP
# ─────────────────────────────────────────────
FONT = FONT_B = 'Helvetica'
_BASE = os.path.dirname(os.path.abspath(__file__))
for fp, fn in [
    (os.path.join(_BASE, 'DejaVuSans.ttf'),      'DV'),
    (os.path.join(_BASE, 'DejaVuSans-Bold.ttf'), 'DVB'),
    ('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',      'DV'),
    ('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 'DVB'),
]:
    if os.path.exists(fp):
        try:
            pdfmetrics.registerFont(TTFont(fn, fp))
            if 'Bold' not in fp: FONT  = fn
            else:                FONT_B = fn
        except: pass

# ─────────────────────────────────────────────
# HEBREW RTL
# ─────────────────────────────────────────────
def H(text):
    text = str(text)
    if not any('\u05D0' <= c <= '\u05EA' for c in text):
        return text
    segs = re.split(r'([\u0590-\u05FF ]+)', text)
    out  = [s[::-1] if s and '\u05D0' <= s[0] <= '\u05EA' else s for s in segs]
    return ''.join(reversed(out))

# ─────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────
DAY_MAP    = {'א':'ראשון','ב':'שני','ג':'שלישי','ד':'רביעי',
              'ה':'חמישי','ו':'שישי','ש':'שבת'}
SHIFT_MAP  = {'ב':'בוקר','צ':'צהריים','ל':'לילה'}
DAYS       = ['ראשון','שני','שלישי','רביעי','חמישי','שישי','שבת']
SHIFTS     = ['בוקר','צהריים','לילה']
SHIFT_HRS  = {'בוקר':'06:00-14:00','צהריים':'14:00-22:00','לילה':'22:00-06:00'}
SHIFT_SH   = {'בוקר':'ב','צהריים':'צ','לילה':'ל'}
WEEKENDS   = {'שישי','שבת'}

# ─────────────────────────────────────────────
# PARSER — availability messages
# ─────────────────────────────────────────────
def parse(text: str) -> dict:
    result = {}
    for line in text.strip().splitlines():
        line = line.strip()
        if not line or ':' not in line:
            continue
        i    = line.index(':')
        name = line[:i].strip()
        body = line[i+1:]
        avail = defaultdict(list)
        for day_ch, shifts_str in re.findall(r'([אבגדהוש])\s*-\s*([בצל,\s]+)', body):
            day = DAY_MAP.get(day_ch)
            if day:
                avail[day] = [SHIFT_MAP[s] for s in re.findall(r'[בצל]', shifts_str)]
        if name:
            result[name] = dict(avail)
    return result

# ─────────────────────────────────────────────
# PARSER — preferences
# ─────────────────────────────────────────────
def parse_preferences(text: str) -> dict:
    """
    Format:  שם עובד: מעדיף לילה   /  מעדיף בוקר  /  מעדיף צהריים
    Returns: {name: {shift: boost_weight}}  boost > 1 = preference
    """
    prefs = {}
    kw_shift = {'לילה': 'לילה', 'ערב': 'לילה', 'בוקר': 'בוקר',
                'צהריים': 'צהריים', 'אחהצ': 'צהריים'}
    for line in text.strip().splitlines():
        line = line.strip()
        if not line or ':' not in line:
            continue
        i    = line.index(':')
        name = line[:i].strip()
        desc = line[i+1:]
        boost = {}
        for kw, shift in kw_shift.items():
            if kw in desc:
                boost[shift] = 3.0   # strong preference weight
        if boost:
            prefs[name] = boost
    return prefs

# ─────────────────────────────────────────────
# AUTO-SCHEDULER
#   1. Night shifts distributed as evenly as possible
#   2. Preference weighting applied
#   3. General fairness (total hours) for day shifts
#   4. No double shifts in 24h (no 2 shifts same day)
#   5. Night-to-morning gap constraint (8h min)
# ─────────────────────────────────────────────
def auto_schedule(avail: dict, prefs: dict = None, shift_mode='3x8') -> tuple:
    prefs     = prefs or {}

    # Choose shifts and hours based on mode
    if shift_mode == '2x12':
        shifts = ['בוקר', 'לילה']
        shift_hrs_map = {'בוקר': 12, 'לילה': 12}
        day_shifts = ['בוקר', 'לילה']
    else:  # '3x8' default
        shifts = ['בוקר', 'צהריים', 'לילה']
        shift_hrs_map = {'בוקר': 8, 'צהריים': 8, 'לילה': 8}
        day_shifts = ['בוקר', 'צהריים', 'לילה']

    sched     = {d: {s: None for s in shifts} for d in DAYS}
    hours     = {emp: 0 for emp in avail}
    night_hrs = {emp: 0 for emp in avail}
    emp_assignments = {emp: [] for emp in avail}  # Track (day, shift) assignments per employee

    # How many night shifts is each employee available for (capacity)?
    night_cap = {
        emp: max(sum(1 for d in DAYS if 'לילה' in avail[emp].get(d, [])), 1)
        for emp in avail
    }

    def sort_key(emp, shift):
        emp_boost = prefs.get(emp, {}).get(shift, 1.0)  # >1 prefers this shift
        night_boost = prefs.get(emp, {}).get('לילה', 1.0)

        if shift == 'לילה':
            # Proportion of night capacity already used — lower = gets priority
            proportion = night_hrs[emp] / night_cap[emp]
            # Employees who prefer nights get extra priority (lower sort score)
            return proportion / emp_boost
        else:
            # Total hours fairness
            # Employees who prefer nights are slightly deprioritised for day shifts
            # so their nights remain available
            return (hours[emp] / emp_boost) * (night_boost ** 0.4)

    def can_assign(emp, day, shift):
        """Check if employee can be assigned this shift without violating constraints."""
        # Constraint 1: Employee must be available for this shift
        if shift not in avail[emp].get(day, []):
            return False

        # Constraint 2: No double shifts on same day (only one shift per day)
        if any(d == day for d, s in emp_assignments[emp]):
            return False

        # Constraint 3: Night-to-morning gap constraint
        # If employee works night on day X, cannot work בוקר on day X+1
        if shift == 'בוקר':
            day_idx = DAYS.index(day)
            if day_idx > 0:
                prev_day = DAYS[day_idx - 1]
                if (prev_day, 'לילה') in emp_assignments[emp]:
                    return False

        return True

    # ── Assign shifts in order: nights first, then others
    for shift in ['לילה'] + [s for s in day_shifts if s != 'לילה']:
        for d in DAYS:
            candidates = [e for e in avail if can_assign(e, d, shift)]
            if not candidates:
                continue
            candidates.sort(key=lambda e: sort_key(e, shift))
            chosen = candidates[0]
            sched[d][shift] = chosen
            hours[chosen] += shift_hrs_map[shift]
            emp_assignments[chosen].append((d, shift))
            if shift == 'לילה':
                night_hrs[chosen] += shift_hrs_map[shift]

    return sched, hours, night_hrs

# ─────────────────────────────────────────────
# DATE UTILS
# ─────────────────────────────────────────────
def get_week_dates(week_start: str) -> list:
    """Parse 'DD.MM.YYYY' and return list of 7 date objects (Sun→Sat)."""
    start = datetime.strptime(week_start, '%d.%m.%Y')
    return [start + timedelta(days=i) for i in range(7)]

def fmt_date(d) -> str:
    return d.strftime('%d.%m')

# ─────────────────────────────────────────────
# PDF GENERATOR
# ─────────────────────────────────────────────
def make_pdf(sched, avail, hrs, night_hrs, prefs, week, output, mode='manager', shift_mode='3x8'):
    # Determine shifts and hours based on mode
    if shift_mode == '2x12':
        SHIFTS_LOCAL = ['בוקר', 'לילה']
        SHIFT_HRS_LOCAL = {'בוקר': '06:00-18:00', 'לילה': '18:00-06:00'}
    else:  # '3x8' default
        SHIFTS_LOCAL = ['בוקר', 'צהריים', 'לילה']
        SHIFT_HRS_LOCAL = {'בוקר': '06:00-14:00', 'צהריים': '14:00-22:00', 'לילה': '22:00-06:00'}

    PW, PH = landscape(A4)
    c = canvas.Canvas(output, pagesize=landscape(A4))
    MX, MY = 1.0*cm, 0.65*cm
    TW = PW - 2*MX

    # ── Palette ──────────────────────────────
    NAVY      = colors.HexColor('#1a365d')
    BLUE      = colors.HexColor('#2b6cb0')
    SLATE     = colors.HexColor('#2d3748')
    # Shift colours (used for BOTH main table cells and dots)
    SH_LIGHT  = {'בוקר': colors.HexColor('#f0fff4'),   # mint
                 'צהריים': colors.HexColor('#fffbeb'),  # amber
                 'לילה':   colors.HexColor('#ebf4ff')}  # ice blue
    SH_MED    = {'בוקר': colors.HexColor('#48bb78'),
                 'צהריים': colors.HexColor('#d69e2e'),
                 'לילה':   colors.HexColor('#4299e1')}
    MISS_BG   = colors.HexColor('#fed7d7')
    WHITE     = colors.white
    GREEN_TXT = colors.HexColor('#276749')
    RED_TXT   = colors.HexColor('#c53030')
    GRAY_TXT  = colors.HexColor('#718096')
    AVAIL_BG  = colors.HexColor('#f7fafc')
    PREF_CLR  = colors.HexColor('#744210')   # amber-dark for preference tags

    # ── Dimensions ───────────────────────────
    TITLE_H  = 1.3*cm
    HDR_H    = 0.75*cm
    LBL_W    = 3.1*cm
    DAY_W    = (TW - LBL_W) / 7
    SHIFT_H  = 1.6*cm
    AV_HDR_H = 0.58*cm
    AV_ROW_H = 0.62*cm

    # Parse dates
    week_dates = get_week_dates(week)
    week_label = f'{fmt_date(week_dates[0])} – {fmt_date(week_dates[6])}'

    y = PH - MY

    # ════════════════════════════════════════
    # TITLE BAR
    # ════════════════════════════════════════
    ty = y - TITLE_H
    c.setFillColor(NAVY)
    c.rect(MX, ty, TW, TITLE_H, fill=1, stroke=0)
    c.setFillColor(WHITE)
    c.setFont(FONT_B, 17)
    suffix = H('לעובדים') if mode == 'employee' else H('')
    c.drawCentredString(PW/2, ty + TITLE_H*0.55,
        H('סידור עבודה שבועי') + (f'  —  {suffix}' if mode=='employee' else ''))
    c.setFont(FONT, 8.5)
    c.drawString(MX+0.4*cm, ty+0.17*cm, f'Week: {week_label}')
    y = ty

    # ════════════════════════════════════════
    # DAY HEADER ROW  (with date below name)
    # ════════════════════════════════════════
    hy = y - HDR_H
    c.setFillColor(SLATE)
    c.rect(MX, hy, LBL_W, HDR_H, fill=1, stroke=1)
    c.setFillColor(WHITE); c.setFont(FONT, 8)
    c.drawCentredString(MX+LBL_W/2, hy+HDR_H*0.38, H('משמרת'))

    for i, day in enumerate(DAYS):
        x = MX + LBL_W + i*DAY_W
        c.setFillColor(BLUE)
        c.rect(x, hy, DAY_W, HDR_H, fill=1, stroke=1)
        c.setFillColor(WHITE)
        # Day name (upper)
        c.setFont(FONT_B, 10)
        c.drawCentredString(x+DAY_W/2, hy+HDR_H*0.58, H(day))
        # Date (lower, smaller)
        c.setFont(FONT, 7.5)
        c.drawCentredString(x+DAY_W/2, hy+HDR_H*0.15, fmt_date(week_dates[i]))
    y = hy

    # ════════════════════════════════════════
    # SHIFT ROWS — colored by shift type, not day
    # ════════════════════════════════════════
    for shift in SHIFTS_LOCAL:
        ry = y - SHIFT_H
        bg_light = SH_LIGHT[shift]

        # Shift label cell
        c.setFillColor(SLATE)
        c.rect(MX, ry, LBL_W, SHIFT_H, fill=1, stroke=1)
        c.setFillColor(WHITE); c.setFont(FONT_B, 10)
        c.drawCentredString(MX+LBL_W/2, ry+SHIFT_H*0.62, H(shift))
        c.setFont(FONT, 8)
        c.drawCentredString(MX+LBL_W/2, ry+SHIFT_H*0.25, SHIFT_HRS_LOCAL[shift])

        for di, day in enumerate(DAYS):
            x   = MX + LBL_W + di*DAY_W
            emp = sched[day][shift]
            bg  = MISS_BG if emp is None else bg_light

            c.setFillColor(bg)
            c.rect(x, ry, DAY_W, SHIFT_H, fill=1, stroke=1)

            if emp:
                c.setFillColor(GREEN_TXT); c.setFont(FONT_B, 9)
                c.drawCentredString(x+DAY_W/2, ry+SHIFT_H*0.62, H(emp))
                # edit underline
                c.setStrokeColor(colors.HexColor('#c6f6d5'))
                c.setLineWidth(0.5)
                c.line(x+0.2*cm, ry+SHIFT_H*0.3, x+DAY_W-0.2*cm, ry+SHIFT_H*0.3)
            else:
                c.setFillColor(RED_TXT); c.setFont(FONT, 8)
                c.drawCentredString(x+DAY_W/2, ry+SHIFT_H*0.62, H('אין כיסוי'))
                c.setStrokeColor(colors.HexColor('#fc8181'))
                c.setLineWidth(0.7)
                c.line(x+0.2*cm, ry+SHIFT_H*0.3, x+DAY_W-0.2*cm, ry+SHIFT_H*0.3)
        y = ry

    # ════════════════════════════════════════
    # AVAILABILITY TABLE  (manager only)
    # ════════════════════════════════════════
    if mode == 'employee':
        c.save()
        return

    y -= 0.3*cm
    c.setFillColor(SLATE); c.setFont(FONT_B, 9)
    c.drawString(MX, y-0.27*cm, H('זמינות עובדים:'))
    y -= 0.43*cm

    # Header row
    c.setFillColor(SLATE)
    c.rect(MX, y-AV_HDR_H, LBL_W, AV_HDR_H, fill=1, stroke=1)
    c.setFillColor(WHITE); c.setFont(FONT, 7)
    c.drawCentredString(MX+LBL_W/2, y-AV_HDR_H*0.58, H('עובד  |  שעות  |  לילות'))

    for i, day in enumerate(DAYS):
        x = MX + LBL_W + i*DAY_W
        c.setFillColor(BLUE)
        c.rect(x, y-AV_HDR_H, DAY_W, AV_HDR_H, fill=1, stroke=1)
        c.setFillColor(WHITE); c.setFont(FONT, 7)
        c.drawCentredString(x+DAY_W/2, y-AV_HDR_H*0.58, H(day))
    y -= AV_HDR_H

    # Employee rows
    for emp in sorted(avail.keys()):
        ry         = y - AV_ROW_H
        total_h    = hrs.get(emp, 0)
        n_nights   = night_hrs.get(emp, 0) // (12 if shift_mode == '2x12' else 8)
        emp_prefs  = prefs.get(emp, {})

        # Name + stats cell
        c.setFillColor(AVAIL_BG)
        c.rect(MX, ry, LBL_W, AV_ROW_H, fill=1, stroke=1)
        c.setFillColor(SLATE); c.setFont(FONT, 7.5)
        c.drawString(MX+0.15*cm, ry+AV_ROW_H*0.52, H(emp))

        # hours + night count
        stats = f'{total_h}h | {n_nights}🌙'
        c.setFillColor(GRAY_TXT); c.setFont(FONT, 6.5)
        c.drawString(MX+0.15*cm, ry+AV_ROW_H*0.1, stats)

        # Preference tag if any
        if emp_prefs:
            pref_shifts = [s for s in SHIFTS_LOCAL if emp_prefs.get(s, 1) > 1]
            tag = 'מעדיף: ' + ', '.join(pref_shifts)
            c.setFillColor(PREF_CLR); c.setFont(FONT, 5.5)
            tag_x = MX + LBL_W - 0.15*cm
            c.drawRightString(tag_x, ry+AV_ROW_H*0.65, H(tag))

        # Day cells
        for di, day in enumerate(DAYS):
            x          = MX + LBL_W + di*DAY_W
            day_shifts = avail[emp].get(day, [])

            c.setFillColor(WHITE)
            c.rect(x, ry, DAY_W, AV_ROW_H, fill=1, stroke=1)

            if day_shifts:
                dot_r  = AV_ROW_H * 0.26
                slot_w = DAY_W / len(SHIFTS_LOCAL)
                for si, sh in enumerate(SHIFTS_LOCAL):
                    if sh not in day_shifts:
                        continue
                    cx  = x + slot_w*(si+0.5)
                    cy  = ry + AV_ROW_H*0.5
                    assigned = (sched[day][sh] == emp)
                    c.setFillColor(SH_MED[sh])
                    c.circle(cx, cy, dot_r, fill=1, stroke=0)
                    if assigned:
                        c.setStrokeColor(SLATE); c.setLineWidth(1.0)
                        c.circle(cx, cy, dot_r, fill=0, stroke=1)
                        c.setLineWidth(0.5)
                    c.setFillColor(WHITE); c.setFont(FONT, 5)
                    shift_ch = {'בוקר':'ב','צהריים':'צ','לילה':'ל'}.get(sh, '?')
                    c.drawCentredString(cx, cy-1.5, shift_ch)
        y = ry

    # ════════════════════════════════════════
    # NIGHT-SHIFT BALANCE SUMMARY BAR
    # ════════════════════════════════════════
    y -= 0.3*cm
    bar_h   = 0.45*cm
    bar_y   = y - bar_h
    max_n   = max((night_hrs[e]//(12 if shift_mode == '2x12' else 8) for e in avail), default=1)
    bar_tw  = TW * 0.55
    bar_x   = MX

    c.setFillColor(SLATE); c.setFont(FONT_B, 7.5)
    c.drawString(MX, y-0.1*cm, H('איזון משמרות לילה:'))
    bar_y -= 0.12*cm

    emp_col_w = bar_tw / max(len(avail), 1)
    for ei, emp in enumerate(sorted(avail.keys())):
        n = night_hrs.get(emp, 0) // (12 if shift_mode == '2x12' else 8)
        ex = bar_x + ei * emp_col_w
        # bar background
        c.setFillColor(colors.HexColor('#ebf8ff'))
        c.rect(ex, bar_y, emp_col_w*0.9, bar_h, fill=1, stroke=1)
        # filled portion
        if max_n > 0:
            fill_w = emp_col_w * 0.9 * (n / max_n)
            c.setFillColor(SH_MED['לילה'])
            c.rect(ex, bar_y, fill_w, bar_h, fill=1, stroke=0)
        c.setFillColor(SLATE); c.setFont(FONT, 6)
        label = H(emp.split()[0]) if ' ' in emp else H(emp)  # first name only
        c.drawCentredString(ex + emp_col_w*0.45, bar_y + bar_h*0.3, f'{label} ({n})')

    # ════════════════════════════════════════
    # LEGEND + FOOTER
    # ════════════════════════════════════════
    lx = MX
    ly = MY + 0.25*cm
    for sh in SHIFTS_LOCAL:
        c.setFillColor(SH_MED[sh])
        c.circle(lx+0.12*cm, ly+0.08*cm, 0.09*cm, fill=1, stroke=0)
        c.setFillColor(GRAY_TXT); c.setFont(FONT, 7)
        shift_ch = {'בוקר':'ב','צהריים':'צ','לילה':'ל'}.get(sh, '?')
        c.drawString(lx+0.27*cm, ly+0.03*cm, H(f'{shift_ch} = {sh}  {SHIFT_HRS_LOCAL[sh]}'))
        lx += 4.0*cm

    c.setFillColor(GRAY_TXT); c.setFont(FONT, 6.5)
    c.drawString(MX, MY*0.25,
        H('* עיגול עם מסגרת = שיבוץ אוטומטי  |  אדום = אין כיסוי  |  '
          'מצב חריג: 2 משמרות 12ש  06:00-18:00 / 18:00-06:00'))

    c.save()


# ══════════════════════════════════════════════
#  ▶  הכנס כאן את נתוני השבוע
# ══════════════════════════════════════════════

WEEK = '30.03.2026'   # תאריך יום ראשון של השבוע  (DD.MM.YYYY)

# הודעות זמינות מהעובדים (הדבק כאן את הטקסט מהווטסאפ)
MESSAGES = """
דביר יונה: א-ב,צ, ב-ב,ל, ג-ב,צ,ל, ד-ב,צ
שרה כהן: א-צ,ל, ב-ב,צ, ג-ל, ה-ב,צ, ו-ב
יוסי לוי: ב-צ,ל, ג-ב,צ, ד-ב,ל, ה-צ,ל, ש-ב
מיכל גולן: א-ב,ל, ג-ב,צ, ד-צ,ל, ו-ב,ל, ש-צ
רוני אביב: א-ב, ב-ב,צ, ג-ל, ד-ב,צ, ה-ב, ו-ב,ל
נועה שפיר: א-צ,ל, ב-ל, ד-ב,צ,ל, ה-צ, ש-ב,ל
"""

# העדפות עובדים (אופציונלי — השאר ריק אם אין)
PREFERENCES = """
דביר יונה: מעדיף לילה
"""

BASE_DIR = '/sessions/youthful-admiring-wright/mnt/\u05e2\u05d1\u05d5\u05d3\u05d4- \u05d0\u05d1\u05d8\u05d7\u05d4'
OUT_MGR  = f'{BASE_DIR}/\u05e1\u05d9\u05d3\u05d5\u05e8_\u05e2\u05d1\u05d5\u05d3\u05d4_\u05de\u05e0\u05d4\u05dc.pdf'
OUT_EMP  = f'{BASE_DIR}/\u05e1\u05d9\u05d3\u05d5\u05e8_\u05e2\u05d1\u05d5\u05d3\u05d4_\u05dc\u05e2\u05d5\u05d1\u05d3\u05d9\u05dd.pdf'

# ─────────────────────────────────────────────
if __name__ == '__main__':
    avail          = parse(MESSAGES)
    prefs          = parse_preferences(PREFERENCES)
    sched, hrs, nh = auto_schedule(avail, prefs, shift_mode='3x8')

    make_pdf(sched, avail, hrs, nh, prefs, WEEK, OUT_MGR, mode='manager', shift_mode='3x8')
    make_pdf(sched, avail, hrs, nh, prefs, WEEK, OUT_EMP, mode='employee', shift_mode='3x8')

    print(f'✓  PDF מנהל    →  {OUT_MGR}')
    print(f'✓  PDF עובדים  →  {OUT_EMP}\n')
    print(f'{"עובד":<22} {"שעות כלל":>10} {"משמרות לילה":>14}')
    print('─' * 50)
    for emp in sorted(avail.keys()):
        print(f'{emp:<22} {hrs[emp]:>8}h  {nh[emp]//8:>12} 🌙')
