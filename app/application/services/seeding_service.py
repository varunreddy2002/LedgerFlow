import logging

from sqlalchemy.orm import Session

from app.domain.models import Category, CategorizationRule
from app.domain.enums import CategoryType

logger = logging.getLogger(__name__)


SYSTEM_CATEGORIES: list[tuple[str, CategoryType]] = [
    ("Revenue",                 CategoryType.REVENUE),
    ("Cost of Goods Sold",      CategoryType.EXPENSE),
    ("Software & SaaS",         CategoryType.EXPENSE),
    ("Payroll & Contractors",   CategoryType.EXPENSE),
    ("Marketing & Advertising", CategoryType.EXPENSE),
    ("Travel & Transport",      CategoryType.EXPENSE),
    ("Meals & Entertainment",   CategoryType.EXPENSE),
    ("Bank Fees",               CategoryType.EXPENSE),
    ("Office & Operations",     CategoryType.EXPENSE),
    ("Owner Draw",              CategoryType.OWNER_DRAW),
    ("Transfer",                CategoryType.TRANSFER),
]

# (regex_pattern, category_name, confidence)
GENERIC_RULES: list[tuple[str, str, float]] = [
    (r"stripe|paypal|square|shopify payments|braintree|gumroad",                              "Revenue",                0.80),
    (r"amazon web services|aws|google cloud|azure|digitalocean|heroku|vercel|cloudflare",     "Software & SaaS",        0.85),
    (r"github|notion|figma|slack|zoom|dropbox|hubspot|intercom|jira|linear|loom|canva|adobe", "Software & SaaS",        0.85),
    (r"gusto|rippling|adp|deel|remote\.com|justworks|bamboohr|paychex",                       "Payroll & Contractors",  0.85),
    (r"google ads|facebook ads|meta ads|instagram ads|twitter ads|linkedin ads|tiktok ads",   "Marketing & Advertising",0.85),
    (r"uber|lyft|airbnb|delta air|united airlines|southwest|american airlines|expedia",       "Travel & Transport",     0.75),
    (r"doordash|grubhub|uber eats|starbucks|chipotle|restaurant|cafe|diner",                  "Meals & Entertainment",  0.70),
    (r"bank fee|service fee|overdraft fee|wire fee|monthly fee|account fee",                  "Bank Fees",              0.85),
    (r"amazon|staples|office depot|fedex|ups|usps|postage",                                   "Office & Operations",    0.65),
    (r"transfer|zelle|wire transfer|ach transfer|venmo",                                      "Transfer",               0.70),
    (r"owner draw|owner withdrawal|personal withdrawal",                                      "Owner Draw",             0.85),
]


def seed_business_defaults(db: Session, business_id: int) -> None:
    existing_names: set[str] = {
        name for (name,) in db.query(Category.name).filter(
            Category.business_id == business_id,
        )
    }

    new_categories: list[Category] = []
    for name, cat_type in SYSTEM_CATEGORIES:
        if name not in existing_names:
            new_categories.append(Category(business_id=business_id, name=name, category_type=cat_type))

    if new_categories:
        db.add_all(new_categories)
        db.flush()
        logger.info("Seeded %d categories for business_id=%s", len(new_categories), business_id)

    category_map: dict[str, int] = {
        name: cat_id for name, cat_id in db.query(Category.name, Category.id).filter(
            Category.business_id == business_id,
        )
    }

    existing_patterns: set[str] = {
        pattern for (pattern,) in db.query(CategorizationRule.pattern).filter(
            CategorizationRule.business_id == business_id,
        )
    }

    new_rules: list[CategorizationRule] = []
    for pattern, category_name, confidence in GENERIC_RULES:
        if pattern in existing_patterns:
            continue
        cat_id = category_map.get(category_name)
        if cat_id is None:
            continue
        new_rules.append(CategorizationRule(
            business_id=business_id,
            pattern=pattern,
            category_id=cat_id,
            confidence=confidence,
            is_system=True,
        ))

    if new_rules:
        db.add_all(new_rules)
        logger.info("Seeded %d rules for business_id=%s", len(new_rules), business_id)
