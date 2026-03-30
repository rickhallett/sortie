# Sortie Eval Plan

Comprehensive evaluation suite covering the modern web development problem space. Each eval is a small, self-contained project built via swarm + sortie, designed to stress-test specific bug classes that adversarial multi-model review should catch.

## Design Principles

- Each eval is 2-4 worker scope (completable in 30-60 minutes)
- Each targets bug classes where models from different labs have demonstrably different priors
- Together they cover the major axes of web development: data, auth, state, I/O, time, money, concurrency, trust boundaries
- Each eval produces ledger data that answers: did sortie catch bugs humans would care about?
- Evals are ordered by increasing subtlety -- early evals have obvious bugs, later ones have nuanced ones

## Eval Matrix

| # | Project | Bug Classes | Why Multi-Model Helps |
|---|---------|-------------|----------------------|
| 001 | Carrier Integration Service | Auth lifecycle, HTTP error classification, type safety | Baseline -- proved the concept |
| 002 | Rate Limiter | Concurrency, time handling, floating-point drift | Models differ on concurrent-safety intuitions |
| 003 | JWT Auth Middleware | Token validation, timing attacks, secret management | Security priors vary dramatically across labs |
| 004 | Event Sourcing Store | Ordering guarantees, idempotency, projection consistency | Stateful reasoning is model-specific |
| 005 | Form Validation Engine | Unicode edge cases, ReDoS, type coercion | String handling blind spots are lab-specific |
| 006 | Webhook Delivery System | At-least-once semantics, retry backoff, signature verification | Distributed systems intuitions vary |
| 007 | File Upload Pipeline | Path traversal, MIME validation, streaming backpressure | Security + I/O -- different axes per model |
| 008 | Shopping Cart with Optimistic Locking | Race conditions, stale reads, price consistency | Concurrency + money -- highest stakes |
| 009 | Database Migration Runner | Idempotency, rollback safety, lock ordering | Destructive operations -- models are most cautious here |
| 010 | Server-Sent Events Multiplexer | Connection lifecycle, backpressure, reconnection state | Real-time edge cases are under-represented in training |

---

## Eval 003: JWT Auth Middleware

**Scope:** Express/Hono middleware that validates JWTs, manages refresh tokens, and enforces role-based access.

**Target bug classes:**
- Algorithm confusion (accepting `alg: none` or `HS256` when `RS256` expected)
- Token expiry off-by-one (clock skew tolerance)
- Refresh token rotation without invalidation of old tokens
- Timing-safe comparison for signatures
- Secret/key leakage in error messages
- Missing audience/issuer validation
- Bearer token extraction from non-standard headers

**Swarm split (3 workers):**
- Worker A: Token types, config, key management interface
- Worker B: JWT verification middleware (sign, verify, decode)
- Worker C: Refresh token rotation + role-based access control

**Why adversarial review matters:** Security bugs in auth middleware have the highest blast radius. Claude tends to flag algorithm confusion, GPT catches timing attacks, Gemini finds configuration validation gaps. Cross-model coverage is critical.

**Eval measures:**
- How many OWASP JWT vulnerabilities does sortie catch unprompted?
- Do convergent findings align with known JWT attack vectors?
- What's the false positive rate on security findings?

---

## Eval 004: Event Sourcing Store

**Scope:** TypeScript event store with append-only log, snapshot projections, and replay capability.

**Target bug classes:**
- Event ordering violations under concurrent appends
- Snapshot/projection desync after failed writes
- Replay idempotency (applying the same event twice)
- Version conflict detection with optimistic concurrency
- Unbounded event stream memory growth
- Serialization round-trip fidelity (Date, BigInt, undefined)

**Swarm split (3 workers):**
- Worker A: Event types, store interface, in-memory append log
- Worker B: Projection engine (fold events into state)
- Worker C: Snapshot + replay + conflict detection

**Why adversarial review matters:** Event sourcing correctness depends on invariants that are easy to state but hard to verify by inspection. Models reason differently about state machines -- Claude tends to catch ordering issues, GPT finds serialization edge cases, Gemini flags memory growth.

**Eval measures:**
- Does sortie catch the classic projection-desync bug?
- Do findings map to known event sourcing anti-patterns?
- How do models handle the replay-idempotency invariant?

---

## Eval 005: Form Validation Engine

**Scope:** Composable validation library with built-in validators for common web form fields (email, phone, URL, credit card, password strength).

**Target bug classes:**
- ReDoS in regex-based validators (catastrophic backtracking)
- Unicode normalization (visually identical but different codepoints)
- Type coercion exploits (`"0"` vs `0` vs `false` vs `""`)
- Email validation RFC compliance vs practical acceptance
- Locale-dependent phone number parsing
- XSS in error message interpolation
- Length validation on multi-byte strings (bytes vs characters vs grapheme clusters)

**Swarm split (3 workers):**
- Worker A: Validator interface, composition utilities (and/or/pipe), result types
- Worker B: String validators (email, URL, phone, credit card)
- Worker C: Type validators (number ranges, enum, date, password strength)

**Why adversarial review matters:** String handling and regex safety are areas where model priors diverge most. Claude is conservative on regex safety, GPT catches Unicode edge cases, Gemini finds type coercion issues. This eval specifically tests whether sortie catches ReDoS -- a bug class that's hard to spot by inspection.

**Eval measures:**
- Does sortie flag any ReDoS-vulnerable regexes?
- Are Unicode normalization issues caught?
- How do models handle the bytes-vs-characters-vs-graphemes distinction?

---

## Eval 006: Webhook Delivery System

**Scope:** Queue-backed webhook dispatcher with retry logic, HMAC signature verification, and delivery receipts.

**Target bug classes:**
- At-least-once vs exactly-once delivery confusion
- Exponential backoff without jitter (thundering herd)
- HMAC timing attack in signature verification
- Payload tampering between queue and delivery
- Dead letter queue overflow without alerting
- Idempotency key collision on retry
- Connection pooling exhaustion under load

**Swarm split (4 workers):**
- Worker A: Event types, queue interface, delivery receipt model
- Worker B: HMAC signing + verification
- Worker C: Retry engine with backoff + jitter + dead letter
- Worker D: Delivery dispatcher with connection management

**Why adversarial review matters:** Distributed delivery semantics are where models disagree most productively. The "at-least-once vs exactly-once" confusion is caught differently by each model. Timing attacks in HMAC are a classic security finding that varies by model prior.

**Eval measures:**
- Is the thundering herd problem (backoff without jitter) caught?
- Do models independently find the HMAC timing vulnerability?
- How is the at-least-once guarantee evaluated?

---

## Eval 007: File Upload Pipeline

**Scope:** Multipart upload handler with streaming to object storage, MIME validation, image processing, and virus scanning hook.

**Target bug classes:**
- Path traversal via filename (`../../etc/passwd`)
- MIME type mismatch (claims image/png, actually executable)
- Streaming backpressure (slow consumer, fast producer)
- Incomplete upload cleanup (orphaned temporary files)
- Double-extension bypass (`file.php.jpg`)
- Content-length mismatch / request smuggling
- Memory exhaustion from unbounded buffering

**Swarm split (3 workers):**
- Worker A: Upload types, storage interface, temp file management
- Worker B: Multipart parser with streaming + backpressure
- Worker C: MIME validation + image processing + virus scan hook

**Why adversarial review matters:** File upload is the intersection of security and I/O correctness -- two axes where models have very different strengths. Path traversal is Claude's strong suit, streaming edge cases are GPT's, MIME validation gaps are caught by Gemini.

**Eval measures:**
- Is path traversal caught as critical/convergent?
- Do models find the double-extension bypass?
- Is the orphaned temp file cleanup issue flagged?

---

## Eval 008: Shopping Cart with Optimistic Locking

**Scope:** Cart service with inventory reservation, price consistency, and concurrent modification handling via optimistic locking.

**Target bug classes:**
- TOCTOU race (check inventory, then reserve -- another request between)
- Price change between add-to-cart and checkout
- Lost update on concurrent cart modifications
- Phantom read on inventory during checkout
- Money representation (floating-point vs integer cents)
- Negative quantity / negative price edge cases
- Lock version mismatch handling and retry

**Swarm split (3 workers):**
- Worker A: Cart types, Money type (integer cents), inventory interface
- Worker B: Cart operations (add, remove, update quantity) with optimistic locking
- Worker C: Checkout flow with inventory reservation + price verification

**Why adversarial review matters:** Money handling and race conditions are the highest-stakes combination. Models are unanimously good at catching floating-point money bugs (easy convergence signal). The TOCTOU race is where model priors diverge -- it's subtle and context-dependent. This eval tests sortie on the bugs that cost companies real money.

**Eval measures:**
- Is the floating-point money bug convergent across all 3 models?
- Do models find the TOCTOU inventory race?
- How is the price-change-during-checkout scenario handled?
- What's the convergence rate on the highest-stakes findings?

---

## Eval 009: Database Migration Runner

**Scope:** Schema migration tool that runs up/down migrations with lock ordering, checksum verification, and rollback support.

**Target bug classes:**
- Non-idempotent migrations (running twice breaks schema)
- Missing rollback for data migrations (DDL rollback != data rollback)
- Lock ordering deadlocks (migration A locks table X then Y, migration B locks Y then X)
- Checksum drift (migration file edited after applied)
- Concurrent migration runners (two processes start migration simultaneously)
- Partial migration failure (5 of 10 statements succeed, then error)
- Character encoding mismatch between migration files and database

**Swarm split (3 workers):**
- Worker A: Migration types, file loader, checksum computation
- Worker B: Migration executor with transaction wrapping + lock management
- Worker C: State tracking (applied migrations table) + rollback engine

**Why adversarial review matters:** Migrations are destructive and irreversible in production. Models are most cautious here -- which means they produce more findings, but also more false positives. This eval tests sortie's triage quality: can it distinguish real migration risks from overreactive caution?

**Eval measures:**
- How many findings are false positives (overreactive caution)?
- Is the concurrent runner race condition found?
- Do models catch the partial-failure-without-rollback bug?
- What's the precision rate compared to other evals?

---

## Eval 010: SSE Multiplexer

**Scope:** Server-Sent Events hub that manages multiple channels, client subscriptions, reconnection with last-event-ID, and backpressure.

**Target bug classes:**
- Connection leak (client disconnects, server keeps writing)
- Backpressure: slow client blocks fast channel
- Last-Event-ID replay on reconnect delivers duplicates or misses events
- Channel cleanup after last subscriber leaves
- Memory growth from unbounded event buffers
- UTF-8 encoding issues in SSE data fields (newlines must be escaped)
- Keep-alive comment timing (too frequent = waste, too rare = proxy timeout)

**Swarm split (3 workers):**
- Worker A: Event types, channel registry, subscription management
- Worker B: SSE encoder (spec-compliant formatting, keep-alive, retry field)
- Worker C: Client connection lifecycle + reconnection + backpressure

**Why adversarial review matters:** Real-time connection lifecycle is the least-represented domain in LLM training data. Models struggle differently with SSE spec compliance, connection cleanup, and backpressure semantics. This eval tests sortie at the edge of what models can reliably review.

**Eval measures:**
- Is the connection leak found?
- How do models handle the SSE spec compliance requirements?
- What's the divergent finding rate (expected to be highest of all evals)?
- Does the debrief correctly identify SSE-specific findings vs general correctness?

---

## Analysis Plan

After all 10 evals, the ledger data answers:

### Per-Eval Metrics
- Total findings, convergent rate, precision (% fixed vs false-positive)
- Model contribution (which model found the most convergent findings)
- Bug class coverage (which target bugs were actually caught)
- Remediation cycles (how many fix rounds per worker)

### Cross-Eval Comparisons
- **Convergence by domain:** Which domains produce the most agreement? (Hypothesis: money/auth/security have highest convergence)
- **Model specialization:** Does Claude consistently catch security, GPT concurrency, Gemini performance? Or is it more nuanced?
- **Triage quality:** Which evals produce the most false positives? (Hypothesis: migrations and SSE -- domains where models are least confident)
- **Debrief accuracy:** When models disagree, how often is the divergent finding real vs noise? (Builds the case for or against convergence-only blocking)
- **Cost per real bug:** Tokens spent per finding that was actually fixed. Is multi-model review cost-justified?

### Portfolio Artifacts
- Aggregated ledger across 10 evals
- Model reliability trend (success rate improvement from v1 → v2 → v3)
- Bug class taxonomy: which bugs are systematically caught, which are systematically missed
- The "sortie coverage map": a matrix of [domain x bug class x model] showing where the system is strong and where it's blind
