# AGENTS.md
Keep changes simple, correct, and consistent with the existing codebase. Prefer understanding and extending existing patterns over introducing new ones.


## Project Basics


* Python version: 3.11
* Package/tooling manager: `uv`
* Default working directory: `backend/`
* Base branch for all work: `main`


## Git Workflow


* Always branch from the latest `main`.
* Pull latest `main` before creating a new branch.
* Target `main` when creating PRs.
* Use branch names in this format: `anusman/type/short-slug`.
* use commit <type>: feat, fix, chore, perf, docs, build, revert, style, refactor, ci and test correctly while writing commit messages 
* commit message should be structured like this:

```
<type>[optional scope]: <description>

[optional body]

[optional footer(s)]
```

use gh cli 
```
gh auth switch
```
to ansuman-yral

push chnges from this username only no other username strictly


```bash
git fetch origin && git checkout -b <branch-name> origin/staging
```
Don't make any copy of code in tmp folder work in this repo only

## Commands


* Run Python commands through `uv run ...`.
* Manage dependencies using `uv`.
* Format code with `make format`.
* Lint code with `make lint`.


## Coding Principles


* Prefer small, focused changes over broad rewrites.
* Inspect nearby code first, then follow existing style, structure, and implementation patterns.
* Reuse obviously suitable existing modules before creating new ones.
* Keep code DRY, but avoid premature abstractions.
* Apply SOLID principles when they make the code easier to change, test, or reason about.
* Use design patterns only when they naturally fit the problem; do not force them.
* Prefer simple functions over classes when no state, lifecycle, or polymorphism is needed.
* Build for the current requirement unless the task clearly needs a reusable foundation.


## Architecture & Module Design


* Keep business logic out of API route handlers when it belongs in a service/helper layer.
* Use FastAPI dependency injection patterns for API routes.
* Avoid local imports used only to hide circular dependencies; fix the module design instead.
* Put environment/config constants in `app/core/config.py`.
* Keep modules cohesive: one module should have one clear reason to change.
* Do not duplicate logic across routes, services, or tools when an existing utility can be extended cleanly.


## Python Style


* Use type hints for function signatures and important intermediate structures.
* Avoid duck typing when a concrete model/type is known.
* Trust known Pydantic/dataclass/domain models; do not add unnecessary `hasattr` or `isinstance` checks.
* Use dataclasses for simple structured data without runtime validation needs.
* Use Pydantic models when runtime validation, parsing, or API boundaries are involved.
* Use comprehensions and `itertools` only when they improve clarity.
* Prefer clear names over comments.
* Add comments only for non-obvious business rules, constraints, or tradeoffs.


## Error Handling


* Fail fast for programmer errors and invalid assumptions.
* Avoid broad `try/except` blocks.
* Do not swallow errors with warnings when the operation should fail.
* Handle expected external failures explicitly at the boundary: network calls, user input, file I/O, database operations, and third-party APIs.


## Agent Behavior


* Do not modify unrelated input/output behavior
* Keep variable, functions nomenclature descriptive, but also not too long
* If multiple valid designs exist, choose the one most consistent with the current repository.
* Make minimal, precise code changes. Add new code only when it has one clear purpose and replaces duplication or isolates the confirmation behavior.
* If implementation reveals a decision not covered in the provided plan or in the user prompt, pause and ask the user before choosing. Include the optimal recommended option.
* If the codebase has a surprising pattern or unclear convention, mention it in the final response instead of silently inventing a new pattern. Don't swallow anomaly in code silently.

## Sub-Agent Delegation

* Execute Targeted Searches:Deploy a `5.4` model sub-agent (medium reasoning) for all internet research. You must provide the sub-agent with the exact search query and your specific objective. The sub-agent will extract and return only the precise answer.
* Preserve Context Window: You must delegate all large web-reading operations to a sub-agent. Do not process massive web payloads in your primary context.