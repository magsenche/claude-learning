---
name: stats
description: Quick snapshot of your learning stats — card counts, box distribution, due cards, streaks, and topic mastery.
allowed-tools: Bash(python3 *)
---

You display a quick stats overview. All data comes from the quiz engine — no manual file reading needed.

## Step 1: Get Stats

Run:
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/quiz_engine.py status
```

It returns JSON with everything:
```json
{
  "total_cards": 34,
  "due_today": 5,
  "overdue": 2,
  "leeches": 2,
  "next_review_date": "2026-02-01",
  "box_distribution": {"1": 6, "2": 4, "3": 5, "4": 4, "5": 3, "6": 1, "7": 1},
  "by_type": {"qa": 20, "cloze": 10, "code-completion": 4},
  "streaks": {"quiz_current": 3, "quiz_best": 7, "recap_current": 2, "recap_best": 5},
  "stats": {"total_reviews": 234, "accuracy_rate": 0.68, "total_correct": 160, "total_incorrect": 44, "total_partial": 30},
  "strongest_topics": [...],
  "weakest_topics": [...]
}
```

## Step 2: Display

Format it nicely:

```
## Learning Stats

### Deck
Total: N cards | Due today: M | Overdue: O
Types: X qa | Y cloze | Z code-completion
Leeches: L cards need attention

### Box Distribution
[1] ████████ 12   New/Failed
[2] ██████░░ 8    Learning
[3] ████░░░░ 5    Developing
[4] ███░░░░░ 4    Familiar
[5] ██░░░░░░ 3    Good
[6] █░░░░░░░ 1    Strong
[7] █░░░░░░░ 1    Mastered

### Streaks
Quiz: X days (best: Y)
Recap: X days (best: Y)

### Accuracy
Total reviews: N | Accuracy: X%

### Strongest Topics
1. design-patterns — 73% mastery (15 cards)

### Weakest Topics
1. python-async — 25% mastery (8 cards)
```

If total_cards is 0, show:
"No flashcards yet. Run /claude-learning:recap to generate cards from your sessions."

## Rules
- Read all data through quiz_engine.py commands. Do not use the Read tool on ~/.claude/learning/ files directly.
- This is read-only — display only, no modifications
- Scale bar charts proportionally
- Skip sections with no data
- Show actionable next steps (which skill to run)
