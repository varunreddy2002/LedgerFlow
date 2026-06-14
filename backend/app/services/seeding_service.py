"""Business defaults seeding — runs once when a new business is created.

Creates two things:
  1. System categories  — standard chart of accounts (is_system=True).
  2. Generic categorization rules — regex patterns pointing to those categories,
     covering the most common SaaS / solo-entrepreneur transaction descriptions.

Both are scoped to the business so the owner can edit, extend, or delete them
without affecting other businesses.  ``is_system=True`` is just a UI hint that
these were auto-generated — it does not prevent editing.
"""

import logging

from sqlalchemy.orm import Session

from app.models.business import Category
from app.models.enums import CategoryType, TransactionType
from app.models.transaction import CategorizationRule

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# System category definitions
# Each entry: (display_name, CategoryType)
# ---------------------------------------------------------------------------

SYSTEM_CATEGORIES: list[tuple[str, CategoryType]] = [
    ("Revenue",                 CategoryType.REVENUE),
    ("Cost of Goods Sold",      CategoryType.COGS),
    ("Software & SaaS",         CategoryType.EXPENSE),
    ("Payroll & Contractors",   CategoryType.EXPENSE),
    ("Marketing & Advertising", CategoryType.EXPENSE),
    ("Travel & Transport",      CategoryType.EXPENSE),
    ("Meals & Entertainment",   CategoryType.EXPENSE),
    ("Bank Fees",               CategoryType.EXPENSE),
    ("Office & Operations",     CategoryType.EXPENSE),
    ("Owner Draw",              CategoryType.NON_PNL),
    ("Transfer",                CategoryType.TRANSFER),
]


# ---------------------------------------------------------------------------
# Generic rule definitions
# Each entry: (regex_pattern, category_name, TransactionType, confidence)
#
# Patterns are case-insensitive (applied with re.IGNORECASE in the engine).
# ``category_name`` must match exactly one entry in SYSTEM_CATEGORIES above.
# ---------------------------------------------------------------------------

GENERIC_RULES: list[tuple[str, str, TransactionType, float]] = [
    # --- Inflows / Revenue ---
    (
        r"stripe|paypal|square|shopify payments|braintree|gumroad",
        "Revenue",
        TransactionType.REVENUE,
        0.80,
    ),
    # --- Cloud & SaaS infrastructure ---
    (
        r"amazon web services|aws|google cloud|azure|digitalocean|heroku|vercel|cloudflare",
        "Software & SaaS",
        TransactionType.EXPENSE,
        0.85,
    ),
    # --- SaaS tools ---
    (
        r"github|notion|figma|slack|zoom|dropbox|hubspot|intercom|jira|linear|loom|canva|adobe",
        "Software & SaaS",
        TransactionType.EXPENSE,
        0.85,
    ),
    # --- Payroll & HR ---
    (
        r"gusto|rippling|adp|deel|remote\.com|justworks|bamboohr|paychex",
        "Payroll & Contractors",
        TransactionType.EXPENSE,
        0.85,
    ),
    # --- Advertising ---
    (
        r"google ads|facebook ads|meta ads|instagram ads|twitter ads|linkedin ads|tiktok ads",
        "Marketing & Advertising",
        TransactionType.EXPENSE,
        0.85,
    ),
    # --- Travel ---
    (
        r"uber|lyft|airbnb|delta air|united airlines|southwest|american airlines|expedia|booking\.com",
        "Travel & Transport",
        TransactionType.EXPENSE,
        0.75,
    ),
    # --- Meals ---
    (
        r"doordash|grubhub|uber eats|starbucks|chipotle|restaurant|cafe|diner",
        "Meals & Entertainment",
        TransactionType.EXPENSE,
        0.70,
    ),
    # --- Bank fees ---
    (
        r"bank fee|service fee|overdraft fee|wire fee|monthly fee|account fee",
        "Bank Fees",
        TransactionType.EXPENSE,
        0.85,
    ),
    # --- Office ---
    (
        r"amazon|staples|office depot|fedex|ups|usps|postage",
        "Office & Operations",
        TransactionType.EXPENSE,
        0.65,
    ),
    # --- Transfers (lower confidence — description often ambiguous) ---
    (
        r"transfer|zelle|wire transfer|ach transfer|venmo",
        "Transfer",
        TransactionType.TRANSFER,
        0.70,
    ),
    # --- Owner draw ---
    (
        r"owner draw|owner withdrawal|personal withdrawal",
        "Owner Draw",
        TransactionType.OWNER_DRAW,
        0.85,
    ),
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def seed_business_defaults(db: Session, business_id: int) -> None:
    """Create system categories and generic rules for a newly created business.

    Safe to call multiple times — skips categories / rules that already exist
    for the business (matched by name / pattern).
    """
    # --- 1. Seed system categories ----------------------------------------
    existing_names: set[str] = {
        name
        for (name,) in db.query(Category.name).filter(
            Category.business_id == business_id,
            Category.is_system == True,  # noqa: E712
        )
    }

    new_categories: list[Category] = []
    for name, cat_type in SYSTEM_CATEGORIES:
        if name not in existing_names:
            new_categories.append(
                Category(
                    business_id=business_id,
                    name=name,
                    category_type=cat_type,
                    is_system=True,
                )
            )

    if new_categories:
        db.add_all(new_categories)
        db.flush()  # assigns IDs before we build the rules
        logger.info(
            "Seeded %d system categories for business_id=%s",
            len(new_categories),
            business_id,
        )

    # --- 2. Build name → id lookup ----------------------------------------
    category_map: dict[str, int] = {
        name: cat_id
        for name, cat_id in db.query(Category.name, Category.id).filter(
            Category.business_id == business_id,
            Category.is_system == True,  # noqa: E712
        )
    }

    # --- 3. Seed generic categorization rules ------------------------------
    existing_patterns: set[str] = {
        pattern
        for (pattern,) in db.query(CategorizationRule.merchant_pattern).filter(
            CategorizationRule.business_id == business_id,
        )
    }

    new_rules: list[CategorizationRule] = []
    for pattern, category_name, txn_type, confidence in GENERIC_RULES:
        if pattern in existing_patterns:
            continue
        cat_id = category_map.get(category_name)
        if cat_id is None:
            logger.warning(
                "Category '%s' not found for business_id=%s — skipping rule.",
                category_name,
                business_id,
            )
            continue
        new_rules.append(
            CategorizationRule(
                business_id=business_id,
                merchant_pattern=pattern,
                category_id=cat_id,
                transaction_type=txn_type,
                confidence_boost=confidence,
            )
        )

    if new_rules:
        db.add_all(new_rules)
        logger.info(
            "Seeded %d generic categorization rules for business_id=%s",
            len(new_rules),
            business_id,
        )
