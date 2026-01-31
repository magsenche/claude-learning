---
name: export
description: Export flashcards to various formats — Markdown, JSON, Anki-compatible TSV, or Notion database.
argument-hint: "<format: markdown | json | anki | notion> [topic]"
allowed-tools: Bash(python3 *), mcp__notion__notion-search, mcp__notion__notion-fetch, mcp__notion__notion-create-database, mcp__notion__notion-create-pages, mcp__notion__notion-update-page
---

> **Note:** The data directory defaults to `~/.claude/learning/`. Override with the `CLAUDE_LEARNING_DIR` environment variable.

You are an export utility for the claude-learning flashcard system. You read the flashcard database and export it in the requested format.

The quiz engine is at: `${CLAUDE_PLUGIN_ROOT}/scripts/quiz_engine.py`
Use it via: `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/quiz_engine.py <command> [args]`

## Step 1: Parse Arguments

Parse `$ARGUMENTS` to determine:
- **Format** (required, first argument): `markdown`, `json`, `anki`, or `notion`
- **Topic filter** (optional, second argument): only export cards matching this topic

If no format is specified, show usage:
```
Usage: /claude-learning:export <format> [topic]

Formats:
  markdown  — Readable Markdown file grouped by topic
  json      — Structured JSON for custom apps/websites
  anki      — TSV file compatible with Anki import
  notion    — Create/update a Notion database with all cards

Examples:
  /claude-learning:export markdown
  /claude-learning:export anki design-patterns
  /claude-learning:export notion
```

## Step 2: Read Flashcards

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/quiz_engine.py read-file flashcards.json
```

If topic filter is provided, only include cards matching that topic.

If no cards exist, tell the user and exit.

## Step 3: Export Based on Format

### Format: markdown

Generate a readable Markdown file grouped by topic:

```markdown
# Claude Learning — Flashcard Export
Generated: YYYY-MM-DD | Total cards: N

## design-patterns (X cards)

### Circuit Breaker Pattern
**Type:** Q&A | **Box:** 3/7 | **Ease:** 2.6

**Q:** What is the Circuit Breaker pattern and when should you use it?

**A:** A stability pattern that wraps calls to external services...

**Tags:** microservices, resilience
**Created:** 2026-01-30 | **Reviews:** 5

---

### Strategy Pattern
...
```

Write via engine:
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/quiz_engine.py write-export exports/flashcards-YYYY-MM-DD.md <<'EXPORT'
<markdown content>
EXPORT
```

### Format: json

Generate structured JSON:

```json
{
  "exported_at": "2026-01-30T18:00:00Z",
  "total_cards": 42,
  "cards": [
    {
      "id": "fc_20260130_001",
      "type": "qa",
      "front": "...",
      "back": "...",
      "topic": "design-patterns",
      "tags": ["microservices"],
      "box": 3,
      "ease_factor": 2.6,
      "created": "2026-01-30",
      "review_count": 5,
      "is_leech": false
    }
  ]
}
```

Write via engine:
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/quiz_engine.py write-export exports/flashcards-YYYY-MM-DD.json <<'EXPORT'
<json content>
EXPORT
```

### Format: anki

Generate a TSV file compatible with Anki's import feature.

Format: `front\tback\ttags`

- For `qa` cards: front = question, back = answer
- For `cloze` cards: front = text with `{{c1::answer}}` Anki cloze syntax (convert from `{{answer}}` format), back = empty
- For `code-completion` cards: front = code prompt, back = completed code
- Tags: combine topic + tags with spaces (Anki tag format)

Write via engine:
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/quiz_engine.py write-export exports/flashcards-YYYY-MM-DD.tsv <<'EXPORT'
<tsv content>
EXPORT
```

Show the user how to import:
```
Exported N cards to ~/.claude/learning/exports/flashcards-YYYY-MM-DD.tsv

To import into Anki:
1. Open Anki → File → Import
2. Select the .tsv file
3. Set field separator to Tab
4. Map fields: Field 1 → Front, Field 2 → Back, Field 3 → Tags
5. Click Import
```

### Format: notion

Use the Notion MCP tools to create/update a database:

1. Search for an existing "Claude Learning Flashcards" database using `mcp__notion__notion-search`
2. If not found, create a new database using `mcp__notion__notion-create-database` with columns:
   - Front (title)
   - Back (rich text)
   - Topic (select)
   - Tags (multi-select)
   - Box (number)
   - Ease Factor (number)
   - Type (select)
   - Created (date)
   - Next Review (date)
   - Is Leech (checkbox)
3. If found, update existing pages and add new ones using `mcp__notion__notion-create-pages` and `mcp__notion__notion-update-page`

Show the user the Notion database URL when done.

If Notion MCP tools are not available, tell the user:
"Notion export requires the Notion MCP server to be configured. Use /claude-learning:export json instead and import manually."

## Step 4: Confirm

After writing, show:
```
Exported N cards to <filepath>
Format: <format>
Topic filter: <topic or "all">
```

## Important Rules
- ALL file operations MUST go through quiz_engine.py via Bash. NEVER use Write, Edit, or Read tools directly on files in ~/.claude/learning/.
- The engine's `write-export` command creates the exports/ directory automatically
- Never include internal scheduling fields (ease_factor, fail_count) in user-facing formats unless it adds value
- For Anki export, handle cloze cards specially with Anki's `{{c1::}}` syntax
- Preserve Unicode characters correctly in all formats
