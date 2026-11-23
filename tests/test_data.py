"""Checks that run before anything is published. python -m unittest discover -s tests"""
import json
import re
import unittest
from pathlib import Path

from pipeline import classify
from pipeline.common import (CATEGORIES, EMAIL_RE, EVIDENCE_LEVELS, FIELDS, ROOT, SCOPES, looks_like_personal_name,
                             norm_key, scrub)

PHONE = re.compile(r'\(?\b\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}\b')
VENDOR_KEYS = {'id', 'name', 'category', 'category_basis', 'scope', 'scope_basis', 'city', 'state', 'region',
               'location_basis', 'events', 'evidence', 'sources', 'checked', 'merged_rows'}
SNAPSHOT_EXTRA = {'source_category', 'evidence_level', 'events', 'source_record', 'roster_kind', 'event_type'}


def load(p):
    return json.loads(Path(p).read_text(encoding='utf-8'))


class Privacy(unittest.TestCase):
    def published_files(self):
        files = [ROOT / 'data/vendors.json', ROOT / 'data/coverage.json']
        files += sorted((ROOT / 'data/sources').glob('*.json')) + sorted((ROOT / 'data/rosters').glob('*.json'))
        return [f for f in files if f.exists()]

    def test_no_emails_or_phone_numbers_anywhere(self):
        for f in self.published_files():
            text = f.read_text(encoding='utf-8')
            self.assertIsNone(EMAIL_RE.search(text), f'email address in {f.name}')
            self.assertIsNone(PHONE.search(text), f'phone number in {f.name}')

    def test_snapshot_rows_carry_business_fields_only(self):
        for f in (ROOT / 'data/sources').glob('*.json'):
            if f.name.startswith('_'):
                continue
            for v in load(f)['vendors']:
                extra = set(v) - set(FIELDS) - SNAPSHOT_EXTRA
                self.assertFalse(extra, f'{f.name}: unexpected fields {extra}')

    def test_no_personal_names_published(self):
        for v in load(ROOT / 'data/vendors.json')['vendors']:
            self.assertFalse(looks_like_personal_name(v['name']), f'personal name published: {v["name"]}')

    def test_scrub(self):
        self.assertEqual(scrub('Acme Farm, info@acme.com, 614-555-0100'), 'Acme Farm')
        self.assertTrue(looks_like_personal_name('Jane Q. Smith'))
        self.assertFalse(looks_like_personal_name('Buckeye Kettle Corn'))


class Shape(unittest.TestCase):
    def test_vendors(self):
        d = load(ROOT / 'data/vendors.json')
        ids = set()
        for v in d['vendors']:
            self.assertLessEqual(set(v), VENDOR_KEYS, v['name'])
            self.assertIn(v['category'], CATEGORIES)
            self.assertIn(v['scope'], SCOPES)
            self.assertTrue(v['sources'])
            for e in v['evidence']:
                self.assertIn(e, EVIDENCE_LEVELS)
            self.assertNotIn(v['id'], ids)
            ids.add(v['id'])
        self.assertEqual(d['counts']['vendors'], len(d['vendors']))

    def test_registry(self):
        reg = load(ROOT / 'pipeline/registry.json')
        ids = [s['id'] for s in reg['sources']]
        self.assertEqual(len(ids), len(set(ids)), 'duplicate source id')
        for s in reg['sources']:
            self.assertIn(s['status'], ('active', 'queued', 'blocked'))
            self.assertIn(s['evidence_level'], EVIDENCE_LEVELS)
            if s['status'] == 'active' and s['fetch']['method'] == 'roster':
                self.assertTrue((ROOT / f'data/rosters/{s["id"]}.json').exists(), s['id'])

    def test_rules(self):
        self.assertEqual(norm_key('Acme Co., LLC'), norm_key('ACME'))
        self.assertEqual(classify.scope('Nationwide')[0], 'national')
        self.assertEqual(classify.scope(None, states={'OH', 'PA'})[0], 'regional')
        self.assertEqual(classify.scope(None, states={'OH'}, cities=['Columbus, OH', 'Dayton, OH'])[0], 'state')
        self.assertEqual(classify.category(hint='Wood-fired pizza')[0], 'food-beverage')
        self.assertEqual(classify.category(source_category='Insurance')[0], 'professional-services')


if __name__ == '__main__':
    unittest.main()
