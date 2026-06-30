import logging

from sqlalchemy.orm import Session

from app.domain.models import Category, CategorizationRule
from app.domain.enums import CategoryType

logger = logging.getLogger(__name__)


# Chart of accounts tuned for a consulting / professional-services business.
SYSTEM_CATEGORIES: list[tuple[str, CategoryType]] = [
    ("Consulting Revenue",                CategoryType.REVENUE),
    ("Subcontractors & Freelancers",      CategoryType.EXPENSE),
    ("Payroll & Benefits",                CategoryType.EXPENSE),
    ("Software & SaaS",                   CategoryType.EXPENSE),
    ("Professional Services",             CategoryType.EXPENSE),
    ("Marketing & Business Development",   CategoryType.EXPENSE),
    ("Travel & Client Meetings",          CategoryType.EXPENSE),
    ("Meals & Entertainment",             CategoryType.EXPENSE),
    ("Training & Development",             CategoryType.EXPENSE),
    ("Office & Admin",                    CategoryType.EXPENSE),
    ("Bank & Payment Fees",               CategoryType.EXPENSE),
    ("Taxes & Government",                CategoryType.EXPENSE),
    ("Owner Draw",                        CategoryType.OWNER_DRAW),
    ("Transfer",                          CategoryType.TRANSFER),
]

# (regex_pattern, category_name, confidence)
GENERIC_RULES: list[tuple[str, str, float]] = [
    (r"stripe|paypal|wise|bill\.com|client payment|invoice payment",                          "Consulting Revenue",               0.75),
    (r"upwork|fiverr|toptal|contra|gun\.io|freelance",                                        "Subcontractors & Freelancers",     0.80),
    (r"gusto|rippling|adp|justworks|paychex|deel",                                            "Payroll & Benefits",               0.85),
    (r"aws|amazon web services|google cloud|azure|github|notion|figma|slack|zoom|openai|anthropic|vercel|linear", "Software & SaaS",        0.85),
    (r"legal|attorney|law firm|accounting|quickbooks|cpa|insurance|clio",                     "Professional Services",            0.80),
    (r"google ads|linkedin ads|meta ads|hubspot|mailchimp|apollo",                            "Marketing & Business Development",  0.80),
    (r"delta|united|american airlines|southwest|airbnb|marriott|hilton|uber|lyft|expedia",    "Travel & Client Meetings",         0.75),
    (r"starbucks|restaurant|cafe|doordash|grubhub|uber eats|chipotle",                        "Meals & Entertainment",            0.70),
    (r"udemy|coursera|pluralsight|oreilly|conference|summit",                                 "Training & Development",           0.75),
    (r"amazon|staples|fedex|ups|usps|wework|regus",                                           "Office & Admin",                   0.65),
    (r"bank fee|wire fee|service fee|stripe fee|processing fee",                              "Bank & Payment Fees",              0.85),
    (r"irs|franchise tax|estimated tax|dept of revenue|edd",                                  "Taxes & Government",               0.85),
    (r"owner draw|owner withdrawal|distribution|partner draw",                                "Owner Draw",                       0.85),
    (r"transfer|zelle|venmo|wire transfer|ach transfer",                                      "Transfer",                         0.70),
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
