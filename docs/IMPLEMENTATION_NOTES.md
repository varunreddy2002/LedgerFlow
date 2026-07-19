# IMPLEMENTATION NOTES — Ledger Core + Ladder + Agentic Chat

Companion to `docs/HANDOVER.md`. This is the engineering write-up: what was built,
which design patterns/OOP concepts were used *where and why*, the invariants and how
they're tested, LangGraph notes, and a candid self-assessment of the engineering
standards (met / partial / skipped).

---

## 1. Module-by-module

All new code lives under `app/application/accounting/` unless noted.

| Module | Responsibility |
|---|---|
| `money.py` | The one place rounding lives: `to_money()` → 2-dp `Decimal`. Floats never touch the books. |
| `errors.py` | Custom exception hierarchy rooted at `AccountingError` (see §4). |
| `dtos.py` | Typed value objects across boundaries: `LineDraft`, `JournalEntryDraft`, `AccountNode`, `PnLReport`, `TrialBalance(Row)`. Each report DTO has `to_dict()` for the chat layer. |
| `repository.py` | Repository pattern. `LedgerRepository` **protocol** + `SqlAlchemyLedgerRepository`; also `BankTransactionRepository`, `ReviewItemRepository`. Returns primitive records/aggregates, never ORM objects, so the service stays pure. |
| `ledger.py` | `LedgerService` — `balance`, `account_tree`, `pnl`, `trial_balance`. The debit/credit **sign convention lives here once** (`_signed_balance`); reads only POSTED entries; rolls leaf balances up the COA tree. |
| `journal_entry_builder.py` | Builder pattern. `JournalEntryBuilder` refuses to build unless non-empty, balanced, and all-leaves. `AccountCatalog` is an id/code lookup built from records (no ORM). `from_bank_movement()` encodes the owner-confirmed cash-basis rule + direction check. |
| `posting_service.py` | Service layer. `PostingService.propose()` (DRAFT/PENDING) vs `.post()` (POSTED + entry number + `ApprovalEvent`). The only writer of journal entries. |
| `rule_engine.py` | `AccountingRuleEngine` — pure, first-match-by-priority; operators (`regex`/`contains`/`icontains`/`equals`) dispatched from a **registry**. `load_rules()` is the DB adapter. |
| `escalation/context.py` | `LadderContext` (mutable, threads the chain), `AccountProposal`, `LadderOutcome`; the `AccountClassifier` protocol + `NullAccountClassifier`. |
| `escalation/handlers.py` | **Chain of Responsibility**: `RuleHandler` → `AgentHandler` → `ReviewHandler`. |
| `escalation/agent_classifier.py` | `BedrockAccountClassifier` — the LLM picks an account (never an amount); direction-filtered candidates. |
| `escalation/pipeline.py` | `CategorizationPipeline` + `build_pipeline()` factory (wires the chain, reads thresholds from `settings`). |
| `review/dtos.py` | `ReviewResolution` (input), `ResolutionResult`, `ReviewItemView` (read model). |
| `review/handlers.py` | **Strategy** + **Registry**: `ReviewItemHandler` interface, `BankRowReviewHandler` (uncategorized + large_amount), `StubReviewHandler` (the other 7), `ReviewItemHandlerRegistry`. |
| `review/rule_learning.py` | `RuleLearner` — the flywheel: a correction becomes a new `accounting_rule`. |
| `review/service.py` | `ReviewQueueService` — `list`, `preview` (read-only, for the interrupt), `resolve` (dispatches to a handler). |
| `app/application/skills.py` | `SkillRegistry` — parses `skills/*.md` frontmatter, serves a one-line index + on-demand playbooks. |
| `agents/chat/*` | Rebuilt LangGraph loop (see §5). |
| `services/seeding_service.py` | `BusinessSeeder` — COA tree (derives normal_balance/level/posting), rules, sample POSTED JEs (via the builder+posting), UNPROCESSED bank rows. |

---

## 2. Design patterns — where and why

- **Repository** (`repository.py`) — `LedgerService`/handlers depend on the
  `LedgerRepository` protocol, not SQLAlchemy. This is the DIP seam that lets the
  entire ledger be unit-tested with an in-memory `FakeLedgerRepository` (zero DB).
- **Builder** (`JournalEntryBuilder`) — makes an invalid journal entry
  *unconstructable*: the only way to get a `JournalEntryDraft` is through the builder,
  which enforces balanced + leaves-only. Callers never touch raw signs.
- **Service layer** (`PostingService`, `ReviewQueueService`, `LedgerService`) —
  orchestration separated from persistence (repositories) and domain calc (builder/ledger).
- **Chain of Responsibility** (`escalation/handlers.py`) — the escalation ladder.
  Each handler resolves or forwards; adding a step doesn't touch the others. The tail
  (`ReviewHandler`) always resolves, so the chain can't fall through.
- **Strategy** (`review/handlers.py`) — per-item-type resolution behind one interface;
  `uncategorized`/`large_amount` share `BankRowReviewHandler`, the rest are stubs.
- **Registry** (three of them) — rule-operator registry (`rule_engine`), review-item
  handler registry (`review/handlers`), and the tool/skill indices in chat.
  Data-driven dispatch, no `if/elif` ladders — Open/Closed.
- **Command** (chat nodes) — every node returns `Command(goto, update)`; routing lives
  with the node that owns the decision.
- **DTO / value objects** (`dtos.py`, `review/dtos.py`) — typed dataclasses cross every
  boundary; no loose dicts in the domain. (Dicts appear only at the JSON edge:
  `to_dict()` for the LLM, and the `proposed_resolution` JSONB blob.)
- **Factory** (`build_pipeline`, `build_review_service`, `build_registry`) — assemble
  a fully-wired object graph bound to one session.

**OOP/SOLID specifics**: the sign rule is encapsulated in `LedgerService`; posting
invariants in `JournalEntryBuilder`; callers never see raw debit/credit signs. Adding a
skill, a rule operator, an escalation step, or a review-item type is additive (new file
/ new registration), not a switch edit.

---

## 3. Architecture decisions & trade-offs

- **`journal_entries` / `journal_entry_lines`** naming (per the build plan), not the
  schema doc's `transactions`/`entries` — clearer, and retires the overloaded flat
  `transactions` name.
- **Repository returns records/aggregates, not ORM objects.** Slightly more mapping
  code, but it keeps all sign/rollup math in a pure, fast-to-test service. Worth it.
- **The proposal *is* a draft journal entry** (no separate proposal tables) — per the
  schema doc decision. `PENDING_APPROVAL` → approve → `POSTED`.
- **Cash side deterministic, counter side classified** — exactly the owner-confirmed
  rules. Direction consistency is enforced in the builder; violations escalate to
  review rather than posting nonsense.
- **High-confidence rules auto-post; agent proposals never do.** The agent can only
  choose an account and always routes to review; only the deterministic layer (a
  seeded/learned rule ≥ threshold, under the large-amount cap) posts without a human.
- **Ladder fed from seeded `bank_transactions`**, not live upload — ingestion stays
  dormant this session by design.
- **Boot-path cleanup**: dropping the flat schema broke several out-of-scope modules
  (ingestion, old agents, old routes/schemas). I deleted what was fully superseded and
  neutered the rest (upload → 501, empty package `__init__`s) so the app boots clean,
  rather than half-porting ingestion out of scope.

---

## 4. Custom exceptions

```
AccountingError
├── LedgerError → UnbalancedEntryError, PostingToNonLeafError,
│                 EmptyJournalEntryError, AccountNotFoundError, DirectionConsistencyError
├── ReviewError → ReviewItemNotFoundError, ReviewItemAlreadyResolvedError,
│                 UnsupportedReviewItemTypeError
├── SkillNotFoundError
└── EscalationError
```

Raised specifically, never swallowed; the chat tools translate them into user-facing
notes at the boundary.

---

## 5. LangGraph notes (web-confirmed this session)

- Installed **LangGraph 1.2.6**. Confirmed current API from the official docs:
  `from langgraph.graph import StateGraph, START, END`; `from langgraph.types import
  Command, interrupt`; nodes return `Command(goto=, update=)`; `interrupt(payload)`
  pauses and is resumed with `Command(resume=value)`; requires a checkpointer +
  `config={"configurable": {"thread_id": ...}}`. The repo's existing patterns already
  matched 1.x, so the rebuild kept the skeleton and added nodes.
- **Rebuilt loop**: `agent ⇄ run_tools`, plus two interrupt branches sharing one
  mechanism — **review approval** (`run_tools → review_preview → review_confirm
  (interrupt) → review_apply`) and the retained **chart** branch. `review_preview`
  computes a read-only preview so the owner sees the exact Dr/Cr lines before
  confirming; nothing writes until `review_apply` after approval.
- **`run_tools` answers every tool_call** with a `ToolMessage` (the old code only
  handled the first call — a latent bug against Bedrock, now fixed) and diverts a
  single signal tool (`resolve_review_item` / `request_chart`) to its branch.
- **System prompt** dropped the always-on ~100-line schema for: concise accounting
  grounding + a one-line **skill index** + a tool index. Full playbooks load on demand
  via `load_skill`.
- Both paths were **run for real against Bedrock** this session (not mocked): P&L
  rendered a hierarchical report; the ladder path listed items, interrupted with a
  correct entry preview, posted on approval, and learned a rule.

---

## 6. Invariants & how they're tested

41 tests, all green (`pytest`). Pure unit tests use an in-memory repo/catalog; DB-backed
integration tests run in a rolled-back Postgres transaction (skip if DB is down).

| Invariant | Test(s) |
|---|---|
| Sign convention (debit/credit normal) | `test_ledger.py::test_signed_balance_*` |
| P&L rolls up the tree; net income correct | `test_ledger.py::test_pnl_*` |
| Trial balance foots (Σdr == Σcr) | `test_ledger.py::test_trial_balance_balances` |
| Builder: balanced / leaves-only / empty | `test_builder.py::*` |
| Cash-basis direction rules + conflict | `test_builder.py::test_money_*`, `test_escalation.py::test_direction_conflict_*` |
| Rule engine match / priority / operators | `test_rule_engine.py::*` |
| Ladder: auto-post vs review, large-amount override | `test_escalation.py::*` |
| POSTED-only visibility (proposals invisible) | `test_integration.py::test_proposed_draft_is_invisible_to_reports` |
| Pipeline splits seeded rows (4 post / 3 review) | `test_integration.py::test_pipeline_splits_bank_rows` |
| Review resolve → balanced post + learned rule | `test_integration.py::test_resolve_uncategorized_posts_entry_and_learns_rule` |
| Not-found / double-resolve guards | `test_integration.py::test_*_raises` |

---

## 7. Candid gaps / shortcuts / tech-debt

- **Agent classifier is lightly exercised.** `BedrockAccountClassifier` is implemented
  and wired (`run_pipeline.py --agent`), but the deterministic path is the default and
  the unit tests use `NullAccountClassifier`. The agent's *proposal* still always goes
  to review, so correctness doesn't hinge on it — but its prompt isn't tuned/evaluated.
- **Rule learning is coarse.** `RuleLearner._keyword` takes the first ~3 alphabetic
  tokens of the description as an `icontains` key. Good enough to demo the flywheel;
  a real system wants vendor normalization and confidence decay.
- **No REST surface for the ledger/review** beyond chat + the COA read route. The
  `transactions` route was removed; inspect via chat, `query_ledger`, or SQL.
- **Old migration downgrade is broken** (pre-existing, documented in HANDOVER §2).
  `upgrade head` on a fresh DB is clean; `downgrade base` is not.
- **`type: ignore`-free but not type-checker-verified** — no mypy/pyright is configured
  in the repo, so "clean under the configured type checker" means "fully annotated with
  `from __future__ import annotations`", not "a checker ran".
- **Ingestion left dormant** (by plan) — the dormant modules still import dropped
  symbols; they're off the boot path but will error if imported directly.
- **Windows console logging**: log messages are ASCII-only on purpose (the cp1252
  console can't encode `Σ`/em-dash). LLM answers may contain Unicode — that's fine over
  UTF-8, only console logging was the constraint.

---

## 8. Engineering-standards self-assessment

| Standard | Status | Notes |
|---|---|---|
| OOP & SOLID (SRP classes, DIP, Open/Closed) | **Met** | Repository/Builder/Service/CoR/Strategy/Registry all real; extension is additive. |
| Encapsulate debit/credit + posting invariants | **Met** | Sign rule in `LedgerService`; balance/leaf rules in `JournalEntryBuilder`; callers never touch signs. |
| Named design patterns, used where they fit | **Met** | Repository, Builder, Service, CoR, Strategy, Registry, Command, DTO, Factory — all present and documented above. |
| Full type hints, `from __future__ import annotations` | **Met** | Throughout new code. |
| Clean under a configured type checker | **Partial** | No checker configured in the repo; code is fully annotated but not machine-verified. |
| Docstrings on public classes/methods | **Met** | Purpose/args/invariants on public surface. |
| Structured logging via `get_logger`, no `print` | **Met** | Leveled logs at boundaries (tool calls, posting, skill load, escalation/review decisions). Scripts use `print` intentionally (CLI output). |
| Custom exception hierarchy, fail loudly | **Met** | See §4; nothing swallowed. |
| Config via `settings`, no magic numbers; wire dead config | **Met** | Wired `large_transaction_threshold` (was dead) + `categorization_confidence_threshold` into the ladder. |
| Invariants enforced in code + unit-tested | **Met** | 41 tests; see §6. |
| Latest LangGraph, web-confirmed | **Met** | 1.2.6 confirmed against current docs; both paths run live. |
| Review queue generic; 2 types full, rest stubs | **Met** | Registry + Strategy; `uncategorized`/`large_amount` full, 7 stubs. |
| Money never LLM-derived | **Met** | Classifier picks accounts only; amounts from data; balancing in builder. |
| Nothing posts without the human gate | **Met** | Review resolutions pass the `interrupt`; agent proposals never auto-post; only high-confidence rules do. |

---

## 9. Next-session TODOs

1. Repoint ingestion (`ingestion_service`) to create `bank_transactions`/bills/invoices,
   then trigger `build_pipeline`.
2. Build the `bills`/`invoices`/`payment_allocations` tables and AP/AR + reconciliation;
   promote the `payment_match` / `unmatched_party` / `duplicate` review stubs to real handlers.
3. Add `balance_sheet` + aging to `LedgerService` and matching skills.
4. Tune + evaluate the `BedrockAccountClassifier` prompt; add a golden-set accuracy harness.
5. Real approval identity (auth/RBAC) — replace the `"owner"`/`"system"` actor strings.
6. Configure a type checker (mypy/pyright) in CI; squash/fix the old migration downgrade.
7. Semantic memory (type 3): `recall_memory` tool + `business_memory` table (seam reserved).
