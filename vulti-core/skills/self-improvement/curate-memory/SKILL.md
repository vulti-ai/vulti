---
name: curate-memory
description: Scheduled memory curation — review all memory stores, decay old noise, strengthen signal, consolidate duplicates
version: 1.0.0
metadata:
  vulti:
    tags: [memory, curation, maintenance, self-improvement]
    related_skills: [reflect]
---

# Curate Memory

A maintenance pass over all persistent memory. Designed to run as a scheduled cron job (daily) or manually when memory feels cluttered. The goal: maximize signal-to-noise ratio within the bounded memory budget.

## Philosophy

Memory is a scarce resource (~2,200 chars for MEMORY.md, ~1,375 chars for USER.md). Every entry competes for space. The curation pass acts like a gardener: prune what's dead, strengthen what's growing, pull weeds.

**Important beats recent.** A correction the user gave three weeks ago that prevents a recurring mistake is worth more than yesterday's environment detail. Small details decay. Patterns and preferences persist.

## Process

### Step 1: Read everything

Read the current state of:
- `MEMORY.md` (agent notes — environment, conventions, learnings)
- `USER.md` (user profile — identity, preferences, communication style)

Use the `memory` tool with `action="read"` or read the files directly if available.

### Step 2: Score each entry

For every entry, evaluate on two axes:

**Importance** (would this change how I respond in a future session?):
- **High**: Corrections, strong preferences, recurring patterns, identity-level traits, active project context
- **Medium**: Useful facts, environment details, workflow notes
- **Low**: One-off details, stale project context, things easily re-discovered

**Freshness** (is this still true and relevant?):
- **Current**: Still accurate, actively relevant
- **Aging**: Probably still true but context may have shifted
- **Stale**: Project finished, tool changed, preference superseded

### Step 3: Apply decay rules

| Importance | Freshness | Action |
|-----------|-----------|--------|
| High | Current | Keep. Strengthen wording if vague. |
| High | Aging | Keep. Verify if possible (session_search). |
| High | Stale | Remove only if clearly superseded. |
| Medium | Current | Keep. |
| Medium | Aging | Candidate for removal if space needed. |
| Medium | Stale | Remove. |
| Low | Current | Keep only if space allows. |
| Low | Aging | Remove. |
| Low | Stale | Remove. |

### Step 4: Consolidate

- **Merge duplicates**: If two entries say similar things, combine into the stronger version.
- **Promote patterns**: If multiple episodic memories point to the same underlying preference, extract the preference into USER.md and remove the individual memories.
- **Tighten language**: Replace verbose entries with tighter versions. Every character counts.
- **Resolve contradictions**: If entries conflict, keep the more recent one.

### Step 5: Rebalance

Check the usage percentage of each store:
- If USER.md is nearly full but has low-importance entries while high-importance insights are missing, make room.
- If MEMORY.md is full of stale project details, clear them for fresh learnings.
- Soul-level insights (USER.md) are more durable and valuable per-character than episodic memories (MEMORY.md). Prioritize user understanding.

### Step 6: Execute changes

Use the `memory` tool to apply all changes:
- `remove` stale/low-value entries
- `replace` entries that need tightening or updating
- `add` any promoted/consolidated entries

Do removals first to free space, then replacements, then additions.

### Step 7: Report

Briefly summarize what changed:
- Entries removed (and why)
- Entries updated (and what changed)
- Entries promoted (episodic → preference)
- Current usage after curation
- Any observations about memory health (e.g., "USER.md is underpopulated — future reflect passes should focus on user understanding")

## Rules

- Never delete a correction/feedback entry unless it's been clearly superseded by a newer one. These are the highest-value memories.
- Don't be afraid to delete. Noisy memory is worse than empty memory — it dilutes the signal that actually matters.
- When in doubt about an entry: "Would losing this change how I respond next session?" If no, delete.
- Don't fabricate entries. Only work with what exists.
- If both stores are healthy and balanced, it's fine to report "Nothing to change" and exit.
