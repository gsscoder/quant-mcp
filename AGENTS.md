# Project Overview & AI Instructions

## Project Brief
An MCP server that gives an AI agent market vision: a catalog of available market signals and on-demand snapshots computed over them.
Read-only by design — it perceives markets, it never trades. Order execution belongs to a separate, dedicated MCP server.

## Core Technologies
Python 3.11+, MCP (FastMCP), asyncio, quant-pulse as the signal engine

## Architecture
A thin MCP surface over a `quant_pulse.Context`, exposing two tools:
- `list_signals` — the catalog: for each configured signal profile, its kind, venue, supported ops, params, result shape, and a one-line statement of what it tells. Paid once per session; the agent chooses from it
- `get_snapshot` — batch compute: N targets x M chosen signal profiles in one call, single fan-out, per-cell result-or-error so one dead symbol never blinds the rest
- Venue-agnostic: exchanges and signal profiles are declared in quant-pulse config, never hardcoded here
- Lean by default: latest values and regime fields only; full series are opt-in, to keep agent context affordable

## Maturity
- The system is currently under development
- Backward compatibility is not required when changing existing features

## Memory
The development documents are in the `memory-bank` dir — they primarily focus on specific feature implementation details

## Output
- Code: match the architectural and stylistic conventions of the existing codebase
- Language: use English for all generated artifacts and symbols by default. Content in another language is allowed only in user-facing strings, messages, and labels when the application has a single localization
- Quality: production-grade — every line will be reviewed
- Markdown: compact, no linting compliance, formatting identical to this file

### Python Code Standards
- Generate code for Python 3.12+ using modern, idiomatic syntax, favoring clarity and expressive constructs over legacy patterns
- Prefer explicit named parameters; avoid `**kwargs` except for true pass-through scenarios (e.g., decorators/adapters). If used, document all consumed keys
- Never use mutable defaults (`list`, `dict`, `set`); use `None` and initialize inside the function
- Avoid mutating input arguments unless explicitly documented or clearly indicated by the function name; otherwise return a new object
- Signal errors with specific exceptions; do not use sentinel return values (`None`, `False`, `-1`) unless explicitly required and properly typed
- Require full type annotations on all functions; only use `Optional[T]` when `None` has explicit semantic meaning, not as a generic default

## Operational Rules:
- If you're Claude Code, you may have specialized subagents available for many use cases — check `.claude/agents/` and prefer delegating to a matching one over doing the work directly
- Read files in `memory-bank` only when required by the current task; scan filenames first and read file contents only if they are relevant to the task
- Review/audit/report requests end at the report; fixing findings needs its own separate request — authorization never carries across turns
- NEVER update `AGENTS.md` without an explicit request
- NEVER modify `*.md` files in `memory-bank` (at any depth in the dir tree) without an explicit request
- NEVER initiate any codebase modifications without an explicit request
- NEVER commit changes to Git history without explicit authorization

## Guardrails
These are hard constraints, not suggestions, and they bias toward caution over speed — apply them proportionately on trivial or throwaway tasks. Where a request conflicts with a guardrail, follow the guardrail and say why.

### Before Implementing — Reason First
- Surface Uncertainty, Don't Guess Through It: When requirements are ambiguous, contradictory, or incomplete, stop and ask instead of assuming intent and proceeding silently. State assumptions explicitly; if multiple readings are viable, present them rather than picking one silently. Resolve intent up front — this is what makes autonomous execution safe afterward
- Plan Before Implementing: For non-trivial tasks, outline a brief approach before writing code so wrong directions surface early. For multi-step work, list the steps with a verification check for each

### Design & Scope — Code Minimally
- Simplicity Over Abstraction: Write the simplest solution that meets the requirements. Avoid speculative features, abstractions for single-use code, unrequested configurability, and error handling for impossible cases. If a construction could be materially shorter without losing correctness, rewrite it — ask whether a senior engineer would call it overcomplicated
- Surgical Scope: Every changed line should trace directly to the current task. Match the surrounding style even where you'd choose differently. Remove imports, variables, and comments that *your* changes made obsolete, but never modify, reformat, or delete code or comments orthogonal to the task. If you notice unrelated dead code, mention it — don't delete it

### Execution — Verify Against Goals
- Drive Toward Success Criteria: Turn the task into checkable goals and work until they're met — e.g. "add validation" → write tests for invalid inputs, then make them pass; "fix the bug" → write a failing test that reproduces it, then make it pass. When the goal is well-defined, loop and self-verify independently rather than pausing for confirmation the criteria already answer. (This is the counterpart to *Surface Uncertainty*: clarify the goal before starting; do not re-open a settled goal mid-execution)

### Collaboration — Communicate Honestly
- Honesty Over Agreement: Push back on questionable requests and defend sound technical choices instead of complying by default; avoid reflexive agreement
- Signal Confidence Level: Indicate when a solution is a best guess versus a well-established approach, so review effort can be calibrated. (Complements `Surface Uncertainty`: if you couldn't proceed at all, you ask; if you proceeded on a judgment call, you flag it)