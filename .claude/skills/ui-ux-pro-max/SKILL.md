---
name: ui-ux-pro-max
description: >-
  UI and UX design guidance for the Warehouse web UI. Use for visual direction,
  interaction quality, responsive behavior, accessibility checks, and UI review.
---

# UI/UX Pro Max

Use this skill when a task changes how the interface looks, feels, behaves, or is reviewed for UX quality.

## Use For

- page and component design direction
- spacing, hierarchy, typography, and visual consistency
- interaction states, feedback, and perceived quality
- responsive behavior and mobile fit
- accessibility review for contrast, focus, labels, and touch targets
- UI review criteria before implementation is accepted

## Required Outcomes

- one clear visual direction per task
- explicit interaction expectations for loading, empty, error, hover, active, and disabled states when relevant
- responsive expectations for narrow and wide layouts
- accessibility constraints that are concrete enough to verify in review
- no accidental redesign beyond the approved scope

## Critical Checks

- contrast must stay readable
- focus states must stay visible
- icon-only controls must have labels
- touch targets must not be too small
- layout must not break on smaller screens
- motion must support clarity, not decoration only

## Working Rules

- give implementation-ready guidance to `implementer`
- review the delivered UI against the approved design direction
- prefer targeted improvement over vague aesthetic feedback
- call out weak hierarchy, inconsistent spacing, poor affordance, and inaccessible states directly
- do not take ownership of backend behavior or data contracts
