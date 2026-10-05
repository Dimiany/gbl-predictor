---
description: Run tests, create a feature branch, commit, push, and open a PR. Never pushes to main directly.
---

Carry out a full "branch + commit + PR" workflow. Follow these steps in order
and STOP if any of them fails — do not improvise around failures.

## Steps

1. **Run tests.** Execute `python -m pytest tests/ -q`. If any test fails,
   STOP and report the failure to the user. Do not commit, do not branch,
   do not push.

2. **Check for changes.** Run `git status`. If the working tree is clean
   (no modified, staged, or untracked files we would commit), tell the user
   "Nothing to commit." and STOP.

3. **Branch (if needed).** Run `git branch --show-current`.
   - If the current branch is `main`, you MUST create a feature branch
     before committing. Pick a short, descriptive name following these
     conventions:
       * Prefix: `feat/` (new feature) | `fix/` (bug) | `chore/` (housekeeping) |
         `docs/` (docs only) | `refactor/` (no behaviour change) | `test/`
       * Body: 2-5 lowercase dash-separated words describing the change
       * Examples: `chore/refresh-prediction-log`, `feat/add-rest-feature`,
         `fix/fixture-date-parsing`
     Then run `git checkout -b <branch-name>`.
   - If the current branch is anything else, STAY on it. Do not create
     another branch.

4. **Stage the files.** `git add` the relevant files. Avoid `git add -A`;
   prefer naming the files explicitly so we don't accidentally commit
   `.env`, large binaries, or unrelated junk. Skip files known to be
   sensitive (`.env`, `*.key`, anything containing the word "secret"
   or "credential" in the path).

5. **Write the commit message.** Use Conventional Commits:
   - Subject: `<type>: <short description>` (≤ 50 chars)
   - Optional body: 1-3 sentences explaining WHY (separated from subject
     by a blank line)
   - Always include the trailer:
     `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>`

6. **Commit.** Use a HEREDOC so multiline messages format correctly. Never
   use `--amend` unless the user explicitly asked.

7. **Push the branch.** Run `git push -u origin <branch-name>` on the first
   push of a new branch (the `-u` sets upstream tracking). On subsequent
   pushes to the same branch, plain `git push` is fine.

8. **Open the pull request.** Run `gh pr create --base main --head <branch-name>`
   with:
   - `--title "<commit subject>"`
   - `--body` containing:
     ```
     ## Summary
     <one-paragraph what + why, derived from the commit message>

     ## Test plan
     - [x] `python -m pytest tests/ -q` passes (verified at step 1)

     🤖 Generated with [Claude Code](https://claude.com/claude-code)
     ```
   - If `gh` is not installed or not authenticated, do NOT proceed
     silently. Tell the user to run `gh auth login` (or install `gh`
     first) and STOP.

9. **Report.** Return the PR URL to the user, along with a one-line
   summary of what's in the commit and a reminder that CI is running.

## Hard rules

- **Never** push to `main` directly. If a step's natural completion would
  do that, halt and ask the user what they want.
- **Never** force-push (`--force` / `-f`) unless explicitly asked.
- **Never** skip hooks (`--no-verify`) unless explicitly asked.
- If a pre-commit hook fails, fix the underlying issue and commit again.
  Do not paper over the failure.
- After all steps succeed, the user is left with: a clean working tree,
  a pushed feature branch, and an open PR with running CI. Anything
  short of that is incomplete.
