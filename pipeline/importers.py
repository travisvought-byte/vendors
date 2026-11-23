"""Turn each source's rows into vendor rows with business fields only.

Each importer returns (vendors, counts). A vendor row may carry only the fields in
common.FIELDS plus: source_category, evidence_level (when it differs from the source's),
events (list of event dicts). Contact people, emails and phone numbers are never copied.
"""
import re

from pipeline.common import (EMAIL_RE, PHONE_RE, clean, looks_like_personal_name, scrub, state_code,
                             website)

OCHBS_2026 = {'name': 'Ohio Cannabis Health & Business Summit (OCHBS)', 'year': 2026, 'city': 'Columbus', 'state': 'OH'}


def _counts(read, vendors, **dropped):
    return {'read': read, 'kept': len(vendors), 'dropped': {k: v for k, v in dropped.items() if v}}


def _vendor(name, **fields):
    v = {'name': scrub(name)}
    for k, val in fields.items():
        if k in ('events',):
            if val:
                v[k] = val
            continue
        val = website(val) if k == 'website' else scrub(val)
        if val:
            v[k] = val
    return v


def ohio_cannabis_directory(src, rows):
    """The Ohio Cannabis Ecosystem Directory CSV (owner's own, source-verified)."""
    vendors, out_of_scope, not_business = [], 0, 0
    for r in rows:
        cat = clean(r.get('Category')) or ''
        if cat.lower().startswith('out of scope'):
            out_of_scope += 1
            continue
        if clean(r.get('Type')) in ('Individual', 'Political Party'):
            not_business += 1
            continue
        area = clean(r.get('Service Area')) or ''
        state = region = served = None
        m = re.match(r'Ohio regional:\s*(.*)', area)
        if m:
            state, region = 'OH', m.group(1)
            region = None if re.fullmatch(r'Ohio( \(extent unspecified\)| market.*)?', region or '') else region
            served = f'{region}, Ohio' if region else 'Ohio statewide'
        elif area == 'Ohio statewide':
            state, served = 'OH', 'Ohio statewide'
        elif area.startswith('Nationwide'):
            served = 'Nationwide'
        elif area.startswith('Multistate'):
            served = 'Multistate'
        seed = (r.get('Seed Source') or '') + ' ' + (r.get('Source(s)') or '')
        at_ochbs = 'ochbs' in seed.lower()
        direct = 'OCHBS 2026 direct contact' in (r.get('Seed Source') or '')
        v = _vendor(r.get('Organization / Business Name'), state=state, region=region, served_area=served,
                    website=r.get('Website'), category_hint=r.get('Capabilities / Keywords'),
                    source_category=cat, events=[OCHBS_2026] if at_ochbs else None)
        if direct:
            v['evidence_level'] = 'trade-show-contact'
        v['source_record'] = clean(r.get('Record ID'))
        vendors.append(v)
    return vendors, _counts(len(rows), vendors, out_of_scope=out_of_scope, not_a_business=not_business)


ADDRESS_RE = re.compile(r',\s*([A-Za-z .]+),\s*(PA|Pennsylvania)\s*\d{5}')


def pennsylvania_companies(src, rows):
    """The cannabis directory's Pennsylvania companies CSV. Contact column is never read."""
    vendors = []
    for r in rows:
        conn = clean(r.get('PA connection')) or ''
        m = ADDRESS_RE.search(conn) or ADDRESS_RE.search(clean(r.get('What they provide')) or '')
        city = m.group(1).strip().split(',')[-1].strip() if m else None
        sites = (clean(r.get('Public business facts')) or '').split('|')
        v = _vendor(r.get('Organization'), city=city, state='PA', source_category=r.get('Directory category'),
                    category_hint=r.get('Directory category'), website=sites[0].strip() if sites and sites[0].strip() else None,
                    served_area='Pennsylvania')
        v['source_record'] = clean(r.get('Organization ID'))
        vendors.append(v)
    return vendors, _counts(len(rows), vendors)


HQ_RE = re.compile(r'HQ ([A-Za-z .\'-]+), ([A-Z]{2}), (US|USA|United States)')
MJBIZ_2026 = {'name': 'MJBizCon', 'year': 2026, 'city': 'Las Vegas', 'state': 'NV'}


def mjbizcon_candidates(src, data):
    """MJBizCon 2026 exhibitors whose official profile lists Ohio (cannabis directory research file)."""
    vendors = []
    for c in data['candidates']:
        notes = c.get('notes') or ''
        hq = HQ_RE.search(notes)
        signal = c.get('ohio_signal') or ''
        n_states = len(re.findall(r'\b[A-Z][a-z]+(?: [A-Z][a-z]+)?\b', signal.split(':', 1)[-1])) if ':' in signal else 0
        served = 'all 50 states' if 'all 50' in signal else ('multistate' if n_states >= 4 else None)
        v = _vendor(c['name'], city=hq.group(1) if hq else None, state=hq.group(2) if hq else None,
                    website=c.get('website'), category_hint=c.get('capabilities'),
                    source_category=c.get('proposed_category'), served_area=served, events=[MJBIZ_2026])
        vendors.append(v)
    return vendors, _counts(len(data['candidates']), vendors)


def roster(src, data):
    """A public event roster saved under data/rosters/<id>.json (or parsed from an html-list page).

    Roster file shape: {"event": {...}, "roster_kind": ..., "vendors": [{"name", "city", "state",
    "website", "category_hint"}], "personal_name_only_count": n, "retrieved": "YYYY-MM-DD"}
    """
    event = data.get('event') or src.get('event')
    kind = data.get('roster_kind') or src.get('roster_kind')
    personal = int(data.get('personal_name_only_count') or 0)
    contact_like, dupes, seen = 0, 0, set()
    vendors = []
    for row in data.get('vendors', []):
        raw = clean(row.get('name'))
        if not raw:
            continue
        if EMAIL_RE.search(raw) or PHONE_RE.fullmatch(raw.strip()):
            contact_like += 1
            continue
        if looks_like_personal_name(raw):
            personal += 1
            continue
        key = raw.lower()
        if key in seen:
            dupes += 1
            continue
        seen.add(key)
        v = _vendor(raw, city=row.get('city'), state=state_code(row.get('state')), website=row.get('website'),
                    category_hint=row.get('category_hint'), events=[event] if event else None)
        if kind:
            v['roster_kind'] = kind
        if (event or {}).get('type'):
            v['event_type'] = event['type']
        vendors.append(v)
    counts = _counts(len(data.get('vendors', [])), vendors, contact_like=contact_like, duplicate_on_roster=dupes)
    counts['personal_name_only'] = personal
    return vendors, counts
