ROLE

You are acting as a senior systems architect and CLI platform designer.

You are designing a reusable, shared command-line interface (CLI) framework that will be extracted from an existing Python repository and turned into a standalone package named `cli-root-yo`.

This package will be pip-installable and used as a dependency by multiple downstream repositories, which will extend it with repo-specific commands while preserving a unified interface, behavior, and user experience.

This is a SPECIFICATION task, not an implementation task.

Your output will be handed verbatim to another model (Claude 4.6 via VS Code + Augment) to implement.  
Therefore ambiguity, stylistic suggestion, or open-ended design language is NOT acceptable.

---

CONTEXT

- There exists an existing Python repository (`zebra_day`) containing a CLI with a consistent interaction pattern.
- That CLI behavior must be extracted into a new reusable package: `cli-root-yo`.
- `zebra_day` and future repositories will:
  - `pip install cli-root-yo`
  - extend it with additional commands
  - retain identical look, feel, semantics, and ergonomics

The CLI is intended to be:
- Used interactively by humans
- Used from scripts
- Invoked from bash and zsh
- Supported on macOS and Ubuntu
- Run in environments where Python is available, but environment managers vary

---

HARD REQUIREMENTS (MANDATORY)

1. This is a **normative specification**, not prose discussion.
2. Every behavior must be defined precisely.
3. No “may”, “could”, “typically”, or “for example” language.
4. If a design choice is made, it must be justified briefly and locked.
5. If something is intentionally left flexible, that flexibility must be explicitly scoped.
6. No implementation code.
7. No references to external frameworks unless mandated by the spec.
8. Assume Claude 4.6 will follow this spec literally.

---

PRIMARY OBJECTIVE

Produce a complete design specification for `cli-root-yo` that:

- Extracts shared CLI behavior from `zebra_day`
- Defines a stable, reusable CLI core
- Allows downstream repositories to extend commands without altering core UX
- Enables migration of additional repositories later with minimal friction

---

DELIVERABLE STRUCTURE (MUST FOLLOW EXACTLY)

### 1. Scope and Non-Goals
- Explicitly define what `cli-root-yo` is responsible for
- Explicitly define what it must never do

### 2. CLI Contract (User-Facing)
Define, in exact terms:
- Invocation pattern
- Command grammar (noun/verb or equivalent)
- Global flags
- Help behavior
- Version reporting
- Exit codes
- STDOUT vs STDERR rules
- Machine-readable vs human-readable output guarantees
- Shell-safety requirements

This section defines the immutable “feel” of the CLI.

### 3. Core Architecture (Library-Facing)
Define:
- Core modules and responsibilities
- How command discovery works
- How commands are registered
- How shared flags and config are injected
- What downstream repos are allowed to override vs forbidden to override

### 4. Extension Model for Downstream Repositories
Define:
- How a downstream repo adds commands
- Namespacing rules
- Conflict resolution rules
- Help text merging rules
- Version compatibility expectations
- How downstream repos pin or adapt to `cli-root-yo` versions

### 5. Packaging and Installation Contract
Define:
- Python version floor
- Packaging format
- Entry point strategy
- Editable vs released install expectations
- OS assumptions
- Shell assumptions

### 6. UX Invariants
Define non-negotiable UX rules:
- Color usage
- Output formatting
- Error style and phrasing
- Verbosity levels
- Progress reporting
- Determinism guarantees

### 7. Migration Plan from `zebra_day`
Define:
- What logic must move to `cli-root-yo`
- What remains local to `zebra_day`
- Steps to migrate without breaking users
- Rules for validating behavioral equivalence

### 8. Explicit “DO NOT CHANGE” Rules
List behaviors that Claude 4.6 must not reinterpret, simplify, or redesign.

### 9. Open Questions (If Any)
Only include if truly unavoidable.
Each question must:
- Be concrete
- Have bounded answer choices
- Not block the rest of the implementation

---

OUTPUT FORMAT

- Markdown
- Headings exactly as specified above
- Bulleted lists preferred
- No emojis
- No fluff
- No motivational language

---

SUCCESS CRITERIA

A competent engineer should be able to implement `cli-root-yo` from this document alone, and later migrate multiple repositories to it, without introducing CLI drift.

Produce the specification now.
