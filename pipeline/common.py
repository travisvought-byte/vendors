"""Shared paths, the vendor row shape, categories, scope rules and text helpers.

Everything Vendor Maps publishes passes through here. The privacy rule lives in two places:
FIELDS (the only fields a normalized vendor row may carry) and scrub() (which refuses any value
that looks like an email address or phone number).
"""
import json
import re
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / 'pipeline/registry.json'
CACHE = ROOT / '.pipeline-cache'                 # raw downloads; never committed
RAW = CACHE / 'raw'
SNAPSHOTS = ROOT / 'data/sources'                # normalized, business-only snapshots; committed
ROSTERS = ROOT / 'data/rosters'                  # rosters read by a person or assistant; committed
FETCH_LOG = SNAPSHOTS / '_fetch-log.json'        # status only, no row data
VENDORS = ROOT / 'data/vendors.json'             # the merged public list
COVERAGE_JSON = ROOT / 'data/coverage.json'
COVERAGE_MD = ROOT / 'docs/COVERAGE.md'

# The only fields a normalized vendor row may carry. Contact people, emails and phone
# numbers are never kept, even when a source publishes them.
FIELDS = ('name', 'city', 'state', 'country', 'region', 'website', 'category_hint', 'served_area')

CATEGORIES = {
    'food-beverage': 'Food & Beverage',
    'arts-crafts': 'Arts & Crafts',
    'retail-gifts': 'Retail, Gifts & Apparel',
    'health-wellness': 'Health, Beauty & Wellness',
    'cannabis-hemp': 'Cannabis, Hemp & CBD',
    'home-garden': 'Home, Garden & Building',
    'farm-agriculture': 'Farm & Agriculture',
    'professional-services': 'Professional & Financial Services',
    'technology': 'Technology',
    'marketing-media': 'Marketing, Media & Printing',
    'packaging-supplies': 'Packaging & Supplies',
    'security-logistics': 'Security & Logistics',
    'event-services': 'Event Services & Rentals',
    'entertainment': 'Entertainment & Activities',
    'outdoors-auto': 'Outdoors, Auto & Recreation',
    'nonprofit-community': 'Nonprofit, Community & Government',
    'other': 'Other',
}

SCOPES = {
    'local': 'Seen in one city or metro area.',
    'state': 'Serves or appears across one state.',
    'regional': 'Appears in two to three neighboring states.',
    'national': 'Serves the whole country, or appears in four or more states.',
}

EVIDENCE_LEVELS = {
    'event-roster': "Named on the event's own published exhibitor, vendor or sponsor list.",
    'trade-show-contact': 'Met in person at a trade show and shared their details to be listed (owner-collected).',
    'directory-verified': 'Listed in one of the owner\'s source-verified directories, which cite the business\'s own pages.',
    'event-profile': "Has an exhibitor profile on the event's official site.",
    'business-own-page': "Stated on the business's own website; no event appearance recorded yet.",
}

US_STATES = {
    'AL': 'Alabama', 'AK': 'Alaska', 'AZ': 'Arizona', 'AR': 'Arkansas', 'CA': 'California', 'CO': 'Colorado',
    'CT': 'Connecticut', 'DE': 'Delaware', 'DC': 'District of Columbia', 'FL': 'Florida', 'GA': 'Georgia',
    'HI': 'Hawaii', 'ID': 'Idaho', 'IL': 'Illinois', 'IN': 'Indiana', 'IA': 'Iowa', 'KS': 'Kansas',
    'KY': 'Kentucky', 'LA': 'Louisiana', 'ME': 'Maine', 'MD': 'Maryland', 'MA': 'Massachusetts',
    'MI': 'Michigan', 'MN': 'Minnesota', 'MS': 'Mississippi', 'MO': 'Missouri', 'MT': 'Montana',
    'NE': 'Nebraska', 'NV': 'Nevada', 'NH': 'New Hampshire', 'NJ': 'New Jersey', 'NM': 'New Mexico',
    'NY': 'New York', 'NC': 'North Carolina', 'ND': 'North Dakota', 'OH': 'Ohio', 'OK': 'Oklahoma',
    'OR': 'Oregon', 'PA': 'Pennsylvania', 'RI': 'Rhode Island', 'SC': 'South Carolina', 'SD': 'South Dakota',
    'TN': 'Tennessee', 'TX': 'Texas', 'UT': 'Utah', 'VT': 'Vermont', 'VA': 'Virginia', 'WA': 'Washington',
    'WV': 'West Virginia', 'WI': 'Wisconsin', 'WY': 'Wyoming', 'PR': 'Puerto Rico',
}
STATE_BY_NAME = {v.lower(): k for k, v in US_STATES.items()}

EMAIL_RE = re.compile(r'[\w.+-]+@[\w-]+\.[\w.-]+')
PHONE_RE = re.compile(r'(\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}')


def load_json(path, default=None):
    path = Path(path)
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding='utf-8'))


def save_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False) + '\n', encoding='utf-8')


def registry():
    return load_json(REGISTRY)


def today():
    return date.today().isoformat()


def plus_days(iso, days):
    return (date.fromisoformat(iso) + timedelta(days=days)).isoformat()


def clean(value):
    """Collapse whitespace; treat blanks and placeholder dashes as missing."""
    if value is None:
        return None
    if isinstance(value, float):
        if value != value:
            return None
        if value.is_integer():
            value = int(value)
    text = ' '.join(str(value).split())
    if text.lower() in ('', 'nan', 'none', 'null', 'n/a', 'na', '-', '--', 'tbd', 'tba'):
        return None
    return text


def scrub(text):
    """Return text with any email address or phone number removed. Never store contacts."""
    text = clean(text)
    if not text:
        return None
    text = EMAIL_RE.sub('', text)
    text = PHONE_RE.sub('', text)
    return clean(text.strip(' ,;|/-'))


def state_code(text):
    text = clean(text)
    if not text:
        return None
    t = text.strip().rstrip('.')
    if t.upper() in US_STATES:
        return t.upper()
    return STATE_BY_NAME.get(t.lower())


def website(text):
    text = clean(text)
    if not text or ' ' in text or '.' not in text or '@' in text:
        return None
    if not re.match(r'https?://', text, re.I):
        text = 'https://' + text.lstrip('/')
    return text


def domain(url):
    if not url:
        return None
    host = urlparse(url).netloc.lower()
    host = host.split(':')[0]
    if host.startswith('www.'):
        host = host[4:]
    # social and marketplace pages are not a business's own domain
    if any(host.endswith(s) for s in ('facebook.com', 'instagram.com', 'etsy.com', 'linktr.ee', 'square.site',
                                         'google.com', 'goo.gl', 'tiktok.com', 'x.com', 'twitter.com', 'youtube.com')):
        return None
    return host or None


def norm_key(name):
    """A loose comparison key for business names: case, punctuation and legal suffixes folded."""
    if not name:
        return ''
    t = name.lower().replace('&', ' and ')
    t = re.sub(r"[’'`]", '', t)
    t = re.sub(r'\b(llc|l\.l\.c\.|inc|incorporated|ltd|co|corp|corporation|company|dba|the|pllc|llp|lp)\b\.?', ' ', t)
    return re.sub(r'[^a-z0-9]', '', t)


GIVEN_NAMES = frozenset(['aaron', 'abigail', 'adam', 'alan', 'albert', 'alex', 'alexander', 'alexis', 'alice', 'alison', 'allison', 'amanda', 'amber', 'amy', 'andrea', 'andrew', 'angela', 'ann', 'anna', 'anne', 'annie', 'anthony', 'april', 'arthur', 'ashley', 'austin', 'barbara', 'becky', 'ben', 'benjamin', 'beth', 'bethany', 'betty', 'beverly', 'bill', 'billy', 'bob', 'bobby', 'bonnie', 'brad', 'brandon', 'brenda', 'brian', 'brittany', 'brooke', 'bruce', 'bryan', 'caleb', 'carl', 'carla', 'carol', 'carolyn', 'carrie', 'catherine', 'chad', 'charles', 'charlotte', 'chelsea', 'cheryl', 'chris', 'christian', 'christina', 'christine', 'christopher', 'cindy', 'cody', 'connie', 'connor', 'corey', 'courtney', 'craig', 'crystal', 'curtis', 'cynthia', 'dale', 'dan', 'daniel', 'danielle', 'dave', 'david', 'dawn', 'deb', 'debbie', 'deborah', 'debra', 'denise', 'dennis', 'derek', 'diana', 'diane', 'donald', 'donna', 'doris', 'dorothy', 'douglas', 'dustin', 'dylan', 'earl', 'ed', 'edward', 'elijah', 'elizabeth', 'ellen', 'emily', 'emma', 'eric', 'erica', 'erin', 'ethan', 'eugene', 'evan', 'evelyn', 'frances', 'frank', 'fred', 'gabriel', 'gary', 'george', 'gerald', 'gina', 'ginger', 'glenn', 'gloria', 'grace', 'greg', 'gregory', 'hailey', 'haley', 'hannah', 'harold', 'heather', 'helen', 'henry', 'holly', 'hunter', 'ian', 'isaac', 'isabella', 'jack', 'jacob', 'jacqueline', 'james', 'jamie', 'jane', 'janet', 'janice', 'jared', 'jasmine', 'jason', 'jean', 'jeff', 'jeffrey', 'jen', 'jenna', 'jennifer', 'jenny', 'jeremy', 'jerry', 'jesse', 'jessica', 'jill', 'jim', 'jimmy', 'jo', 'joan', 'joann', 'joanne', 'joe', 'joel', 'john', 'jonathan', 'jordan', 'jose', 'joseph', 'joshua', 'joyce', 'juan', 'judith', 'judy', 'julie', 'justin', 'karen', 'kate', 'katherine', 'kathleen', 'kathryn', 'kathy', 'katie', 'kayla', 'keith', 'kelly', 'ken', 'kenneth', 'kevin', 'kim', 'kimberly', 'kristen', 'kristin', 'kyle', 'larry', 'laura', 'lauren', 'lawrence', 'leah', 'lee', 'leon', 'linda', 'lindsay', 'lindsey', 'lisa', 'liz', 'logan', 'lois', 'lori', 'louis', 'luke', 'madison', 'marcus', 'margaret', 'maria', 'marie', 'marilyn', 'mark', 'marsha', 'martha', 'martin', 'mary', 'mary-ellen', 'mason', 'matt', 'matthew', 'megan', 'meghan', 'melanie', 'melissa', 'michael', 'michelle', 'mike', 'misty', 'molly', 'monica', 'morgan', 'nancy', 'natalie', 'nathan', 'nicholas', 'nicole', 'noah', 'norma', 'olivia', 'owen', 'paige', 'pamela', 'pat', 'patricia', 'patrick', 'paul', 'paula', 'peggy', 'peter', 'phil', 'philip', 'rachel', 'ralph', 'randy', 'ray', 'raymond', 'rebecca', 'rhonda', 'richard', 'rick', 'robert', 'robin', 'roger', 'ron', 'ronald', 'roy', 'russell', 'ruth', 'ryan', 'sam', 'samantha', 'samuel', 'sandra', 'sara', 'sarah', 'scott', 'sean', 'seth', 'shane', 'sharon', 'shawn', 'sheila', 'shelly', 'sherry', 'shirley', 'sophia', 'stacey', 'stacy', 'stephanie', 'stephen', 'steve', 'steven', 'sue', 'susan', 'tammy', 'tara', 'taylor', 'teresa', 'terry', 'theresa', 'thomas', 'tiffany', 'tim', 'timothy', 'tina', 'todd', 'tom', 'tony', 'tonya', 'tracy', 'travis', 'trevor', 'troy', 'tyler', 'vanessa', 'veronica', 'victor', 'victoria', 'vincent', 'virginia', 'walter', 'wanda', 'wayne', 'wendy', 'whitney', 'william', 'willie', 'yvonne', 'zachary'])

PERSON_SUFFIX_RE = re.compile(r'\b(jr|sr|ii|iii|iv|md|phd|dds|esq)\.?$', re.I)
BUSINESS_WORDS = re.compile(
    r"\b(llc|inc|co|company|corp|studio|studios|shop|farm|farms|bakery|kitchen|foods?|truck|trucks|designs?|"
    r"art|arts|crafts?|creations?|boutique|candles?|soap|jewel\w*|pottery|works|workshop|goods|supply|services?|"
    r"group|market|brewing|brewery|winery|coffee|tea|bbq|grill|cafe|treats|sweets|cookies|cakes?|pizza|tacos?|"
    r"solutions|consulting|media|labs?|wellness|health|cannabis|hemp|cbd|dispensary|apothecary|collective|"
    r"house|home|garden|gardens|nursery|church|club|association|society|foundation|center|centre|"
    r"photography|press|printing|signs?|rentals?|events?|entertainment|productions?|pets?|dog|dogs|vintage|"
    r"leather|wood|woodworks|glass|metal|soaps|botanicals|bees|honey|apparel|clothing|threads|tees|"
    r"technolog\w*|tech|software|data|digital|university|college|institute|school|hospital|associates|partners|law|firm|agency|academy|capital|ventures|holdings|industries|enterprises|brands|labs|systems|insurance|bank|credit union|realty|construction|roofing|windows|solar|pools?|spa|salon|ohio|"
    r"[a-z]+'s)\b", re.I)


def looks_like_personal_name(name):
    """True for 'Jane Q. Smith'-style entries that name a person and no business.

    Rosters of artists often list makers by their own name. Vendor Maps publishes business names
    only, so these are counted, not listed.
    """
    if not name:
        return False
    if BUSINESS_WORDS.search(name) or any(ch.isdigit() for ch in name):
        return False
    parts = [p.strip() for p in re.split(r'\s+(?:and|&)\s+|\s*/\s*', name) if p.strip()]
    if len(parts) > 1:  # "Jane and John Smith", "Jane Smith & Ann Lee"
        return all(_person(p, allow_single=True) for p in parts)
    return _person(name)


def _person(text, allow_single=False):
    words = PERSON_SUFFIX_RE.sub('', text).replace(',', ' ').split()
    if not (1 if allow_single else 2) <= len(words) <= 4:
        return False
    if not all(re.fullmatch(r"[A-Z][a-zA-Z'\-]+|[A-Z]\.?", w) for w in words):
        return False
    return words[0].lower().strip('.') in GIVEN_NAMES
