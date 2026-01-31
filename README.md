# claude-learning

A Claude Code plugin that turns your AI-assisted coding sessions into lasting knowledge. It automatically extracts learning opportunities from session transcripts and builds a spaced-repetition flashcard deck with Leitner 7-box scheduling and SM-2 adaptive ease factors.

## Features

| Skill | Description |
|-------|-------------|
| `/claude-learning:recap` | Analyze today's sessions, identify learning opportunities, generate flashcards |
| `/claude-learning:quiz` | Spaced-repetition quiz with active recall and self-grading |
| `/claude-learning:stats` | Quick snapshot of deck size, box distribution, streaks, mastery |
| `/claude-learning:weekly` | Weekly progress digest with mastery trends and suggested focus |
| `/claude-learning:export` | Export cards to Markdown, JSON, Anki TSV, or Notion |
| `SessionEnd` hook | Automatically summarizes each session into structured JSONL |

## Installation

### Via plugin marketplace (recommended)

Add the marketplace and install:

```
/plugin marketplace add magsenche/claude-learning
/plugin install claude-learning@magsenche-claude-learning
```

The plugin persists across sessions — no flags needed on subsequent launches.

To update later:

```
/plugin update claude-learning@magsenche-claude-learning
```

### Manual (development)

```bash
git clone https://github.com/magsenche/claude-learning.git ~/code/claude-learning
claude --plugin-dir ~/code/claude-learning
```

## Configuration

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `CLAUDE_LEARNING_DIR` | `~/.claude/learning` | Override the data directory |
| `CLAUDE_LEARNING_DEBUG` | *(off)* | Set to `1` to enable debug logging in the SessionEnd hook |

Example:

```bash
export CLAUDE_LEARNING_DIR=/path/to/custom/dir
export CLAUDE_LEARNING_DEBUG=1
```

## Data Storage

All data lives in the learning directory (default `~/.claude/learning/`):

| File | Purpose |
|------|---------|
| `flashcards.json` | Flashcard deck with scheduling metadata |
| `profile.json` | Learner profile — topic mastery, streaks, stats |
| `sessions/<YYYY-MM-DD>.jsonl` | Daily session summaries (one JSON line per session) |
| `exports/` | Exported flashcard files (Markdown, JSON, TSV) |
| `hook-debug.log` | Debug log (only written when `CLAUDE_LEARNING_DEBUG=1`) |

## Skills Reference

### recap `[date]`

Analyzes session summaries for the given date (default: today), identifies learning opportunities across four categories (technologies, design patterns, best practices, algorithms), and generates flashcards interactively.

### quiz `[topic | number | all | leeches]`

Presents due flashcards one at a time with active recall. Accepts a topic filter, card count limit, `all` to review the full deck, or `leeches` to focus on struggling cards.

### stats

Displays deck overview, box distribution, streaks, accuracy, and strongest/weakest topics. Read-only.

### weekly

Generates a weekly digest covering mastery trends, new leeches, knowledge gaps, and suggested focus areas for next week.

### export `<format> [topic]`

Exports flashcards to `markdown`, `json`, `anki` (TSV), or `notion` (requires Notion MCP server). Optionally filtered by topic.

## Troubleshooting

**Permission prompts:** All file I/O routes through `python3 quiz_engine.py`, matching the `Bash(python3 *)` pattern each skill declares. No manual permission configuration should be needed.

## License

[MIT](LICENSE)
