"""Add rosters read from public pages to the registry and data/rosters/.

Used when a page can't be pulled automatically (it needs a browser, the list is in prose, a PDF
or pictures, or the runner can't reach the site). Someone reads the public page and writes a
collection file:

{"collected_on": "YYYY-MM-DD",
 "rosters": [{"event": "...", "event_year": 2026, "event_city": "...", "event_state": "OH",
              "event_type": "festival|fair|market|trade-show|consumer-expo|cannabis-expo|convention",
              "roster_kind": "exhibitors|vendors|sponsors|food-vendors|artists",
              "source_url": "https://...", "retrieved": "YYYY-MM-DD", "personal_name_only_count": 0,
              "vendors": [{"name": "...", "city": "...", "state": "..", "website": "...", "category_hint": "..."}]}],
 "blocked": [{"url": "...", "reason": "..."}],
 "leads": [{"event": "...", "url": "...", "why_not_read": "..."}]}

Business names only: never put a person's name, email or phone in a collection file.
Re-adding the same source_url replaces that roster (a re-read), it does not duplicate it.

Run: python -m pipeline.add_rosters path/to/collection.json [...]
"""
import re
import sys
from urllib.parse import urlparse

from pipeline.common import REGISTRY, ROSTERS, US_STATES, clean, load_json, save_json, scrub, state_code, website

CADENCE = {'festival': 180, 'fair': 180, 'market': 90, 'trade-show': 180, 'consumer-expo': 180,
           'cannabis-expo': 120, 'convention': 180}


def slug(text, n=48):
    return re.sub(r'-+', '-', re.sub(r'[^a-z0-9]+', '-', (text or '').lower())).strip('-')[:n].strip('-')


def roster_id(r):
    st = (state_code(r.get('event_state')) or 'us').lower()
    return f'us-{st}-{slug(r.get("event"))}-{r.get("event_year") or "undated"}'


def add(collection, reg):
    by_url = {s.get('landing_url'): s for s in reg['sources']}
    ids = {s['id'] for s in reg['sources']}
    added = updated = 0
    for r in collection.get('rosters', []):
        url = clean(r.get('source_url'))
        if not url or not r.get('vendors'):
            continue
        existing = by_url.get(url)
        sid = existing['id'] if existing else roster_id(r)
        while not existing and sid in ids:
            sid += '-b'
        event = {'name': clean(r.get('event')), 'year': r.get('event_year'), 'city': clean(r.get('event_city')),
                 'state': state_code(r.get('event_state')), 'type': clean(r.get('event_type'))}
        event = {k: v for k, v in event.items() if v}
        vendors = []
        for v in r['vendors']:
            row = {'name': scrub(v.get('name')), 'city': scrub(v.get('city')), 'state': state_code(v.get('state')) or scrub(v.get('state')),
                   'website': website(v.get('website')), 'category_hint': scrub(v.get('category_hint'))}
            vendors.append({k: val for k, val in row.items() if val})
        save_json(ROSTERS / f'{sid}.json', {
            'event': event, 'roster_kind': clean(r.get('roster_kind')), 'source_url': url,
            'retrieved': r.get('retrieved') or collection.get('collected_on'),
            'personal_name_only_count': int(r.get('personal_name_only_count') or 0), 'vendors': vendors,
        })
        entry = {
            'id': sid, 'jurisdiction': event.get('state'), 'title': f'{event.get("name")} {event.get("year") or ""} {clean(r.get("roster_kind")) or "vendors"}'.strip(),
            'publisher': urlparse(url).netloc, 'landing_url': url, 'event': event,
            'roster_kind': clean(r.get('roster_kind')), 'fetch': {'method': 'roster', 'url': url},
            'importer': 'roster', 'evidence_level': 'event-roster',
            'kept_rule': 'Every business on the published list; entries naming only a person are counted, not listed.',
            'cadence_days': CADENCE.get(event.get('type'), 180), 'status': 'active',
        }
        if existing:
            existing.update(entry)
            updated += 1
        else:
            reg['sources'].append(entry)
            ids.add(sid)
            by_url[url] = entry
            added += 1
    for kind, items in (('blocked', collection.get('blocked', [])), ('queued', collection.get('leads', []))):
        for b in items:
            url = clean(b.get('url'))
            if not url or url in by_url:
                continue
            host = urlparse(url).netloc
            sid = f'lead-{slug(b.get("event") or host)}'
            while sid in ids:
                sid += '-b'
            entry = {'id': sid, 'jurisdiction': None, 'title': clean(b.get('event')) or host, 'publisher': host,
                     'landing_url': url, 'fetch': {'method': 'roster', 'url': url}, 'importer': 'roster',
                     'evidence_level': 'event-roster', 'cadence_days': 180, 'status': kind,
                     'note': clean(b.get('reason') or b.get('why_not_read'))}
            reg['sources'].append(entry)
            ids.add(sid)
            by_url[url] = entry
    return added, updated


def main(paths):
    reg = load_json(REGISTRY)
    for p in paths:
        a, u = add(load_json(p), reg)
        print(f'{p}: {a} rosters added, {u} re-read')
    save_json(REGISTRY, reg)


if __name__ == '__main__':
    main(sys.argv[1:])
