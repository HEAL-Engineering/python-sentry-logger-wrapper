<!--
CLAUDE INSTRUCTIONS (delete this block when submitting):
- Write a brief Summary: 1-2 short paragraphs or bullet points covering key changes
- Link the ticket if the branch name contains a ticket ID (e.g., HEA-123)
- Leave the rest of the template for the user to fill out
- After creating the PR, tell the user which checklist sections they should review
-->
## Summary
<!-- One or two short paragraphs explaining the "why" and "what". Link ticket/spec if it exists. -->


## Test Plan
<!-- How can a reviewer verify this change locally or in a test environment? -->

- [ ] Repro steps listed below
- [ ] Manual testing completed
- [ ] Automated tests added/updated

**Steps to verify:**
1.

## Checklist

### Before Requesting Review
- [ ] I have read the diff end-to-end and verified it does what I expect
- [ ] I have checked for AI hallucinations (invented APIs, data, or logic that doesn't exist)
- [ ] PR has a single clear purpose (no drive-by refactors)
- [ ] Tests are included or explanation provided why not feasible
- [ ] No secrets, PII, or hardcoded credentials in code
- [ ] All Copilot/Claude comments are addressed
- [ ] CI is passing

### Visual Changes
<!-- Required if this PR has visual changes. Delete section if not applicable. -->
- [ ] Screenshots or screen recording attached below

| Before | After |
|--------|-------|
|        |       |

### Critical Path Changes
<!-- Required if this PR touches auth, payments, data pipelines, or other critical flows. -->
- [ ] E2E/integration checks listed and executed
- [ ] Feature flag or incremental rollout plan in place

### Database Changes
<!-- Required if this PR includes database schema changes or migrations. Delete section if not applicable. -->
- [ ] No database model changes in this PR
- [ ] Migration file generated and included
- [ ] Migration file reviewed manually (autogenerate is a DRAFT, not finished code)
- [ ] Migration tested locally (upgrade, downgrade, re-upgrade)
- [ ] Migration is backward-compatible (no column renames as drop+add)
- [ ] Rollback plan documented (downgrade works correctly)
- [ ] If enum/constraint values changed: manual migration written (autogenerate can't detect these)

### Environment / Config Changes
<!-- Required if this PR adds or modifies environment variables, config files, or secrets. Delete section if not applicable. -->
- [ ] New environment variables documented below
- [ ] 1Password items created/updated (if secrets)
- [ ] Config changes communicated to team

| Variable | Description | Where to add |
|----------|-------------|--------------|
|          |             |              |

---
**Reminder:** Move this PR out of draft and tag reviewers only when all applicable items above are checked.
