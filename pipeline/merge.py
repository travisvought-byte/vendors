"""Merge every snapshot into one deduplicated vendor list: data/vendors.json.

Two rows are the same vendor when their business names match after folding case, punctuation
and legal suffixes ("Acme Co., LLC" = "ACME"), or they share a website domain. Each merged
vendor keeps every event it was seen at and every source that named it.

What is published per vendor: business name, category, scope (with the reason), city/state or
region, the events it was seen at, evidence levels, source ids and the date last checked.
Websites stay in the snapshots; contact goes through Vendor Maps (opt-in), so no email, phone
or contact person is stored anywhere.

Run: python -m pipeline.merge
"""
import hashlib
from collections import Counter

from pipeline import classify
from pipeline.common import (CATEGORIES, EVIDENCE_LEVELS, SCOPES, SNAPSHOTS, VENDORS, domain, load_json, norm_key,
                             registry, save_json, today)

SCOPE_RANK = {'local': 0, 'state': 1, 'regional': 2, 'national': 3}
EVIDENCE_ORDER = list(EVIDENCE_LEVELS)


class Groups:
    def __init__(self):
        self.parent = {}

    def find(self, x):
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[max(ra, rb)] = min(ra, rb)


def load_rows():
    reg = registry()
    rows = []
    for priority, src in enumerate(reg['sources']):
        if src['status'] != 'active':
            continue
        snap = load_json(SNAPSHOTS / f'{src["id"]}.json')
        if not snap:
            continue
        for v in snap['vendors']:
            if not v.get('name') or not norm_key(v['name']):
                continue
            rows.append({**v, '_source': src['id'], '_priority': priority, '_retrieved': snap.get('retrieved_on'),
                         '_evidence': v.get('evidence_level') or src['evidence_level']})
    return rows


def event_key(e):
    return (norm_key(e.get('name', '')), e.get('year'))


def build():
    rows = load_rows()
    groups = Groups()
    for i, r in enumerate(rows):
        groups.union(('row', i), ('name', norm_key(r['name'])))
        d = domain(r.get('website'))
        if d:
            groups.union(('row', i), ('site', d))
    members = {}
    for i, r in enumerate(rows):
        members.setdefault(groups.find(('row', i)), []).append(r)

    vendors = []
    for group in members.values():
        group.sort(key=lambda r: r['_priority'])
        name = group[0]['name']
        key = norm_key(name)
        events = {}
        for r in group:
            for e in r.get('events') or []:
                events.setdefault(event_key(e), e)
        events = sorted(events.values(), key=lambda e: (-(e.get('year') or 0), e.get('name', '')))
        home = next((r for r in group if r.get('state') or r.get('city')), None)
        states = {e.get('state') for e in events} | {r.get('state') for r in group}
        cities = {(e.get('city'), e.get('state')) for e in events if e.get('city')} | \
                 {(r.get('city'), r.get('state')) for r in group if r.get('city')}
        served = max((r.get('served_area') for r in group if r.get('served_area')),
                     key=lambda s: (bool(classify.NATIONAL_TEXT.search(s)), bool(classify.STATEWIDE_TEXT.search(s))),
                     default=None)
        scope, scope_basis = classify.scope(served, states=states,
                                            cities=[f'{c}, {s}' if s else c for c, s in cities],
                                            home_state=home.get('state') if home else None)
        cat, cat_basis = 'other', None
        for strict in (True, False):  # what the vendor is first; the kind of event only as a fallback
            for r in group:
                ev = None if strict else ((r.get('events') or [{}])[0].get('name'))
                cat, cat_basis = classify.category(r.get('source_category'), r.get('category_hint'), r.get('name'),
                                                   r.get('roster_kind'), r.get('event_type'), ev)
                if cat != 'other':
                    break
            if cat != 'other':
                break
        if home:
            city, state, region, loc_basis = home.get('city'), home.get('state'), home.get('region'), 'listed'
        elif events:
            e = events[0]
            city, state, region, loc_basis = e.get('city'), e.get('state'), None, 'seen at event'
        else:
            city = state = region = loc_basis = None
        evidence = sorted({r['_evidence'] for r in group}, key=EVIDENCE_ORDER.index)
        vendors.append({
            'id': 'v-' + hashlib.sha1(key.encode()).hexdigest()[:10],
            'name': name,
            'category': cat,
            'category_basis': cat_basis,
            'scope': scope,
            'scope_basis': scope_basis,
            'city': city, 'state': state, 'region': region, 'location_basis': loc_basis,
            'events': [{k: e[k] for k in ('name', 'year', 'city', 'state') if e.get(k)} for e in events],
            'evidence': evidence,
            'sources': sorted({r['_source'] for r in group}),
            'checked': max((r['_retrieved'] for r in group if r.get('_retrieved')), default=None),
            'merged_rows': len(group),
        })
    vendors.sort(key=lambda v: (v['state'] or 'ZZ', CATEGORIES[v['category']], v['name'].lower()))
    seen_ids = Counter(v['id'] for v in vendors)
    assert max(seen_ids.values(), default=1) == 1, 'vendor id collision'
    out = {
        'about': 'Vendor Maps: businesses seen on public event exhibitor and vendor lists, sorted by category, '
                 'scope and place. Business names only; contact is opt-in through Vendor Maps. We are not selling your data.',
        'built_on': today(),
        'categories': CATEGORIES,
        'scopes': SCOPES,
        'evidence_levels': EVIDENCE_LEVELS,
        'counts': {'vendors': len(vendors), 'rows_merged': len(rows), 'duplicates_merged': len(rows) - len(vendors)},
        'vendors': vendors,
    }
    save_json(VENDORS, out)
    return out


if __name__ == '__main__':
    o = build()
    print(o['counts'])
