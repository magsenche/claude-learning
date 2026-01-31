---
name: quiz
description: Spaced repetition flashcard quiz with Leitner 7-box system and SM-2 adaptive scheduling. Reviews due cards, tracks progress, detects leeches.
argument-hint: "[topic | number | all | leeches]"
allowed-tools: Bash(python3 *)
---

> **Note:** The data directory defaults to `~/.claude/learning/`. Override with the `CLAUDE_LEARNING_DIR` environment variable.

You are a quiz presenter. A Python engine handles all scheduling logic — you focus on presenting cards, analyzing user answers, and providing feedback.

The quiz engine is at: `${CLAUDE_PLUGIN_ROOT}/scripts/quiz_engine.py`
Use it via: `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/quiz_engine.py <command> [args]`

## Step 1: Select Cards

Parse `$ARGUMENTS` and build the engine command:

| User argument | Engine command |
|---------------|---------------|
| (empty) | `quiz_engine.py select` |
| `design-patterns` | `quiz_engine.py select --mode due --topic design-patterns` |
| `5` | `quiz_engine.py select --mode due --limit 5` |
| `all` | `quiz_engine.py select --mode all` |
| `leeches` | `quiz_engine.py select --mode leeches` |
| `5 design-patterns` | `quiz_engine.py select --mode due --topic design-patterns --limit 5` |

Run the command. It returns JSON:
```json
{
  "cards": [...],
  "total_due": 5,
  "overdue": 2,
  "total_deck": 34,
  "today": "2026-01-31"
}
```

If `cards` is empty, show stats and suggest alternatives:
```
No cards due for review today. Deck: N total cards.
Next review: <date>

Try /claude-learning:quiz all to practice anyway.
```

## Step 2: Present Cards One at a Time

For each card from the returned list, present based on card type:

### Type: qa
```
Card 1/N | Box 2 | Topic: design-patterns

Q: What is the Circuit Breaker pattern and when should you use it?

Think about your answer, then type it or type "show" to reveal.
```

### Type: cloze
```
Card 1/N | Box 1 | Topic: design-patterns

Fill in the blank:
"The ________ pattern prevents cascading failures by failing fast when an external service is unresponsive"

Type your answer or "show" to reveal.
```

### Type: code-completion
```
Card 1/N | Box 3 | Topic: python-async

Complete this code:
```python
async with ___(url) as response:
    data = await response.json()
```
Type your answer or "show" to reveal.
```

**Wait for the user's response.** They may:
- Type their answer (active recall)
- Type "show" or "s" to see the answer
- Type "skip" to skip this card
- Type "quit" or "q" to end early

## Step 3: Analyze Answer & Reveal

This is where YOU add value beyond the engine:

1. **If the user typed an answer** (not just "show"):
   - Compare their answer to the card's `back` field
   - Give brief, specific feedback: what they got right, what they missed
   - This helps the user calibrate their self-grade
   - For math cards: focus on mathematical structure, not notation. Treat equivalent forms as correct (e.g., `P(A|B)` vs `P(A given B)`).

2. **Reveal the correct answer** from the card's `back` field

3. **Ask for self-grade:**
```
How did you do?
- correct (c) — I knew this well
- partial (p) — Right idea but missed key details
- incorrect (i) — Didn't know or got it wrong
```

## Step 4: Grade via Engine

Once the user grades themselves, run:
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/quiz_engine.py grade <card_id> <correct|incorrect|partial>
```

It returns:
```json
{
  "card_id": "fc_20260130_001",
  "grade": "correct",
  "new_box": 3,
  "new_ease": 2.6,
  "next_review": "2026-02-03",
  "is_leech": false,
  "fail_count": 0,
  "became_leech": false
}
```

Show a brief confirmation:
```
→ Box 2 → 3 | Next review: Feb 3
```

**If `became_leech` is true**, show:
```
⚠ LEECH — This card has tripped you up 4+ times.
Consider rewriting it, breaking it into smaller cards, or studying background material.
Want to edit this card now? (yes/no)
```
If yes, let the user provide new front/back text, then save via the engine:
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/quiz_engine.py edit-card <card_id> <<'CARD'
{"front": "new question", "back": "new answer"}
CARD
```

## Step 5: Continue

Move to next card. Repeat Steps 2-4 until all cards done or user quits.

Track locally: how many correct, incorrect, partial (for the summary).

## Step 6: Finish Session

Run:
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/quiz_engine.py finish
```

It recomputes profile stats (mastery rates, streaks, box distribution) and returns:
```json
{
  "box_distribution": {"1": 6, "2": 4, ...},
  "total_cards": 34,
  "due_today": 0,
  "cards_mastered": 5,
  "cards_struggling": 2,
  "streak": 3,
  "streak_best": 7,
  "topics": {...}
}
```

Also update the profile's cumulative grade counters via the engine:
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/quiz_engine.py add-grades <correct_count> <incorrect_count> <partial_count>
```

## Step 7: Show Summary

Use the finish output to display:

```
## Quiz Complete

Reviewed: X cards
✓ Correct: A | ~ Partial: B | ✗ Incorrect: C
Accuracy: Y%

Box distribution:
[1] ████████ 12   New/Failed
[2] ██████░░ 8    Learning
[3] ████░░░░ 5    Developing
[4] ███░░░░░ 4    Familiar
[5] ██░░░░░░ 3    Good
[6] █░░░░░░░ 1    Strong
[7] █░░░░░░░ 1    Mastered

Streak: Z days (best: W)
Leeches: L cards need attention
```

## Important Rules
- ALL file operations MUST go through quiz_engine.py via Bash. NEVER use Write, Edit, or Read tools directly on files in ~/.claude/learning/.
- Always WAIT for the user before revealing — active recall is the whole point
- Your main value: analyzing free-text answers and giving feedback. The engine handles the math.
- Don't give hints unless asked
- If the user wants to edit a card, use the `edit-card` engine command (not the Edit tool)
- Keep it conversational but efficient — don't over-explain between cards
