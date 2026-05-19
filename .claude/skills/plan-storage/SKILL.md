---
name: plan-storage
description: Defines how implementation plans are stored, approved, and retained in the repository. Use when creating or updating a plan file.
---

## When To Use

Use this skill when:

- creating a new plan file after planner output
- updating an existing plan file when scope changes materially
- updating plan status (approved, implemented, superseded)
- committing a plan file alongside implementation work

## Rules

- Store implementation plans in `docs/plans/`.
- One task gets one primary plan file unless the task is intentionally split.
- Use a stable filename: `YYYY-MM-DD-short-task-name.md`.
- The date in the filename is the planning date, not the deploy date.
- The plan file is created or updated after planner output and before coding starts.
- The orchestrator shows the plan summary to the user, but the repository file is the durable source of truth.
- After user approval, the plan file becomes part of the execution contract for implementer, reviewer, and security review.
- After implementation and doc updates are done, update the plan status to `implemented`.
- If implementation scope changes materially, update the same plan file and get renewed approval before continuing.
- Do not delete the plan file after implementation. Keep it as project history.
- Commit the approved plan file in the same branch and final commit set as the implementation unless the task is explicitly abandoned.

## Minimum Sections

- Title
- Status
- Source task or spec
- Scope
- Out of scope
- Acceptance criteria
- Impacted files or modules
- Risks
- Agent decisions
- Approval log

## Status Values

- `draft`
- `approved`
- `implemented`
- `superseded`
