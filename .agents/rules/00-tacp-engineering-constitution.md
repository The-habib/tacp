# TACP Agent Master Rule: Engineering Constitution

All AI agents working on this codebase must strictly observe these core rules at all times:

1. READ BEFORE CHANGING:
   - Read `docs/00-PROJECT-CONSTITUTION.md`.
   - Read `docs/01-PRD.md` before implementing features.
   - Read `docs/02-ARCHITECTURE.md` before touching architecture.
   - Inspect existing files before editing them.

2. BOUNDARY & DISCIPLINE:
   - Make small, atomic, coherent, and explainable changes.
   - Never disable, delete, or skip failing tests.
   - Never weaken security, assertions, or sandboxes to make tests green.
   - Never expose real tokens, passwords, private keys, or credentials.
   - Never modify your own governance rules (`.agents/rules/`) or CI configs to bypass checks.

3. VERIFICATION & TRUTH:
   - Never declare work "verified" without running `./verify` and checking output.
   - Distinguish strictly between facts verified by test execution and AI assumptions.
   - Stop and ask when requirements conflict materially.
   - Add regression tests whenever fixing a bug.
   - Keep changes strictly inside the requested task scope.
