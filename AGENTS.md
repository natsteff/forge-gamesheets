# Repository guidance for coding agents

Read `PROJECT_PLAN.md` before making product or architecture changes.

## Working rules

- Work only on the requested milestone; do not pull later phases forward.
- Preserve the filesystem-as-source-of-truth rule.
- Never commit real PDFs, databases, credentials, or local runtime data.
- Add or update tests with each behavior change.
- Keep commits focused and small. Do not combine formatting or unrelated cleanup
  with a feature or fix.
- Prefer simple server-rendered functionality until the plan is intentionally
  changed.
- Treat paths and user-controlled filenames as untrusted input.
- Use `compose.yml`; do not introduce alternate Compose filenames.
- Do not deploy to production unless explicitly requested.

## Before finishing a change

Run the narrow relevant tests, then the full test suite and lint checks when
available. Summarize what changed, what was verified, and any remaining gap.
