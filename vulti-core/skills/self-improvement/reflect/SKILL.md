---
name: reflect
description: End-of-conversation reflection — review the session transcript and consolidate learnings into soul (user profile), memories (agent notes), and understanding (SOUL.md refinement)
version: 1.0.0
metadata:
  vulti:
    tags: [memory, reflection, self-improvement, learning]
    related_skills: [curate-memory]
---

# Reflect

Run this at the natural end of a conversation — after the real work is done, before the session closes. The goal is to extract durable signal from what just happened and persist it across three dimensions.

## The Three Dimensions

### 1. Soul → USER.md

Who the user *is*. Deep patterns, not surface preferences.

This is the slowest-changing layer. Update it when you learn something fundamental about how the user thinks, what they value, or how they want to collaborate. Not "prefers dark mode" but "thinks in systems and wants the architecture before the details." Not "uses Python" but "prototypes fast and refactors later — don't over-engineer on first pass."

Good soul entries:
- Cognitive style: how they reason, what they pay attention to
- Values: what they optimize for (speed? correctness? elegance? shipping?)
- Communication: how they want to be spoken to (terse? detailed? Socratic?)
- Corrections that reveal deep preferences, not one-off fixes
- Relationship dynamics: peer, teacher, explorer — how they use you

Bad soul entries:
- Project-specific details (that's memory)
- One-off preferences that won't generalize
- Anything derivable from their messages without inference

### 2. Memories → MEMORY.md

What happened and what you learned. Episodic, specific, time-bound.

This is the most active layer. Save things that would prevent you from making the same mistake twice or help you pick up context faster next session.

Good memory entries:
- Corrections: "User said don't use forEach in hot paths — use for-of"
- Discoveries: "This project uses a custom ORM, not SQLAlchemy"
- Decisions: "We chose approach B for auth because of X constraint"
- Environment facts: "macOS, uses kitty terminal, Node 20, Python 3.11"
- Workflow: "User prefers to see a plan before implementation"

Bad memory entries:
- Vague summaries ("had a good session about debugging")
- Things derivable from code or git history
- Completed task logs

### 3. Understanding → SOUL.md (agent identity refinement)

How you should behave based on what you've learned. This is about refining *your* voice and approach for this specific user, not about the user themselves.

Only touch SOUL.md if the conversation revealed something about how you should adjust your behavior that isn't already captured. This is rare — maybe 1 in 5 sessions. Examples:
- "This user responds well when I push back on ideas rather than agreeing"
- "Skip preamble — they read the first sentence and skim the rest"
- A tone calibration that worked particularly well

## Process

1. **Scan the conversation** for: corrections, preferences revealed, mistakes you made, things that landed well, new context, decisions, patterns.

2. **Check existing entries** — read current MEMORY.md and USER.md before writing. Don't duplicate. Update existing entries when the new info refines rather than replaces.

3. **Write updates** using the `memory` tool:
   - `memory(action="add", target="user", content="...")` for soul-level insights
   - `memory(action="add", target="memory", content="...")` for episodic memories
   - `memory(action="replace", target="...", old_text="...", content="...")` to refine existing entries
   - `memory(action="remove", target="...", old_text="...")` to clear outdated entries

4. **Respect the budget** — MEMORY.md is ~2,200 chars, USER.md is ~1,375 chars. If you're near the limit, replace weaker entries rather than trying to add. Quality over quantity.

5. **Be selective** — a typical reflection produces 1-3 updates. Some sessions produce zero. If nothing meaningful happened, say so and move on. Don't manufacture insights.

## Rules

- Lead with the strongest signal. If the user corrected you, that's almost always worth saving.
- Be specific. "User prefers concise responses" is weak. "User wants the answer first, reasoning only if asked — got frustrated when I explained before answering" is strong.
- Date-stamp episodic memories when the date matters for context.
- Never save raw conversation snippets — distill the insight.
- If memory is full, earn space by replacing the weakest existing entry, not by skipping the new one.

## When to trigger

- User says "let's wrap up", "that's all", "thanks", or conversation naturally concludes
- After a long or complex multi-turn session (5+ substantive exchanges)
- You can offer: "Want me to reflect on this session before we close?"
- The user can invoke directly: `/reflect`
