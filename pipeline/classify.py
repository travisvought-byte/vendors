"""Put each vendor in one category and one scope (local, state, regional, national).

Category comes from, in order: a category the source assigns (mapped below), the roster's own
description of the vendor, the kind of roster (a food-truck list is food), then the name.

Scope is worked out from evidence, with the reason kept beside it:
  national  the source says it serves the whole country, or it was seen in 4+ states
  regional  seen at events in 2-3 states
  state     the source says it serves the state, or it was seen in 2+ cities in one state
  local     one city or metro area
"""
import re

from pipeline.common import CATEGORIES

# Category names used by the owner's other directories, mapped to Vendor Maps categories.
SOURCE_CATEGORY = {
    # Ohio Cannabis Ecosystem Directory
    'accounting & tax': 'professional-services', 'banking & financial services': 'professional-services',
    'consulting': 'professional-services', 'insurance': 'professional-services', 'legal & licensing': 'professional-services',
    'staffing & hr': 'professional-services', 'real estate / build-out': 'home-garden',
    'cultivator / processor / dispensary': 'cannabis-hemp', 'hemp / cbd products & ancillary': 'cannabis-hemp',
    'testing labs': 'cannabis-hemp', 'marketing & media': 'marketing-media', 'technology': 'technology',
    'packaging & labeling': 'packaging-supplies', 'security & cash logistics': 'security-logistics',
    'nonprofit & advocacy': 'nonprofit-community', 'events & expos': 'event-services',
    # Pennsylvania cannabis companies
    'operators & brands': 'cannabis-hemp', 'facility design & climate': 'home-garden',
    'education & research': 'nonprofit-community', 'packaging & labels': 'packaging-supplies', 'security': 'security-logistics',
    'testing laboratories': 'cannabis-hemp', 'industry organizations': 'nonprofit-community',
    'banking & payments': 'professional-services', 'cultivation supplies': 'cannabis-hemp',
    'extraction & processing equipment': 'cannabis-hemp', 'consulting & other services': 'professional-services',
    'accounting & finance': 'professional-services', 'software & technology': 'technology',
    'pest management / ipm': 'farm-agriculture', 'gases & consumables': 'packaging-supplies', 'hemp materials': 'cannabis-hemp',
    'commercial real estate': 'home-garden', 'energy & backup power': 'home-garden', 'laboratory equipment': 'cannabis-hemp',
    'payroll & hr': 'professional-services', 'electrical & mep engineering': 'home-garden',
    'logistics & distribution': 'security-logistics',
}

# Keyword rules for free text (roster descriptions, then names). First match wins, so the
# more specific categories come first.
KEYWORDS = [
    ('cannabis-hemp', r'cannabis|marijuana|hemp|\bcbd\b|\bthc\b|dispensar|delta[- ]?[89]|kratom|smoke shop|\bglass\b.*pipe|grow(ing)? supply|hydroponic'),
    ('food-beverage', r'food|truck|bbq|barbe?cue|grill|taco|pizza|burger|catering|caterer|bakery|bake|cookie|cake|cupcake|donut|dessert|sweet|candy|fudge|chocolate|ice cream|gelato|kettle ?corn|popcorn|lemonade|coffee|espresso|tea\b|brew|beer|wine|winery|distill|spirits|cider|mead|kombucha|juice|smoothie|jerky|sauce|salsa|spice|seasoning|honey|maple|jam|jelly|pickle|cheese|meat|sausage|deli|kitchen|eats|cuisine|noodle|ramen|dumpling|gyro|crepe|waffle|pretzel|funnel|snack|treat|vegan|soul food|sandwich|\\bpie\\b|syrup|nut ?butter|dough|bread|biscuit|brownie|granola|toffee|caramel|bagel|pasta|soup|chili|hot sauce|nuts\\b|wings|chicken|fries|lemon|coffee'),
    ('health-wellness', r'wellness|health|chiropract|massage|yoga|fitness|gym|medical|dental|vision|hearing|pharm|nutrition|vitamin|supplement|skin ?care|soap|lotion|cosmetic|beauty|salon|spa\b|hair|nail|essential oil|aromatherap|herbal|apothecary|balm|bath|candle'),
    ('arts-crafts', r'\bart\b|artist|arts\b|craft|pottery|ceramic|painting|painter|print(s|maker)|photograph|sculpt|jewel|bead|glass ?art|stained glass|woodwork|wood ?turn|fiber|knit|crochet|quilt|weav|leather|metal ?work|blacksmith|illustrat|handmade|hand-made|maker|studio|gallery|calligraph|origami|mosaic|creations|woven|forge|oddities|embroider|sew|stitch|resin|macrame|wreath|decoupage'),
    ('farm-agriculture', r'apiar|\\bbees?\\b|feed\\b|tractor|farm|orchard|produce|vegetable|fruit|egg|microgreen|nursery|greenhouse|plant(s)?\b|flower|florist|lavender|livestock|cattle|alpaca|goat|poultry|seed|agri|grange|4-h|ffa\b'),
    ('home-garden', r'home|house|garden|landscap|lawn|patio|deck|fence|roof|window|door|siding|gutter|kitchen remodel|bath remodel|remodel|construction|contractor|builder|cabinet|countertop|floor|carpet|furniture|mattress|hvac|heating|cooling|plumb|electric|solar|energy|generator|pool|hot tub|water treatment|basement|waterproof|pest|insulation|paint(ing)? contractor|real estate|realt|mortgage|interior|decor'),
    ('outdoors-auto', r'mower|equine|horse|saddle|tack\\b|farrier|\\brv\\b|camper|boat|marine|fishing|hunting|outdoor|trailer|atv|motorcycle|auto|car\b|truck accessor|tire|golf|bike|cycling|kayak|camping|archery|firearm|gun'),
    ('professional-services', r'insurance|bank|credit union|financial|finance|invest|account|tax|cpa|law\b|legal|attorney|lawyer|consult|staffing|recruit|payroll|hr\b|realty|estate planning|advisor|wealth'),
    ('technology', r'software|tech|app\b|digital|computer|\bit\b|cyber|data|internet|wireless|phone repair|electronics|pos\b|point of sale|web ?design'),
    ('marketing-media', r'marketing|media|radio|tv\b|television|news|magazine|publish|advertis|sign(s|age)?\b|print(ing|er)\b|promo|branding|seo\b|podcast'),
    ('packaging-supplies', r'packag|label|supply|supplies|wholesale|distribut|container|bottle'),
    ('security-logistics', r'security|guard|armored|logistic|shipping|courier|transport|delivery|moving|storage'),
    ('event-services', r'rental|tent|party|event|wedding|bridal|dj\b|disc jockey|photo ?booth|caterer|venue|banquet|linen|decorat|balloon|lighting|audio|sound|stage|planner|officiant|limo|invitation|bounce|inflatable|porta|restroom'),
    ('entertainment', r'entertain|music|band\b|magic|clown|face paint|petting zoo|pony|game|arcade|escape room|comic|toy|puzzle|book|author|anime|cosplay|collectib|card(s)? shop|vinyl|record'),
    ('retail-gifts', r'boutique|apparel|clothing|shirt|tee|hat|fashion|accessor|gift|vintage|antique|thrift|home decor|sock|scarf|purse|bag|wallet|shoe|boot|pet|dog|cat\b|kids|baby|retail|store|shop|merch|decal|sticker|keychain|ornament'),
    ('nonprofit-community', r'nonprofit|non-profit|foundation|charity|church|ministr|association|society|council|club\b|league|union\b|veteran|library|museum|school|university|college|academy|government|county|city of|state of|department|agency|chamber|rotary|lions|scouts|rescue|shelter|humane'),
]
KEYWORD_RES = [(cat, re.compile(rx, re.I)) for cat, rx in KEYWORDS]

EVENT_CATEGORY = [
    (re.compile(r'comic|anime|con\\b|ohayocon|small press', re.I), 'entertainment'),
    (re.compile(r'equine|horse', re.I), 'outdoors-auto'),
    (re.compile(r'home|garden|remodel|renovation|building', re.I), 'home-garden'),
    (re.compile(r'wedding|bridal', re.I), 'event-services'),
    (re.compile(r'farm show|farmers', re.I), 'farm-agriculture'),
    (re.compile(r'christmas|holiday|winter', re.I), 'retail-gifts'),
    (re.compile(r'art|craft|handmade', re.I), 'arts-crafts'),
    (re.compile(r'cannabis|hemp|canna', re.I), 'cannabis-hemp'),
    (re.compile(r'food|taste|truck', re.I), 'food-beverage'),
]

ROSTER_KIND_CATEGORY = {'food-vendors': 'food-beverage', 'food-trucks': 'food-beverage', 'artists': 'arts-crafts'}


def category(source_category=None, hint=None, name=None, roster_kind=None, event_type=None, event_name=None):
    """Return (category_key, basis)."""
    if source_category:
        key = SOURCE_CATEGORY.get(source_category.strip().lower())
        if key:
            return key, f'source category "{source_category}"'
    for text, basis in ((hint, 'roster description'), (name, 'business name')):
        if text:
            for cat, rx in KEYWORD_RES:
                if rx.search(text):
                    return cat, basis
    if roster_kind in ROSTER_KIND_CATEGORY:
        return ROSTER_KIND_CATEGORY[roster_kind], f'listed as {roster_kind.replace("-", " ")}'
    if event_type == 'cannabis-expo':
        return 'cannabis-hemp', 'exhibited at a cannabis expo'
    for rx, cat in EVENT_CATEGORY:
        if event_name and rx.search(event_name):
            return cat, f'kind of event ({event_name})'
    return 'other', 'no description to go on'


NATIONAL_TEXT = re.compile(r'nationwide|national|all 50 states|united states|u\.s\.?-wide|multistate|multi-state|across the (us|u\.s\.|country)', re.I)
STATEWIDE_TEXT = re.compile(r'statewide|state-wide', re.I)


def scope(served_area=None, states=(), cities=(), home_state=None):
    """Return (scope_key, basis) from what the sources say and where the vendor was seen."""
    states = sorted({s for s in states if s})
    cities = sorted({c for c in cities if c})
    if served_area and NATIONAL_TEXT.search(served_area):
        return 'national', f'source says "{served_area}"'
    if len(states) >= 4:
        return 'national', f'seen at events in {len(states)} states'
    if len(states) >= 2:
        return 'regional', 'seen at events in ' + ', '.join(states)
    if served_area and STATEWIDE_TEXT.search(served_area):
        return 'state', f'source says "{served_area}"'
    if len(cities) >= 2:
        return 'state', f'seen at events in {len(cities)} cities'
    if cities:
        return 'local', f'seen in {cities[0]}'
    if served_area:
        return 'local', f'source says "{served_area}"'
    if home_state:
        return 'local', f'based in {home_state}'
    return 'local', 'one event so far'


assert set(c for c, _ in KEYWORDS) <= set(CATEGORIES)
assert set(SOURCE_CATEGORY.values()) <= set(CATEGORIES)
