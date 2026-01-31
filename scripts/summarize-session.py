#!/usr/bin/env python3
"""
SessionEnd hook script for claude-learning plugin.

Reads a Claude Code session transcript (JSONL) and extracts a compact
structured summary of learning-relevant information. Appends the summary
to a daily session index file under the learning data directory
(default: ~/.claude/learning/sessions/YYYY-MM-DD.jsonl).

Set CLAUDE_LEARNING_DIR to override the data directory.
Set CLAUDE_LEARNING_DEBUG=1 to enable debug logging.

Input: JSON via stdin from Claude Code SessionEnd hook
Output: Appends one JSON line to the daily session index

Python 3, stdlib only — no external dependencies.
"""

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_default_dir = Path.home() / ".claude" / "learning"
LEARNING_DIR = Path(os.environ["CLAUDE_LEARNING_DIR"]) if os.environ.get("CLAUDE_LEARNING_DIR") else _default_dir
SESSIONS_DIR = LEARNING_DIR / "sessions"

DEBUG = os.environ.get("CLAUDE_LEARNING_DEBUG", "") == "1"

# Minimum length for assistant text to be considered an "explanation"
MIN_EXPLANATION_LENGTH = 120

# Max number of user prompts / explanations to keep (avoid huge summaries)
MAX_USER_PROMPTS = 30
MAX_EXPLANATIONS = 15
MAX_ERRORS = 10

# Common technology / framework patterns to detect in code and text
# Covers languages, frameworks, libraries, tools
TECH_PATTERNS = [
    # Python
    r"\bfastapi\b", r"\bflask\b", r"\bdjango\b", r"\bpydantic\b",
    r"\bsqlalchemy\b", r"\balembic\b", r"\bcelery\b", r"\bpytest\b",
    r"\bnumpy\b", r"\bpandas\b", r"\bscikit-learn\b", r"\btensorflow\b",
    r"\bpytorch\b", r"\btorch\b", r"\bkeras\b", r"\bhuggingface\b",
    r"\btransformers\b", r"\blangchain\b", r"\blangsmith\b",
    r"\buvicorn\b", r"\bgunicorn\b", r"\bhttpx\b", r"\baiohttp\b",
    r"\basyncio\b", r"\btyping\b", r"\bmypy\b", r"\bruff\b",
    r"\bpolars\b", r"\bdask\b", r"\bray\b", r"\bmlflow\b",
    r"\bstreamlit\b", r"\bgradio\b", r"\bbeautifulsoup\b",
    # JavaScript / TypeScript
    r"\breact\b", r"\bnext\.?js\b", r"\bnuxt\b", r"\bvue\b",
    r"\bangular\b", r"\bsvelte\b", r"\bexpress\b", r"\bnestjs\b",
    r"\btailwindcss\b", r"\btailwind\b", r"\bprisma\b", r"\bdrizzle\b",
    r"\btypeorm\b", r"\bsequelize\b", r"\bmongoose\b",
    r"\bwebpack\b", r"\bvite\b", r"\besbuild\b", r"\brollup\b",
    r"\bjest\b", r"\bvitest\b", r"\bcypress\b", r"\bplaywright\b",
    r"\bzod\b", r"\btrpc\b", r"\btanstack\b", r"\bswr\b",
    r"\bredux\b", r"\bzustand\b", r"\bjotai\b",
    # Databases
    r"\bpostgresql?\b", r"\bmysql\b", r"\bsqlite\b", r"\bmongodb\b",
    r"\bredis\b", r"\belasticsearch\b", r"\bneo4j\b", r"\bcassandra\b",
    r"\bsupabase\b", r"\bfirebase\b", r"\bdynamodb\b",
    r"\bpinecone\b", r"\bchromadb\b", r"\bweaviate\b", r"\bqdrant\b",
    # Infrastructure / DevOps
    r"\bdocker\b", r"\bkubernetes\b", r"\bk8s\b", r"\bterraform\b",
    r"\bansible\b", r"\bnginx\b", r"\bcaddy\b",
    r"\baws\b", r"\bgcp\b", r"\bazure\b", r"\bvercel\b",
    r"\bcloudflare\b", r"\bheroku\b",
    r"\bgithub.actions\b", r"\bci.?cd\b",
    # Languages (only when they appear as topic, not noise)
    r"\btypescript\b", r"\brusht\b", r"\bgolang\b", r"\bzig\b",
    r"\belixir\b", r"\bswift\b", r"\bkotlin\b",
    # AI/ML specific
    r"\bopenai\b", r"\banthropic\b", r"\bclaude\b", r"\bgpt-?\d\b",
    r"\bllm\b", r"\brag\b", r"\bembedding\b", r"\bfine.?tun\w*\b",
    r"\bprompt.?engineer\w*\b", r"\bvector.?database\b",
    r"\bsemantic.?search\b", r"\bagent\b",
    # General patterns
    r"\bwebsocket\b", r"\bgrpc\b", r"\bgraphql\b", r"\brest.?api\b",
    r"\boauth\b", r"\bjwt\b", r"\bcors\b",
    r"\bmicroservic\w*\b", r"\bevent.?sourc\w*\b", r"\bcqrs\b",
    r"\brate.?limit\w*\b", r"\bcircuit.?breaker\b",
]

# Compiled patterns for performance
TECH_RE = [re.compile(p, re.IGNORECASE) for p in TECH_PATTERNS]

# Import/require patterns to detect technologies from code
IMPORT_PATTERNS = [
    # Python: import X, from X import Y
    re.compile(r"^\s*(?:from|import)\s+([\w.]+)", re.MULTILINE),
    # JS/TS: import ... from 'X', require('X')
    re.compile(r"""(?:from|require)\s*\(?['"]([^'"]+)['"]""", re.MULTILINE),
    # Go: import "X"
    re.compile(r'import\s+"([^"]+)"', re.MULTILINE),
    # Rust: use X;
    re.compile(r"^\s*use\s+([\w:]+)", re.MULTILINE),
]

# Error patterns — require error keyword followed by a colon or at start of traceback
ERROR_PATTERNS = [
    # Python-style: "SomeError: message" or "SomeException: message"
    re.compile(r"\b\w+(?:Error|Exception):\s+.+"),
    # Traceback header
    re.compile(r"Traceback \(most recent call last\)"),
    # Rust-style: "error[E0123]: message"
    re.compile(r"error\[E\d+\]:\s+.+"),
    # Generic FAILED/FATAL with colon
    re.compile(r"\b(?:FAILED|FATAL|panic):\s+.+"),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def extract_text_content(content):
    """Extract plain text from a message content field.
    Content can be a string or a list of content blocks."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append(block.get("text", ""))
                elif block.get("type") == "tool_use":
                    # Include tool input for analysis
                    inp = block.get("input", {})
                    if isinstance(inp, dict):
                        for v in inp.values():
                            if isinstance(v, str):
                                parts.append(v)
                elif block.get("type") == "tool_result":
                    # Include tool result content
                    rc = block.get("content", "")
                    if isinstance(rc, str):
                        parts.append(rc)
                    elif isinstance(rc, list):
                        for rb in rc:
                            if isinstance(rb, dict) and rb.get("type") == "text":
                                parts.append(rb.get("text", ""))
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(parts)
    return str(content)


def extract_tool_info(content):
    """Extract tool names and file paths from assistant content blocks."""
    tools = {}
    files = set()
    if not isinstance(content, list):
        return tools, files
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "tool_use":
            tool_name = block.get("name", "unknown")
            tools[tool_name] = tools.get(tool_name, 0) + 1
            inp = block.get("input", {})
            if isinstance(inp, dict):
                # File paths from Read/Write/Edit/Glob
                for key in ("file_path", "path", "pattern"):
                    val = inp.get(key)
                    if isinstance(val, str) and "/" in val:
                        files.add(val)
                # Bash commands — extract for tech detection
                cmd = inp.get("command", "")
                if isinstance(cmd, str) and cmd:
                    files.add(f"[cmd] {cmd[:200]}")
    return tools, files


def detect_technologies(text):
    """Detect technology/framework mentions in text."""
    found = set()
    for pattern in TECH_RE:
        if pattern.search(text):
            # Use the pattern's string to derive a clean name
            match = pattern.search(text)
            if match:
                found.add(match.group(0).lower().strip())
    return found


def extract_imports(text):
    """Extract imported module/package names from code."""
    imports = set()
    for pattern in IMPORT_PATTERNS:
        for match in pattern.finditer(text):
            module = match.group(1).split(".")[0].split("/")[0]
            # Skip relative imports and very short names
            if module and len(module) > 1 and not module.startswith("."):
                imports.add(module.lower())
    return imports


def extract_errors(text):
    """Extract error messages from text."""
    errors = []
    for pattern in ERROR_PATTERNS:
        for match in pattern.finditer(text):
            err = match.group(0).strip()[:300]
            if err and len(err) > 10:
                errors.append(err)
    return errors


def extract_explanations(text):
    """Extract substantial explanation paragraphs from assistant text.
    These are text blocks that explain concepts (not code)."""
    explanations = []
    # Split by double newline to get paragraphs
    paragraphs = re.split(r"\n\s*\n", text)
    for para in paragraphs:
        para = para.strip()
        # Skip short paragraphs
        if len(para) < MIN_EXPLANATION_LENGTH:
            continue
        # Skip paragraphs that are mostly code (high ratio of special chars)
        code_chars = sum(1 for c in para if c in "{}()[];=<>|&$`")
        if len(para) > 0 and code_chars / len(para) > 0.08:
            continue
        # Skip if starts with common code indicators
        if para.startswith(("```", "import ", "from ", "const ", "let ", "var ",
                            "def ", "class ", "function ", "async ", "@",
                            "services:", "    ", "\t")):
            continue
        # Skip if contains too many lines that look like code (indented or special chars)
        lines = para.split("\n")
        code_lines = sum(1 for l in lines if l.startswith(("  ", "\t", "- ", "│"))
                         or re.match(r"^\s*[\w.]+\s*[:=({]", l))
        if len(lines) > 1 and code_lines / len(lines) > 0.5:
            continue
        # Keep first 500 chars of the explanation
        explanations.append(para[:500])
    return explanations


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def process_transcript(transcript_path):
    """Parse a session transcript JSONL and return structured summary."""
    user_prompts = []
    all_text = []
    all_tools = {}
    all_files = set()
    all_technologies = set()
    all_errors = []
    all_explanations = []
    user_msg_count = 0
    assistant_msg_count = 0
    total_tool_uses = 0

    try:
        with open(transcript_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue

                # Claude Code transcript format wraps messages:
                # {"type": "user"|"assistant", "message": {"role": ..., "content": ...}}
                # Also has non-message records (file-history-snapshot, summary) — skip those.
                record_type = record.get("type", "")
                if record_type in ("file-history-snapshot", "summary"):
                    continue

                # Skip meta messages (system injections like skill prompts)
                if record.get("isMeta"):
                    continue

                msg = record.get("message")
                if msg and isinstance(msg, dict):
                    role = msg.get("role", "")
                    content = msg.get("content", "")
                else:
                    # Fallback: maybe it's a flat format (role/content at top level)
                    role = record.get("role", "")
                    content = record.get("content", "")

                if not role:
                    continue

                if role == "user":
                    text = extract_text_content(content)

                    # Skip tool results (not real user input)
                    if isinstance(content, list) and all(
                        isinstance(b, dict) and b.get("type") == "tool_result"
                        for b in content if isinstance(b, dict)
                    ):
                        # Still count for stats but don't add to prompts
                        all_text.append(text)
                        continue

                    # Skip system/command messages
                    if any(tag in text for tag in (
                        "<command-name>", "<command-message>",
                        "<local-command-caveat>", "<local-command-stdout>",
                        "<tool_use_error>", "<system-reminder>",
                    )):
                        continue

                    user_msg_count += 1
                    all_text.append(text)
                    # Keep meaningful user prompts (not just "yes", "ok", etc.)
                    if len(text.strip()) > 10:
                        user_prompts.append(text.strip()[:500])

                elif role == "assistant":
                    assistant_msg_count += 1
                    text = extract_text_content(content)
                    all_text.append(text)

                    # Extract tool usage
                    tools, files = extract_tool_info(content)
                    for t, c in tools.items():
                        all_tools[t] = all_tools.get(t, 0) + c
                        total_tool_uses += c
                    all_files.update(files)

                    # Extract explanations from assistant text
                    explanations = extract_explanations(text)
                    all_explanations.extend(explanations)

    except (OSError, IOError):
        return None

    # Combine all text for technology detection
    combined_text = "\n".join(all_text)

    # Detect technologies from text mentions and imports
    all_technologies.update(detect_technologies(combined_text))
    all_technologies.update(extract_imports(combined_text))

    # Extract errors from combined text
    all_errors = extract_errors(combined_text)

    # Clean up file paths (remove [cmd] prefix commands, keep real paths)
    clean_files = set()
    for f in all_files:
        if f.startswith("[cmd] "):
            continue
        # Skip very common paths that aren't interesting
        if f.startswith("/tmp") or f.startswith("/dev"):
            continue
        clean_files.add(f)

    # Truncate lists to avoid huge summaries
    user_prompts = user_prompts[:MAX_USER_PROMPTS]
    all_explanations = all_explanations[:MAX_EXPLANATIONS]
    all_errors = list(set(all_errors))[:MAX_ERRORS]

    return {
        "user_prompts": user_prompts,
        "technologies_detected": sorted(all_technologies),
        "files_touched": sorted(clean_files),
        "tools_used": all_tools,
        "errors_encountered": all_errors,
        "key_explanations": all_explanations,
        "stats": {
            "user_messages": user_msg_count,
            "assistant_messages": assistant_msg_count,
            "total_tool_uses": total_tool_uses,
        },
    }


LOG_FILE = LEARNING_DIR / "hook-debug.log"


def debug_log(msg):
    """Write a debug line to hook-debug.log when CLAUDE_LEARNING_DEBUG=1."""
    if not DEBUG:
        return
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now(timezone.utc).isoformat()}] {msg}\n")
    except Exception:
        pass


def main():
    debug_log("SessionEnd hook fired")

    # Read hook input from stdin
    try:
        hook_input = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        debug_log("ERROR: Failed to parse stdin JSON")
        sys.exit(0)

    debug_log(f"Input keys: {list(hook_input.keys())}")

    session_id = hook_input.get("session_id", "")
    transcript_path = hook_input.get("transcript_path", "")

    debug_log(f"session_id={session_id}, transcript_path={transcript_path}")

    # Validate
    if not transcript_path or not os.path.isfile(transcript_path):
        debug_log(f"Skipping: transcript not found at {transcript_path}")
        sys.exit(0)

    debug_log(f"Transcript file exists, size={os.path.getsize(transcript_path)} bytes")

    # Process the transcript
    try:
        summary = process_transcript(transcript_path)
    except Exception as e:
        debug_log(f"ERROR in process_transcript: {e}")
        sys.exit(0)

    if summary is None:
        debug_log("Skipping: process_transcript returned None (read error)")
        sys.exit(0)

    debug_log(f"Parsed: {summary['stats']['user_messages']} user msgs, {summary['stats']['assistant_messages']} assistant msgs, {len(summary['technologies_detected'])} techs")

    # Skip sessions with no real user interaction
    if summary["stats"]["user_messages"] < 1:
        debug_log(f"Skipping: no user messages found")
        sys.exit(0)

    # Build output record — use LOCAL time for the date so it matches
    # the user's `date +%Y-%m-%d` and what /recap expects
    now = datetime.now(timezone.utc).isoformat()
    today = datetime.now().strftime("%Y-%m-%d")

    record = {
        "session_id": session_id,
        "timestamp": now,
        "transcript_path": transcript_path,
        **summary,
    }

    # Ensure output directory exists
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

    # Append to today's session index
    output_file = SESSIONS_DIR / f"{today}.jsonl"
    try:
        with open(output_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        debug_log(f"Summary written to {output_file}")
    except (OSError, IOError) as e:
        debug_log(f"ERROR writing: {e}")
        print(f"Failed to write session summary: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
