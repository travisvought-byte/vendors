"""Read every source in the registry and write a business-only snapshot for each.

  data/rosters/<id>.json     a public roster as it was read (manual sources; committed)
  .pipeline-cache/raw/<id>   raw downloads (automatic sources; never committed)
  data/sources/<id>.json     normalized snapshot: business fields only, dated, with counts

Methods (registry "fetch.method"):
  csv | json        one file at fetch.url (for the owner's own directories: a raw GitHub address)
  html-list         an event page; fetch.selector is a CSS selector for one element per vendor
                    (optional fetch.name_selector inside it, fetch.hint_selector for a description)
  roster            a roster read by a person or assistant and saved under data/rosters/<id>.json
                    (used when a page needs a browser, or the list is in prose, a PDF or images)

Nothing here signs in, submits a form or sends a message. A 401/403/429, a login wall or a bot
check is recorded as "blocked" in the fetch log and is not retried another way (no mirrors,
caches or archives). A person looks at it.

Run: python -m pipeline.sources [--only ID ...] [--offline]
"""
import argparse
import csv
import hashlib
import io
import json
import os
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

from pipeline import importers
from pipeline.common import FETCH_LOG, RAW, ROSTERS, SNAPSHOTS, load_json, registry, save_json, today

USER_AGENT = 'VendorMapsPipeline/1.0 (public exhibitor and vendor lists; free directory for event organizers)'
BOT_MARKERS = ('captcha', 'cf-challenge', 'challenge-platform', 'are you a robot', 'verify you are human',
               'access denied', 'request rejected', 'incapsula', 'akamai bot', 'please log in', 'sign in to continue')


class Blocked(Exception):
    pass


class OfflineMiss(Exception):
    pass


def get(url, timeout=60, tries=3):
    last = None
    for attempt in range(tries):
        req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT, 'Accept': '*/*'})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read()
                ctype = resp.headers.get('Content-Type', '')
            if 'html' in ctype.lower() and any(m in body[:30000].decode('utf-8', 'ignore').lower() for m in BOT_MARKERS):
                raise Blocked(f'bot check or sign-in page at {url}')
            return body
        except urllib.error.HTTPError as err:
            if err.code in (401, 403, 407, 429, 451):
                raise Blocked(f'HTTP {err.code} at {url}') from err
            last = err
        except (urllib.error.URLError, TimeoutError, ConnectionError) as err:
            last = err
        time.sleep(3 * (attempt + 1))
    raise RuntimeError(f'{url}: {last}')


def local_copy(spec):
    """An offline stand-in for a raw GitHub file: $<ENV>/<path> when that checkout is present."""
    env, rel = spec.get('local_env'), spec.get('local_path')
    if env and rel and os.environ.get(env):
        path = os.path.join(os.environ[env], rel)
        if os.path.exists(path):
            return open(path, 'rb').read()
    return None


def read_raw(src, offline):
    spec = src['fetch']
    method = spec['method']
    if method == 'roster':
        roster = load_json(ROSTERS / f'{src["id"]}.json')
        if roster is None:
            raise RuntimeError(f'no roster file data/rosters/{src["id"]}.json')
        return json.dumps(roster).encode(), roster.get('retrieved') or src.get('retrieved'), 'roster file'
    body = local_copy(spec)
    where = 'local checkout'
    if body is None:
        cached = RAW / src['id']
        if offline:
            if not cached.exists():
                raise OfflineMiss()
            return cached.read_bytes(), None, 'cache'
        body = get(spec['url'])
        where = spec['url']
    RAW.mkdir(parents=True, exist_ok=True)
    (RAW / src['id']).write_bytes(body)
    return body, today(), where


def parse(src, body):
    method = src['fetch']['method']
    if method == 'csv':
        return list(csv.DictReader(io.StringIO(body.decode('utf-8-sig'))))
    if method in ('json', 'roster'):
        return json.loads(body)
    if method == 'html-list':
        from bs4 import BeautifulSoup
        spec = src['fetch']
        soup = BeautifulSoup(body, 'html.parser')
        rows = []
        for el in soup.select(spec['selector']):
            name_el = el.select_one(spec['name_selector']) if spec.get('name_selector') else el
            hint_el = el.select_one(spec['hint_selector']) if spec.get('hint_selector') else None
            link = el.select_one('a[href^="http"]')
            rows.append({'name': name_el.get_text(' ', strip=True) if name_el else None,
                         'category_hint': hint_el.get_text(' ', strip=True) if hint_el else None,
                         'website': link['href'] if link and spec.get('links_are_vendor_sites') else None})
        return {'vendors': rows}
    raise ValueError(f'unknown method {method}')


def run_source(src, offline=False):
    body, retrieved, where = read_raw(src, offline)
    data = parse(src, body)
    importer = getattr(importers, src.get('importer', 'roster'))
    vendors, counts = importer(src, data)
    event = src.get('event')
    if event:
        for v in vendors:
            v.setdefault('events', [event])
    snap = {
        'source': src['id'], 'title': src['title'], 'publisher': src.get('publisher'),
        'landing_url': src.get('landing_url'), 'evidence_level': src['evidence_level'],
        'kept_rule': src.get('kept_rule'), 'retrieved_on': retrieved or src.get('retrieved'),
        'read_from': where if where != 'local checkout' else src['fetch'].get('url'),
        'sha256': hashlib.sha256(body).hexdigest(), 'counts': counts, 'vendors': vendors,
    }
    save_json(SNAPSHOTS / f'{src["id"]}.json', snap)
    return snap


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--only', nargs='*')
    ap.add_argument('--offline', action='store_true')
    args = ap.parse_args(argv)
    reg = registry()
    log = load_json(FETCH_LOG, {})
    for src in reg['sources']:
        if src['status'] not in ('active',):
            continue
        if args.only and src['id'] not in args.only and not any(src['id'].startswith(o) for o in args.only):
            continue
        stamp = datetime.now(timezone.utc).isoformat(timespec='seconds')
        try:
            snap = run_source(src, args.offline)
            log[src['id']] = {'ok': True, 'at': stamp, 'kept': snap['counts']['kept']}
            print(f'{src["id"]}: kept {snap["counts"]["kept"]} of {snap["counts"]["read"]}')
        except Blocked as err:
            log[src['id']] = {'ok': False, 'blocked': True, 'at': stamp, 'reason': str(err)}
            print(f'{src["id"]}: BLOCKED ({err}); left for a person to look at')
        except OfflineMiss:
            print(f'{src["id"]}: offline, nothing cached; keeping the committed snapshot')
        except Exception as err:  # keep going; the log says what failed
            log[src['id']] = {'ok': False, 'at': stamp, 'reason': str(err)[:300]}
            print(f'{src["id"]}: FAILED ({err})')
    save_json(FETCH_LOG, log)


if __name__ == '__main__':
    main()
