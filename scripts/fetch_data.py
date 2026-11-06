#!/usr/bin/env python3
"""
Fetch official policy-rate data and the economic calendar for the Markets Board.

Writes  <out>/policy.json  and  <out>/calendar.json.
Runs on GitHub Actions every 30 min (see .github/workflows/pages.yml); stdlib only.

Sources
  RBA  cash rate, last decision, vote   https://www.rba.gov.au/statistics/cash-rate/  (+ linked statement)
  RBA  next meeting                     https://www.rba.gov.au/schedules-events/calendar/
  Fed  target range, EFFR               https://markets.newyorkfed.org/api/rates/unsecured/effr/last/1.json
  Fed  meeting dates                    https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm
  Fed  last decision + vote             https://www.federalreserve.gov/newsevents/pressreleases/monetaryYYYYMMDDa.htm
  Calendar (forecast / previous)        https://nfs.faireconomy.media/ff_calendar_{thisweek,nextweek}.json

If a source fails, the previous good value (from the last deployment, --prev) is kept
with its original timestamp, so the board shows it as stale rather than inventing anything.
"""
import argparse, datetime as dt, html, json, re, sys, urllib.request
from zoneinfo import ZoneInfo

UTC = dt.timezone.utc
SYD = ZoneInfo('Australia/Sydney')
NY = ZoneInfo('America/New_York')
UA = {'User-Agent': 'Mozilla/5.0 (compatible; market-tv-board/1.0; +https://github.com/nur0078/market-tv)'}
MONTHS = {m: i for i, m in enumerate(['january','february','march','april','may','june','july','august',
                                       'september','october','november','december'], 1)}
WORDS = {'one':1,'two':2,'three':3,'four':4,'five':5,'six':6,'seven':7,'eight':8,'nine':9,'ten':10,
         'eleven':11,'twelve':12}

def now(): return dt.datetime.now(UTC)
def iso(d): return d.astimezone(UTC).strftime('%Y-%m-%dT%H:%M:%SZ')
def log(*a): print(*a, file=sys.stderr)

def get(url, timeout=30):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode('utf-8', 'replace')

def text_of(h):
    h = re.sub(r'(?is)<(script|style|noscript)[^>]*>.*?</\1>', ' ', h)
    h = re.sub(r'(?s)<[^>]+>', ' ', h)
    return re.sub(r'\s+', ' ', html.unescape(h)).strip()

def month_num(s): return MONTHS.get(s.lower()) or MONTHS.get(next((m for m in MONTHS if m.startswith(s.lower()[:3])), ''), None)

def parse_dmy(s):
    m = re.match(r'(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})', s.strip())
    if not m: return None
    mo = month_num(m.group(2))
    return dt.date(int(m.group(3)), mo, int(m.group(1))) if mo else None

def frac(s):
    """'3-3/4' -> 3.75, '4' -> 4.0, '4.85' -> 4.85"""
    s = s.strip()
    m = re.match(r'^(\d+)(?:-(\d+)/(\d+))?$', s)
    if m:
        v = float(m.group(1))
        if m.group(2): v += int(m.group(2)) / int(m.group(3))
        return v
    return float(s)

# ─────────────────────────────── RBA ───────────────────────────────
def rba_cash_rate(raw):
    """Latest row of the cash-rate table: effective date, change, rate, statement link."""
    for row in re.findall(r'(?is)<tr[^>]*>(.*?)</tr>', raw):
        cells = [text_of(c) for c in re.findall(r'(?is)<t[hd][^>]*>(.*?)</t[hd]>', row)]
        if len(cells) < 3: continue
        d = parse_dmy(cells[0])
        if not d: continue
        try:
            chg = float(cells[1].replace('−', '-').replace('–', '-').replace('+', ''))
            rate = float(cells[2])
        except ValueError:
            continue
        link = re.search(r'href="([^"]*media-releases[^"]*)"', row)
        url = link.group(1) if link else None
        if url and url.startswith('/'): url = 'https://www.rba.gov.au' + url
        return {'effective': d.isoformat(), 'changeBp': round(chg * 100), 'rate': rate, 'statementUrl': url}
    raise ValueError('no rows parsed from RBA cash-rate table')

def rba_vote(txt):
    if re.search(r'\bunanimous', txt, re.I): return 'Unanimous'
    counts = [WORDS.get(w.lower()) or (int(w) if w.isdigit() else None)
              for w in re.findall(r'\b(\w+) members? voted to', txt, re.I)]
    counts = sorted([c for c in counts if c], reverse=True)
    return '–'.join(map(str, counts)) if len(counts) >= 2 else None

def rba_meetings(txt):
    """'Monetary Policy Board Meeting … 2 November 2026–3 November 2026' → decision dates (day two)."""
    out = set()
    for m in re.finditer(r'Monetary Policy Board Meeting.{0,200}?(\d{1,2} [A-Z][a-z]+ \d{4})\s*[–-]\s*(\d{1,2} [A-Z][a-z]+ \d{4})', txt):
        d = parse_dmy(m.group(2))
        if d: out.add(d)
    return sorted(out)

def fetch_rba():
    raw = get('https://www.rba.gov.au/statistics/cash-rate/')
    cr = rba_cash_rate(raw)
    res = {'rate': cr['rate'], 'changeBp': cr['changeBp'], 'effective': cr['effective'], 'statementUrl': cr['statementUrl']}
    # decision date = day before effective date (RBA announces day 2, effective next day)
    res['decisionDate'] = (dt.date.fromisoformat(cr['effective']) - dt.timedelta(days=1)).isoformat()
    res['action'] = 'Hold' if cr['changeBp'] == 0 else f"{cr['changeBp']:+d}bp"
    res['vote'] = None
    if cr['statementUrl']:
        try:
            res['vote'] = rba_vote(text_of(get(cr['statementUrl'])))
        except Exception as e:
            log('RBA statement fetch failed:', e)
    try:
        dates = rba_meetings(text_of(get('https://www.rba.gov.au/schedules-events/calendar/?topics=mone')))
        today = now().astimezone(SYD)
        nxt = next((d for d in dates if dt.datetime(d.year, d.month, d.day, 14, 30, tzinfo=SYD) > today), None)
        if nxt:
            res['next'] = iso(dt.datetime(nxt.year, nxt.month, nxt.day, 14, 30, tzinfo=SYD))
        res['meetings'] = [iso(dt.datetime(d.year, d.month, d.day, 14, 30, tzinfo=SYD)) for d in dates]
    except Exception as e:
        log('RBA calendar fetch failed:', e)
    return res

# ─────────────────────────────── FED ───────────────────────────────
def fomc_meetings(txt):
    out = []
    for ym in re.finditer(r'(\d{4}) FOMC Meetings(.*?)(?=\d{4} FOMC Meetings|$)', txt):
        year, body = int(ym.group(1)), ym.group(2)
        for m in re.finditer(r'\b(January|February|March|April|May|June|July|August|September|October|November|December|'
                             r'Jan/Feb|Feb/Mar|Mar/Apr|Apr/May|May/Jun|Jun/Jul|Jul/Aug|Aug/Sep|Sep/Oct|Oct/Nov|Nov/Dec)\s+(\d{1,2})-(\d{1,2})\b', body):
            mon = m.group(1).split('/')[-1]
            out.append(dt.date(year, month_num(mon), int(m.group(3))))
    return sorted(set(out))

def fed_statement(txt):
    res = {}
    m = re.search(r'decided to (maintain|raise|lower) the target range for the federal funds rate'
                  r'(?: by ([\d/]+) percentage point)?(?: to| at) ([\d\-/]+) to ([\d\-/]+) percent', txt)
    if m:
        verb, by = m.group(1), m.group(2)
        bp = 0
        if by:
            n, _, d = by.partition('/')
            bp = round(float(n) / float(d or 1) * 100)
        res['action'] = 'Hold' if verb == 'maintain' else f"{'+' if verb == 'raise' else '-'}{bp}bp"
        res['lower'], res['upper'] = frac(m.group(3)), frac(m.group(4))
    v = re.search(r'by an? (\d+)\s*[–-]\s*(\d+) vote', txt)
    if v: res['vote'] = 'Unanimous' if v.group(2) == '0' else f'{v.group(1)}–{v.group(2)}'
    return res

def fetch_fed():
    res = {}
    j = json.loads(get('https://markets.newyorkfed.org/api/rates/unsecured/effr/last/1.json'))
    r = j['refRates'][0]
    res.update(lower=float(r['targetRateFrom']), upper=float(r['targetRateTo']), effr=float(r['percentRate']), effrDate=r['effectiveDate'])
    try:
        dates = fomc_meetings(text_of(get('https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm')))
        t = now()
        at = lambda d: dt.datetime(d.year, d.month, d.day, 14, 0, tzinfo=NY)
        past = [d for d in dates if at(d) <= t]; fut = [d for d in dates if at(d) > t]
        res['meetings'] = [iso(at(d)) for d in dates]
        if fut: res['next'] = iso(at(fut[0]))
        if past:
            last = past[-1]
            res['decisionDate'] = last.isoformat()
            url = f'https://www.federalreserve.gov/newsevents/pressreleases/monetary{last:%Y%m%d}a.htm'
            try:
                st = fed_statement(text_of(get(url)))
                res['statementUrl'] = url
                res['action'], res['vote'] = st.get('action'), st.get('vote')
            except Exception as e:
                log('Fed statement fetch failed:', e)
    except Exception as e:
        log('FOMC calendar fetch failed:', e)
    return res

# ───────────────────────────── CALENDAR ─────────────────────────────
CCY = {'USD':'US','AUD':'AU','CNY':'CN','EUR':'EU','GBP':'UK','JPY':'JP','NZD':'NZ','CAD':'CA'}
KEEP_MEDIUM = {'USD','AUD','CNY'}
CODES = [  # (regex on title, short code)
    (r'Non-Farm', 'NFP'), (r'FOMC.*Minutes', 'FOMC MIN'), (r'Federal Funds Rate', 'FOMC'), (r'Cash Rate', 'RBA'),
    (r'Monetary Policy Meeting Minutes|RBA.*Minutes', 'RBA MIN'), (r'Core PCE', 'PCE'), (r'PCE', 'PCE'),
    (r'Core CPI|^CPI|Trimmed Mean|Inflation Rate', 'CPI'), (r'PPI', 'PPI'), (r'Employment Change|Unemployment', 'JOBS'),
    (r'GDP', 'GDP'), (r'Retail Sales', 'RETL'), (r'ISM Manufacturing', 'ISM MFG'), (r'ISM Services', 'ISM SVC'),
    (r'JOLTS', 'JOLTS'), (r'Wage Price', 'WPI'), (r'Main Refinancing|ECB', 'ECB'), (r'Official Bank Rate', 'BOE'),
    (r'BOJ Policy Rate', 'BOJ'), (r'Official Cash Rate', 'RBNZ'), (r'Trade Balance', 'TRADE'), (r'Consumer Sentiment|Confidence', 'CONF'),
    (r'Speaks', 'SPEAK'),
]
def code_for(country, title):
    for rx, c in CODES:
        if re.search(rx, title, re.I):
            return c if c in ('FOMC', 'FOMC MIN', 'RBA', 'RBA MIN', 'ECB', 'BOE', 'BOJ', 'RBNZ') else f'{country} {c}'[:8]
    initials = ''.join(w[0] for w in re.findall(r'[A-Za-z]+', title))[:4].upper()
    return f'{country} {initials}'[:8]

def fetch_calendar(prev_events):
    raw = []
    for wk in ('thisweek', 'nextweek'):
        try:
            raw += json.loads(get(f'https://nfs.faireconomy.media/ff_calendar_{wk}.json'))
        except Exception as e:
            log(f'FF {wk} failed:', e)
    if not raw: raise ValueError('calendar feed empty')
    groups, seen = {}, set()
    for e in raw:
        k = (e.get('title'), e.get('date'), e.get('country'))
        if k in seen: continue
        seen.add(k)
        ccy, imp = e.get('country'), (e.get('impact') or '')
        if ccy not in CCY or imp not in ('High', 'Medium'): continue
        if imp == 'Medium' and ccy not in KEEP_MEDIUM: continue
        try: t = dt.datetime.fromisoformat(e['date']).astimezone(UTC)
        except Exception: continue
        groups.setdefault((iso(t), ccy), []).append(e)
    events = []
    for (t, ccy), items in groups.items():
        def rank(x):
            t = x.get('title', '')
            pri = next((i for i, (rx, _) in enumerate(CODES) if re.search(rx, t, re.I)), len(CODES))
            return (x.get('impact') != 'High', pri, len(t))
        items.sort(key=rank)
        top = items[0]; c = CCY[ccy]
        name = top['title']
        events.append({'t': t, 'c': c, 'code': code_for(c, top['title']), 'name': name,
                       'imp': 'high' if any(i.get('impact') == 'High' for i in items) else 'med',
                       'fc': top.get('forecast') or None, 'pv': top.get('previous') or None})
    # keep events from the previous run that are beyond this feed's window
    horizon = max(e['t'] for e in events) if events else iso(now())
    for e in prev_events or []:
        if e['t'] > horizon: events.append(e)
    return events

def add_policy_events(events, rba, fed):
    have = {(e['t'][:10], e['code']) for e in events}
    for t in (rba or {}).get('meetings', []):
        if t > iso(now()) and (t[:10], 'RBA') not in have:
            events.append({'t': t, 'c': 'AU', 'code': 'RBA', 'name': 'RBA cash rate decision', 'imp': 'high', 'fc': None, 'pv': None})
    for t in (fed or {}).get('meetings', []):
        d = dt.datetime.fromisoformat(t.replace('Z', '+00:00'))
        if t > iso(now()) and not any(e['code'] == 'FOMC' and abs((dt.datetime.fromisoformat(e['t'].replace('Z', '+00:00')) - d).total_seconds()) < 86400 for e in events):
            events.append({'t': t, 'c': 'US', 'code': 'FOMC', 'name': 'FOMC rate decision', 'imp': 'high', 'fc': None, 'pv': None})
    cutoff = iso(now() - dt.timedelta(hours=2))
    return sorted([e for e in events if e['t'] >= cutoff], key=lambda e: e['t'])

# ─────────────────────────────── MAIN ───────────────────────────────
def load_prev(base, name):
    if not base: return None
    try: return json.loads(get(f'{base.rstrip("/")}/{name}?ts={int(now().timestamp())}'))
    except Exception as e:
        log(f'no previous {name}:', e); return None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default='site/data')
    ap.add_argument('--prev', default=None, help='base URL of the currently deployed data/ folder')
    a = ap.parse_args()
    import os; os.makedirs(a.out, exist_ok=True)
    prev_pol = load_prev(a.prev, 'policy.json') or {}
    prev_cal = load_prev(a.prev, 'calendar.json') or {}

    policy = {'generated': iso(now())}
    for key, fn in (('rba', fetch_rba), ('fed', fetch_fed)):
        try:
            v = fn(); v['asOf'] = iso(now()); v['ok'] = True; policy[key] = v
        except Exception as e:
            log(f'{key} failed:', e)
            old = prev_pol.get(key)
            policy[key] = {**old, 'ok': False} if old else {'ok': False}
    try:
        events = fetch_calendar(prev_cal.get('events'))
        cal = {'asOf': iso(now()), 'ok': True}
    except Exception as e:
        log('calendar failed:', e)
        events = prev_cal.get('events') or []
        cal = {'asOf': prev_cal.get('asOf'), 'ok': False}
    cal['events'] = add_policy_events(events, policy.get('rba'), policy.get('fed'))
    cal['generated'] = iso(now())

    json.dump(policy, open(f'{a.out}/policy.json', 'w'), indent=1)
    json.dump(cal, open(f'{a.out}/calendar.json', 'w'), indent=1)
    print(json.dumps({'rba': policy['rba'].get('ok'), 'fed': policy['fed'].get('ok'), 'calendar': cal['ok'], 'events': len(cal['events'])}))

if __name__ == '__main__':
    main()
