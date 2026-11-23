"""Where Vendor Maps is thin, so the next mining batch goes where it matters.

Reads data/vendors.json, the snapshots and the registry (nothing is fetched) and writes:
  data/coverage.json   vendors by state and category, scope mix, source health, the queue
  docs/COVERAGE.md     the same, readable

Priority for the next batch: Ohio first, then its neighbors, then the rest. A state is thin
when it has few vendors or few categories covered; a source is due when its last read is
older than its cadence_days.

Run: python -m pipeline.coverage
"""
from collections import Counter, defaultdict
from datetime import date

from pipeline.common import (CATEGORIES, COVERAGE_JSON, COVERAGE_MD, FETCH_LOG, SCOPES, SNAPSHOTS, US_STATES, VENDORS,
                             load_json, registry, save_json, today)

HOME = 'OH'
NEIGHBORS = ('PA', 'MI', 'IN', 'KY', 'WV')
TARGET_PER_STATE = 500         # vendors per state before a state stops being "thin"
TARGET_CATEGORIES = 12         # categories with at least one vendor


def tier(code):
    return 0 if code == HOME else (1 if code in NEIGHBORS else 2)


def build():
    data = load_json(VENDORS, {'vendors': []})
    reg = registry()
    log = load_json(FETCH_LOG, {})
    ref = today()
    by_state = defaultdict(Counter)
    for v in data['vendors']:
        states = {v.get('state')} | {e.get('state') for e in v.get('events', [])}
        for s in {s for s in states if s} or {'unknown'}:
            by_state[s][v['category']] += 1
    states = []
    for code in list(US_STATES) + ['unknown']:
        cats = by_state.get(code, Counter())
        total = sum(cats.values())
        gaps = []
        if total < TARGET_PER_STATE and code != 'unknown':
            gaps.append(f'{total} of {TARGET_PER_STATE} vendors')
        missing = [CATEGORIES[c] for c in CATEGORIES if c != 'other' and not cats.get(c)]
        if code != 'unknown' and len(CATEGORIES) - 1 - len(missing) < TARGET_CATEGORIES:
            gaps.append(f'{len(missing)} categories empty')
        srcs = [s for s in reg['sources'] if s.get('jurisdiction') == code]
        states.append({
            'code': code, 'name': US_STATES.get(code, 'Location not stated'), 'vendors': total,
            'by_category': dict(sorted(cats.items())), 'empty_categories': missing if code != 'unknown' else [],
            'sources': {st: sum(1 for s in srcs if s['status'] == st) for st in ('active', 'queued', 'blocked') if any(s['status'] == st for s in srcs)},
            'gaps': gaps, 'priority': (tier(code), total) if code != 'unknown' else (9, 0),
        })
    states.sort(key=lambda r: r['priority'])
    for r in states:
        r['priority'] = list(r['priority'])

    sources, personal_total = [], 0
    for s in reg['sources']:
        snap = load_json(SNAPSHOTS / f'{s["id"]}.json')
        last = snap.get('retrieved_on') if snap else None
        due = None
        if last and s.get('cadence_days'):
            due = (date.fromisoformat(last).toordinal() + s['cadence_days'] - date.fromisoformat(ref).toordinal())
        personal = (snap or {}).get('counts', {}).get('personal_name_only', 0)
        personal_total += personal
        entry = log.get(s['id'], {})
        sources.append({
            'id': s['id'], 'title': s['title'], 'jurisdiction': s.get('jurisdiction'), 'status': s['status'],
            'method': s['fetch']['method'], 'last_read': last, 'days_until_due': due,
            'kept': (snap or {}).get('counts', {}).get('kept'), 'personal_name_only': personal,
            'last_run': 'blocked' if entry.get('blocked') else ('ok' if entry.get('ok') else ('failed' if entry else 'not run')),
            'note': s.get('note'),
        })
    scope_mix = Counter(v['scope'] for v in data['vendors'])
    cat_mix = Counter(v['category'] for v in data['vendors'])
    out = {
        'built_on': ref,
        'totals': {'vendors': len(data['vendors']), 'personal_name_only_counted_not_listed': personal_total,
                   'by_scope': {k: scope_mix.get(k, 0) for k in SCOPES},
                   'by_category': {CATEGORIES[k]: cat_mix.get(k, 0) for k in CATEGORIES}},
        'states': states,
        'sources': sources,
        'queue': [s for s in sources if s['status'] in ('queued', 'blocked') or (s['days_until_due'] is not None and s['days_until_due'] <= 0)],
    }
    save_json(COVERAGE_JSON, out)
    write_md(out)
    return out


def write_md(out):
    t = out['totals']
    lines = [
        '# Vendor Maps coverage', '',
        f'Built {out["built_on"]} by `python -m pipeline.coverage`. Do not edit by hand.', '',
        f'**{t["vendors"]} vendors.** By scope: ' + ', '.join(f'{k} {v}' for k, v in t['by_scope'].items()) + '. '
        f'Another {t["personal_name_only_counted_not_listed"]} roster entries named only a person and are counted, not listed.', '',
        '## By category', '', '| Category | Vendors |', '| --- | ---: |',
        *[f'| {k} | {v} |' for k, v in sorted(t['by_category'].items(), key=lambda x: -x[1])],
        '', '## Next states to mine', '',
        'Ohio first, then Pennsylvania, Michigan, Indiana, Kentucky and West Virginia, then the rest by size of gap.', '',
        '| State | Vendors | Sources (active/queued/blocked) | Gaps |', '| --- | ---: | --- | --- |',
    ]
    for s in out['states'][:25]:
        src = s['sources']
        lines.append(f'| {s["name"]} | {s["vendors"]} | {src.get("active", 0)}/{src.get("queued", 0)}/{src.get("blocked", 0)} | {"; ".join(s["gaps"]) or "none"} |')
    lines += ['', '## Sources', '', '| Source | Status | Last read | Kept | Due in (days) | Last run |', '| --- | --- | --- | ---: | ---: | --- |']
    for s in out['sources']:
        lines.append(f'| {s["title"]} (`{s["id"]}`) | {s["status"]} | {s["last_read"] or ""} | {s["kept"] if s["kept"] is not None else ""} | '
                     f'{s["days_until_due"] if s["days_until_due"] is not None else ""} | {s["last_run"]} |')
    lines += ['', '## Queue', '', 'Queued and blocked sources need a person (or an assistant reading the public page) before they can be added; '
              'due sources are re-read on the next run.', '']
    for s in out['queue']:
        lines.append(f'- **{s["title"]}** (`{s["id"]}`): {s["status"]}' + (f'. {s["note"]}' if s.get('note') else ''))
    COVERAGE_MD.parent.mkdir(parents=True, exist_ok=True)
    COVERAGE_MD.write_text('\n'.join(lines) + '\n', encoding='utf-8')


if __name__ == '__main__':
    o = build()
    print(o['totals'])
