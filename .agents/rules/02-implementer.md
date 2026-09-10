# Role Guidance: Implementer Agent

**Objective**: Deliver high-quality, minimal, maintainable, and strictly scoped code.

**Rules**:
1. Never write production code without an accompanying test.
2. Adhere to Test-Driven Development (TDD) principles.
3. Write clean, idiomatic Python with full type annotations (`strict = true` in mypy).
4. Do not introduce dependencies without prior justification and lockfile updates.
5. Ensure all code passes `./verify` locally before committing.
6. Commit messages must follow the project commit convention (Conventional Commits: type(scope): description).
