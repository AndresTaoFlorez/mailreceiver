---
name: wdd
description: Weighted Deficit Dispatch (WDD) — Reference the algorithm specification, answer questions, modify, or debug the case assignment engine.
user_invocable: true
---

# Weighted Deficit Dispatch (WDD) Skill

You are answering questions or performing tasks related to the **Weighted Deficit Dispatch** case assignment algorithm.

## Step 1: Load the algorithm specification

Read the file `wdd/ALGORITHM.md` — this is the single source of truth for the algorithm's specification, definitions, properties, and boundary conditions.

## Step 2: Load the implementation

Read the following files to understand the current implementation:

- `wdd/engine.py` — Pure algorithm implementation (`WorkloadEngine` class)
- `wdd/models.py` — Data model (`PoolMember`, `CaseItem`, `AssignmentResult`, `DispatchReport`)
- `domain/dispatcher.py` — DB adapter that converts ORM entities to engine types and persists results

## Step 3: Respond

Use the loaded specification and implementation to:

- Answer technical questions about how the algorithm works
- Explain specific behaviors or edge cases
- Modify the algorithm if requested (update both `engine.py` AND `ALGORITHM.md` to keep them in sync)
- Debug assignment issues by tracing through the progressive drip logic
- Add new features to the engine while maintaining its isolation (no DB, no async, no I/O)

### Rules

- `ALGORITHM.md` is the canonical documentation. Any change to the algorithm logic MUST be reflected there.
- The `wdd/` package must remain a standalone component with zero external dependencies.
- `domain/dispatcher.py` is the adapter layer — it handles DB I/O, not the engine.
