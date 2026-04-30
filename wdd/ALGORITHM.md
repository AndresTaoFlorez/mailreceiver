# Weighted Deficit Dispatch (WDD)

Technical specification for the case assignment algorithm implemented in `wdd/`.

---

## 1. Overview

**Weighted Deficit Dispatch** is a deterministic, deficit-first assignment algorithm designed specifically for human support workloads. It distributes incoming cases across a pool of specialists one at a time, prioritizing whoever the system owes the most work to.

Unlike classic Round Robin which assigns in blind turns, WDD:
- Maintains **accumulated deficit memory** between rounds for long-term fairness
- Uses **work windows** to know who is available at assignment time
- Supports **escalations and transfers** that adjust each specialist's debt

The algorithm is stateless, synchronous, and free of infrastructure dependencies. It operates as a pure function: given the current pool state and a list of unassigned cases, it returns a complete set of assignment decisions.

---

## 2. The Deficit Model

### 2.1 Why No Credit

In classic DRR (Deficit Round Robin), credit exists because the quantum is fixed and cases have variable size. In this domain:

- Cases are **unitary** (one case = one case)
- The number of cases per round is **variable and unpredictable**
- There is no fixed quantum that can "overflow"

Therefore **credit disappears** and what matters is only the deviation from ideal distribution.

### 2.2 Deficit Calculation

```
ideal(i)     = total_cases × (load_percentage(i) / 100)
received(i)  = cases_assigned(i)
deficit(i)   = ideal(i) - received(i)
```

| Sign | Meaning |
|------|---------|
| **Positive deficit** | System owes the specialist cases — **highest priority** |
| **Negative deficit** | Specialist is ahead of their fair share — lowest priority |
| **Zero deficit** | Specialist is exactly where they should be |

### 2.3 Priority

At each assignment step:

```
priority = deficit(i)    — highest deficit gets the next case
tiebreak = last_updated  — least recently updated wins ties
```

After each assignment, the deficit of **every** pool member is recalculated against the new total, ensuring the next pick always reflects the current state.

---

## 3. Definitions

| Term | Definition |
|------|-----------|
| **Pool** | The set of specialists eligible to receive cases in a given assignment run. |
| **Pool Member** | A specialist within the pool, characterized by a load percentage, a count of previously assigned cases, and a running deficit. |
| **Load Percentage** | The target share of total cases a specialist should receive, expressed as a percentage (0–100). May be explicitly set or auto-computed. |
| **Cases Assigned** | The cumulative number of cases a specialist has received within the current work window. |
| **Expected Cases (ideal)** | The number of cases a specialist *should* have received: `total_cases × (load_percentage / 100)`. |
| **Deficit** | The signed difference `expected_cases − cases_assigned`. Positive = system owes specialist. Negative = specialist is ahead. |
| **Drip** | The one-by-one assignment strategy where the pool is re-sorted after every single case assignment. |
| **Escalation** | A manual deficit adjustment when one specialist transfers a case to another. |

---

## 4. Algorithm

### 4.1 Load Percentage Resolution

Before assignment begins, each pool member's effective load percentage is resolved:

1. Members with an explicitly configured `load_percentage` retain that value.
2. Members with `load_percentage = null` split the **remaining** percentage equally.
3. The remaining percentage is defined as `max(0, 100 − sum_of_fixed_percentages)`.

**Example:**

| Specialist | Configured % | Effective % |
|-----------|-------------|------------|
| A         | 60          | 60         |
| B         | null        | 20         |
| C         | null        | 20         |

### 4.2 Progressive Drip Loop

For each unassigned case, in input order:

1. **Sort** the pool by `(deficit DESC, last_updated ASC)`.
   - The member with the highest positive deficit (most owed) ranks first.
   - If two members share the same deficit, the one whose state was least recently updated ranks first.
2. **Select** the first member in the sorted order.
3. **Assign** the case to the selected member.
4. **Update** the selected member:
   - `cases_assigned ← cases_assigned + 1`
   - `total_cases ← total_cases + 1`
   - `expected_cases ← total_cases × (load_percentage / 100)`
   - `deficit ← expected_cases − cases_assigned`
5. **Recalculate** `expected_cases` and `deficit` for all other members using the new `total_cases`.
6. **Record** the assignment decision in the output report.

Cases provided when the pool is empty are placed in the queued list without assignment.

### 4.3 Escalations and Transfers

When a specialist escalates or transfers a case to another:

```
source.deficit += 1        # the case shouldn't count against them
source.cases_assigned -= 1 # effectively received one less

target.deficit -= 1        # they took on extra work, now more ahead
target.cases_assigned += 1 # effectively received one more
```

This ensures the next assignment round correctly compensates the source and reduces priority for the target.

**Example:** Luis escalates a case to Ana:

| Before | deficit(Luis) = 0 | deficit(Ana) = 0 |
|--------|-------------------|------------------|
| After  | deficit(Luis) = +1 | deficit(Ana) = -1 |

Luis now has higher priority in the next round.

### 4.4 Complexity

| Metric | Value |
|--------|-------|
| Time | `O(n × p log p)` where `n` = number of cases, `p` = pool size |
| Space | `O(n + p)` |

The sort at each iteration dominates. For typical pool sizes (< 50 specialists), the per-case overhead is negligible.

---

## 5. Properties

### 5.1 Determinism

Given identical inputs (pool state, case list), the algorithm produces identical outputs. There is no randomness, no external state dependency, and no tie-breaking ambiguity (the `last_updated` timestamp resolves all ties).

### 5.2 Convergence

The deficit of every pool member converges toward zero as the number of assigned cases grows. After a sufficiently large batch, the actual distribution matches the configured load percentages within a margin of one case.

### 5.3 Starvation Freedom

Every pool member with a non-zero load percentage will eventually receive cases. The deficit-first selection guarantees that no member is indefinitely skipped — their deficit grows with each case assigned to others, eventually making them the top priority.

### 5.4 Order Independence of Pool Members

The final distribution is independent of the initial ordering of pool members. Only the deficit values and timestamps affect selection.

### 5.5 Escalation Neutrality

Escalations are zero-sum: `source.deficit += 1` and `target.deficit -= 1`. The total system deficit remains constant. Over a large enough batch, the algorithm naturally rebalances after escalation events.

---

## 6. Data Model

### 6.1 Input

```
PoolMember
├── code: str               — Unique identifier for the specialist
├── load_percentage: float?  — Target share (null = auto-split)
├── cases_assigned: int      — Cases already assigned in this window
├── deficit: Decimal         — Current deficit (expected − assigned)
│                              Positive = system owes specialist
│                              Negative = specialist is ahead
└── last_updated: datetime   — Timestamp of last deficit update

CaseItem
├── id: str                  — Unique case identifier
└── level: int?              — Classification level (optional, not used by the engine)

EscalationEvent
├── case_id: str             — The case being escalated
├── source_code: str         — Specialist who escalates away
└── target_code: str         — Specialist who receives the escalation
```

### 6.2 Output

```
DispatchReport
├── assigned: list[AssignmentResult]
│   ├── case_id: str
│   ├── specialist_code: str
│   ├── new_deficit: Decimal
│   ├── new_cases_assigned: int
│   └── new_expected: Decimal
└── queued: list[str]        — Case IDs with no available pool
```

---

## 7. Usage

```python
from wdd import WorkloadEngine, PoolMember, CaseItem, EscalationEvent
from decimal import Decimal
from datetime import datetime

# --- Assignment ---
pool = [
    PoolMember(code="SP-01", load_percentage=60,   cases_assigned=5,
               deficit=Decimal("0.40"), last_updated=datetime(2026, 4, 27, 8, 0)),
    PoolMember(code="SP-02", load_percentage=None,  cases_assigned=3,
               deficit=Decimal("-0.20"), last_updated=datetime(2026, 4, 27, 9, 0)),
]

cases = [
    CaseItem(id="CONV-100", level=1),
    CaseItem(id="CONV-101", level=1),
    CaseItem(id="CONV-102", level=1),
]

report = WorkloadEngine.assign(pool, cases)

for a in report.assigned:
    print(f"{a.case_id} → {a.specialist_code}  (deficit: {a.new_deficit})")

# --- Escalation ---
WorkloadEngine.escalate(pool, EscalationEvent(
    case_id="CONV-100",
    source_code="SP-01",
    target_code="SP-02",
))
# SP-01.deficit += 1 (system owes them more)
# SP-02.deficit -= 1 (they took on extra work)
```

---

## 8. Integration

The engine is designed as a standalone component. Integration with a persistence layer (database, file system, API) is the responsibility of an external adapter. The adapter must:

1. **Read** the current pool state and unassigned cases from the data source.
2. **Convert** domain entities to `PoolMember` and `CaseItem` instances.
   - Note: if the DB stores `balance = assigned - expected`, the adapter must flip the sign: `deficit = -balance`.
3. **Invoke** `WorkloadEngine.assign(pool, cases)`.
4. **Persist** each `AssignmentResult` from the returned `DispatchReport` back to the data source.
5. **For escalations**: call `WorkloadEngine.escalate(pool, event)` and persist the updated deficit values.

The engine performs no I/O, manages no connections, and holds no state between invocations.

---

## 9. Boundary Conditions

| Condition | Behavior |
|-----------|----------|
| Empty case list | Returns an empty `DispatchReport` (no assignments, no queued). |
| Empty pool | All cases are placed in `queued`. No assignments are made. |
| Single pool member | All cases are assigned to that member regardless of load percentage. |
| All load percentages fixed and sum > 100 | Auto-split members receive 0%. Fixed members retain their values. |
| All load percentages null | All members receive `100 / pool_size` percent each. |
| All members at zero deficit | Tiebreak by `last_updated`; the least recently updated member is selected first. |
| Escalation with unknown specialist | Raises `ValueError`. |
