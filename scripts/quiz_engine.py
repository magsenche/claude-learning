#!/usr/bin/env python3
"""
Quiz engine for claude-learning plugin.

Handles all deterministic/algorithmic quiz logic:
- Card selection (due cards, filtering, shuffling)
- Scheduling updates (Leitner box + SM-2 ease factor)
- Profile recomputation (mastery rates, streaks, stats)
- Card CRUD (add, edit)
- Grade counter updates

Usage:
  python3 quiz_engine.py select [--topic TOPIC] [--limit N] [--mode MODE]
  python3 quiz_engine.py grade <card_id> <grade>
  python3 quiz_engine.py finish
  python3 quiz_engine.py status
  python3 quiz_engine.py add-cards              # reads JSON array from stdin
  python3 quiz_engine.py edit-card <card_id>    # reads JSON {front,back,...} from stdin
  python3 quiz_engine.py add-grades <correct> <incorrect> <partial>
  python3 quiz_engine.py read-file <relative-path>   # cat a file from LEARNING_DIR
  python3 quiz_engine.py write-export <relative-path> # write stdin to LEARNING_DIR (exports only)
  python3 quiz_engine.py sessions-since [YYYY-MM-DD]  # read all sessions after date

Modes: due (default), all, leeches

All data read/written from the learning data directory (default: ~/.claude/learning/).
Set CLAUDE_LEARNING_DIR to override. Output: JSON to stdout. Python 3, stdlib only.
"""

import json
import os
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

_default_dir = Path.home() / ".claude" / "learning"
LEARNING_DIR = Path(os.environ["CLAUDE_LEARNING_DIR"]) if os.environ.get("CLAUDE_LEARNING_DIR") else _default_dir
FLASHCARDS_PATH = LEARNING_DIR / "flashcards.json"
PROFILE_PATH = LEARNING_DIR / "profile.json"

BOX_INTERVALS = {1: 1, 2: 2, 3: 4, 4: 7, 5: 14, 6: 30, 7: 60}

EASE_DEFAULT = 2.5
EASE_MAX = 3.0
EASE_MIN = 1.3
EASE_CORRECT_BONUS = 0.1
EASE_INCORRECT_PENALTY = 0.2
EASE_PARTIAL_PENALTY = 0.05
LEECH_THRESHOLD = 4
MASTERY_BOX_THRESHOLD = 5   # box >= this counts as "mastered" for topic rate
MASTERED_BOX_THRESHOLD = 6  # box >= this counts in stats.cards_mastered
RECAP_STREAK_MAX_GAP = 3    # max days between recaps before streak resets


def load_json(path):
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def today_str():
    return datetime.now().strftime("%Y-%m-%d")


def parse_date(s):
    if not s:
        return None
    try:
        return datetime.strptime(str(s), "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def select_cards(args):
    data = load_json(FLASHCARDS_PATH)
    cards = data.get("cards", []) or []

    if not cards:
        print(json.dumps({"cards": [], "message": "No flashcards yet."}))
        return

    mode, topic, limit = "due", None, None
    i = 0
    while i < len(args):
        if args[i] == "--mode" and i + 1 < len(args):
            mode = args[i + 1]; i += 2
        elif args[i] == "--topic" and i + 1 < len(args):
            topic = args[i + 1]; i += 2
        elif args[i] == "--limit" and i + 1 < len(args):
            try: limit = int(args[i + 1])
            except ValueError: pass
            i += 2
        else:
            i += 1

    today = today_str()
    today_date = parse_date(today)

    if mode == "leeches":
        selected = [c for c in cards if c.get("is_leech", False)]
    elif mode == "all":
        selected = list(cards)
    else:
        selected = [c for c in cards if parse_date(c.get("next_review"))
                    and parse_date(c.get("next_review")) <= today_date]

    if topic:
        selected = [c for c in selected if c.get("topic", "").lower() == topic.lower()]

    random.shuffle(selected)

    if limit and limit > 0:
        selected = selected[:limit]

    overdue = sum(1 for c in selected if parse_date(c.get("next_review"))
                  and parse_date(c.get("next_review")) < today_date)

    print(json.dumps({
        "cards": selected,
        "total_due": len(selected),
        "overdue": overdue,
        "total_deck": len(cards),
        "today": today,
    }, ensure_ascii=False))


def grade_card(card_id, grade):
    data = load_json(FLASHCARDS_PATH)
    cards = data.get("cards", []) or []

    card, card_idx = None, None
    for i, c in enumerate(cards):
        if c.get("id") == card_id:
            card, card_idx = c, i
            break

    if card is None:
        print(json.dumps({"error": f"Card '{card_id}' not found"}))
        sys.exit(1)

    today = today_str()
    today_date = parse_date(today)
    box = card.get("box", 1)
    ease = card.get("ease_factor", EASE_DEFAULT)
    fail_count = card.get("fail_count", 0)

    if grade == "correct":
        box = min(box + 1, 7)
        ease = min(EASE_MAX, ease + EASE_CORRECT_BONUS)
        interval = round(BOX_INTERVALS[box] * ease)
        next_review = (today_date + timedelta(days=interval)).isoformat()
    elif grade == "incorrect":
        box = 1
        ease = max(EASE_MIN, ease - EASE_INCORRECT_PENALTY)
        fail_count += 1
        next_review = (today_date + timedelta(days=1)).isoformat()
    elif grade == "partial":
        ease = max(EASE_MIN, ease - EASE_PARTIAL_PENALTY)
        interval = round(BOX_INTERVALS[box] * ease)
        next_review = (today_date + timedelta(days=interval)).isoformat()
    else:
        print(json.dumps({"error": f"Invalid grade '{grade}'. Use: correct, incorrect, partial"}))
        sys.exit(1)

    is_leech = fail_count >= LEECH_THRESHOLD

    card.update({
        "box": box, "ease_factor": round(ease, 2), "fail_count": fail_count,
        "is_leech": is_leech, "last_reviewed": today, "next_review": next_review,
        "review_count": card.get("review_count", 0) + 1,
    })
    cards[card_idx] = card
    data["cards"] = cards
    data["metadata"]["last_updated"] = today
    save_json(FLASHCARDS_PATH, data)

    print(json.dumps({
        "card_id": card_id, "grade": grade, "new_box": box,
        "new_ease": round(ease, 2), "next_review": next_review,
        "is_leech": is_leech, "fail_count": fail_count,
        "became_leech": is_leech and fail_count == LEECH_THRESHOLD,
    }))


def finish_session():
    data = load_json(FLASHCARDS_PATH)
    profile = load_json(PROFILE_PATH)
    cards = data.get("cards", []) or []
    today = today_str()
    today_date = parse_date(today)

    if not profile:
        profile = {"metadata": {}, "topics": {}, "knowledge_gaps": [],
                   "streaks": {}, "stats": {}}

    # Recompute topic stats
    topics = {}
    for card in cards:
        t = card.get("topic", "uncategorized")
        if t not in topics:
            topics[t] = {"total_cards": 0, "mastered": 0, "ease_sum": 0.0,
                         "leech_count": 0, "last_activity": None}
        topics[t]["total_cards"] += 1
        if card.get("box", 1) >= MASTERY_BOX_THRESHOLD:
            topics[t]["mastered"] += 1
        topics[t]["ease_sum"] += card.get("ease_factor", EASE_DEFAULT)
        if card.get("is_leech"):
            topics[t]["leech_count"] += 1
        lr = card.get("last_reviewed")
        if lr and (topics[t]["last_activity"] is None or lr > topics[t]["last_activity"]):
            topics[t]["last_activity"] = lr

    profile_topics = {}
    for t, s in topics.items():
        profile_topics[t] = {
            "total_cards": s["total_cards"],
            "mastery_rate": round(s["mastered"] / s["total_cards"], 2) if s["total_cards"] > 0 else 0.0,
            "avg_ease_factor": round(s["ease_sum"] / s["total_cards"], 2) if s["total_cards"] > 0 else EASE_DEFAULT,
            "leech_count": s["leech_count"],
            "last_activity": s["last_activity"],
        }
    profile["topics"] = profile_topics

    # Aggregate stats
    total_reviews = sum(c.get("review_count", 0) for c in cards)
    stats = profile.get("stats", {})
    stats["total_reviews"] = total_reviews
    stats["cards_mastered"] = sum(1 for c in cards if c.get("box", 1) >= MASTERED_BOX_THRESHOLD)
    stats["cards_struggling"] = sum(1 for c in cards if c.get("is_leech", False))
    if stats.get("total_correct", 0) + stats.get("total_incorrect", 0) + stats.get("total_partial", 0) > 0:
        total_graded = stats["total_correct"] + stats["total_incorrect"] + stats["total_partial"]
        stats["accuracy_rate"] = round(stats["total_correct"] / total_graded, 2)
    profile["stats"] = stats

    # Streaks
    streaks = profile.get("streaks", {})
    last_quiz = streaks.get("quiz_last_date")
    if last_quiz:
        diff = ((today_date - parse_date(last_quiz)).days if parse_date(last_quiz) else 999)
        if diff == 1:
            streaks["quiz_current"] = streaks.get("quiz_current", 0) + 1
        elif diff != 0:
            streaks["quiz_current"] = 1
    else:
        streaks["quiz_current"] = 1
    streaks["quiz_last_date"] = today
    streaks["quiz_best"] = max(streaks.get("quiz_best", 0), streaks.get("quiz_current", 1))
    profile["streaks"] = streaks

    # Box distribution
    box_dist = {str(i): 0 for i in range(1, 8)}
    due_today = 0
    for card in cards:
        b = card.get("box", 1)
        if 1 <= b <= 7:
            box_dist[str(b)] += 1
        nr = parse_date(card.get("next_review"))
        if nr and nr <= today_date:
            due_today += 1

    profile["metadata"]["last_updated"] = today
    if not profile.get("metadata", {}).get("created"):
        profile.setdefault("metadata", {})["created"] = today

    save_json(PROFILE_PATH, profile)

    print(json.dumps({
        "box_distribution": box_dist, "total_cards": len(cards),
        "due_today": due_today,
        "cards_mastered": stats["cards_mastered"],
        "cards_struggling": stats["cards_struggling"],
        "streak": streaks.get("quiz_current", 0),
        "streak_best": streaks.get("quiz_best", 0),
        "topics": {t: {"mastery_rate": s["mastery_rate"], "total_cards": s["total_cards"]}
                   for t, s in profile_topics.items()},
    }, ensure_ascii=False))


def status():
    data = load_json(FLASHCARDS_PATH)
    profile = load_json(PROFILE_PATH)
    cards = data.get("cards", []) or []
    today_date = parse_date(today_str())

    box_dist = {str(i): 0 for i in range(1, 8)}
    due, overdue, leeches = 0, 0, 0
    by_type = {"qa": 0, "cloze": 0, "code-completion": 0}

    for card in cards:
        b = card.get("box", 1)
        if 1 <= b <= 7:
            box_dist[str(b)] += 1
        nr = parse_date(card.get("next_review"))
        if nr and nr <= today_date:
            due += 1
        if nr and nr < today_date:
            overdue += 1
        if card.get("is_leech"):
            leeches += 1
        ct = card.get("type", "qa")
        if ct in by_type:
            by_type[ct] += 1

    next_date = None
    if due == 0:
        future = [parse_date(c.get("next_review")) for c in cards
                  if parse_date(c.get("next_review")) and parse_date(c.get("next_review")) > today_date]
        if future:
            next_date = min(future).isoformat()

    streaks = profile.get("streaks", {})
    stats = profile.get("stats", {})
    topics = profile.get("topics", {})
    topic_list = [(t, s) for t, s in topics.items() if s.get("total_cards", 0) >= 2]
    strongest = sorted(topic_list, key=lambda x: x[1].get("mastery_rate", 0), reverse=True)[:3]
    weakest = sorted(topic_list, key=lambda x: x[1].get("mastery_rate", 0))[:3]

    print(json.dumps({
        "total_cards": len(cards), "due_today": due, "overdue": overdue,
        "leeches": leeches, "next_review_date": next_date,
        "box_distribution": box_dist, "by_type": by_type,
        "streaks": {
            "quiz_current": streaks.get("quiz_current", 0),
            "quiz_best": streaks.get("quiz_best", 0),
            "recap_current": streaks.get("recap_current", 0),
            "recap_best": streaks.get("recap_best", 0),
        },
        "stats": {
            "total_reviews": stats.get("total_reviews", 0),
            "accuracy_rate": stats.get("accuracy_rate", 0.0),
            "total_correct": stats.get("total_correct", 0),
            "total_incorrect": stats.get("total_incorrect", 0),
            "total_partial": stats.get("total_partial", 0),
        },
        "strongest_topics": [{"topic": t, **s} for t, s in strongest],
        "weakest_topics": [{"topic": t, **s} for t, s in weakest],
    }, ensure_ascii=False))


def add_cards_from_stdin():
    """Read a JSON array of card objects from stdin and append to flashcards.json.

    Also recomputes profile topics and bumps the recap streak.
    """
    raw = sys.stdin.read().strip()
    if not raw:
        print(json.dumps({"error": "No input on stdin"}))
        sys.exit(1)

    new_cards = json.loads(raw)
    if not isinstance(new_cards, list):
        new_cards = [new_cards]

    data = load_json(FLASHCARDS_PATH)
    if not data:
        data = {"metadata": {"created": today_str(), "last_updated": today_str(), "total_cards": 0}, "cards": []}

    existing_ids = {c.get("id") for c in data.get("cards", [])}
    added = []
    for card in new_cards:
        if card.get("id") in existing_ids:
            continue
        data.setdefault("cards", []).append(card)
        existing_ids.add(card.get("id"))
        added.append(card.get("id"))

    data["metadata"]["last_updated"] = today_str()
    data["metadata"]["total_cards"] = len(data["cards"])
    save_json(FLASHCARDS_PATH, data)

    # Recompute profile topics and bump recap streak
    profile = load_json(PROFILE_PATH)
    if not profile:
        profile = {"metadata": {"created": today_str()}, "topics": {},
                   "knowledge_gaps": [], "streaks": {}, "stats": {}}

    # Recompute topics from all cards
    topics = {}
    for card in data["cards"]:
        t = card.get("topic", "uncategorized")
        if t not in topics:
            topics[t] = {"total_cards": 0, "mastered": 0, "ease_sum": 0.0,
                         "leech_count": 0, "last_activity": None}
        topics[t]["total_cards"] += 1
        if card.get("box", 1) >= MASTERY_BOX_THRESHOLD:
            topics[t]["mastered"] += 1
        topics[t]["ease_sum"] += card.get("ease_factor", EASE_DEFAULT)
        if card.get("is_leech"):
            topics[t]["leech_count"] += 1
        lr = card.get("last_reviewed")
        if lr and (topics[t]["last_activity"] is None or lr > topics[t]["last_activity"]):
            topics[t]["last_activity"] = lr

    profile_topics = {}
    for t, s in topics.items():
        profile_topics[t] = {
            "total_cards": s["total_cards"],
            "mastery_rate": round(s["mastered"] / s["total_cards"], 2) if s["total_cards"] > 0 else 0.0,
            "avg_ease_factor": round(s["ease_sum"] / s["total_cards"], 2) if s["total_cards"] > 0 else EASE_DEFAULT,
            "leech_count": s["leech_count"],
            "last_activity": s["last_activity"],
        }
    profile["topics"] = profile_topics

    # Bump recap streak
    today = today_str()
    today_date = parse_date(today)
    streaks = profile.get("streaks", {})
    last_recap = streaks.get("recap_last_date")
    if last_recap:
        diff = (today_date - parse_date(last_recap)).days if parse_date(last_recap) else 999
        if diff == 0:
            pass  # same day, no change
        elif diff <= RECAP_STREAK_MAX_GAP:
            streaks["recap_current"] = streaks.get("recap_current", 0) + 1
        else:
            streaks["recap_current"] = 1
    else:
        streaks["recap_current"] = 1
    streaks["recap_last_date"] = today
    streaks["recap_best"] = max(streaks.get("recap_best", 0), streaks.get("recap_current", 1))
    profile["streaks"] = streaks

    profile["metadata"]["last_updated"] = today
    save_json(PROFILE_PATH, profile)

    print(json.dumps({
        "added": len(added),
        "added_ids": added,
        "total_cards": len(data["cards"]),
        "recap_streak": streaks.get("recap_current", 1),
    }))


def edit_card_from_stdin(card_id):
    """Read JSON with updated fields from stdin and apply to the given card."""
    raw = sys.stdin.read().strip()
    if not raw:
        print(json.dumps({"error": "No input on stdin"}))
        sys.exit(1)

    updates = json.loads(raw)
    data = load_json(FLASHCARDS_PATH)
    cards = data.get("cards", [])

    card = None
    for c in cards:
        if c.get("id") == card_id:
            card = c
            break

    if card is None:
        print(json.dumps({"error": f"Card '{card_id}' not found"}))
        sys.exit(1)

    allowed_fields = {"front", "back", "topic", "tags", "type", "source_context"}
    applied = {}
    for k, v in updates.items():
        if k in allowed_fields:
            card[k] = v
            applied[k] = v

    data["metadata"]["last_updated"] = today_str()
    save_json(FLASHCARDS_PATH, data)

    print(json.dumps({"card_id": card_id, "updated_fields": list(applied.keys())}))


def add_grades(correct, incorrect, partial):
    """Add grade counts to profile.json stats."""
    profile = load_json(PROFILE_PATH)
    if not profile:
        profile = {"metadata": {"created": today_str()}, "topics": {},
                   "knowledge_gaps": [], "streaks": {}, "stats": {}}

    stats = profile.get("stats", {})
    stats["total_correct"] = stats.get("total_correct", 0) + correct
    stats["total_incorrect"] = stats.get("total_incorrect", 0) + incorrect
    stats["total_partial"] = stats.get("total_partial", 0) + partial
    total_graded = stats["total_correct"] + stats["total_incorrect"] + stats["total_partial"]
    if total_graded > 0:
        stats["accuracy_rate"] = round(stats["total_correct"] / total_graded, 2)
    profile["stats"] = stats
    profile["metadata"]["last_updated"] = today_str()
    save_json(PROFILE_PATH, profile)

    print(json.dumps({
        "total_correct": stats["total_correct"],
        "total_incorrect": stats["total_incorrect"],
        "total_partial": stats["total_partial"],
        "accuracy_rate": stats.get("accuracy_rate", 0.0),
    }))


def read_file(rel_path):
    """Read a file relative to LEARNING_DIR and print its contents."""
    safe = os.path.normpath(rel_path)
    if safe.startswith(".."):
        print(json.dumps({"error": "Path traversal not allowed"}))
        sys.exit(1)
    target = LEARNING_DIR / safe
    if not target.exists():
        print(json.dumps({"error": f"File not found: {safe}"}))
        sys.exit(1)
    print(target.read_text(encoding="utf-8"), end="")


def sessions_since(since_date_str=None):
    """Read and concatenate all session files with dates strictly after since_date_str.

    If since_date_str is None or empty, returns ALL session files.
    """
    sessions_dir = LEARNING_DIR / "sessions"
    if not sessions_dir.exists():
        print(json.dumps({"sessions": [], "files_read": [], "date_range": None}))
        return

    since_date = parse_date(since_date_str) if since_date_str else None

    session_files = []
    for f in sorted(sessions_dir.glob("*.jsonl")):
        file_date = parse_date(f.stem)
        if file_date is None:
            continue
        if since_date and file_date <= since_date:
            continue
        session_files.append((file_date, f))

    if not session_files:
        print(json.dumps({"sessions": [], "files_read": [], "date_range": None}))
        return

    session_files.sort(key=lambda x: x[0])

    all_sessions = []
    files_read = []
    for file_date, filepath in session_files:
        files_read.append(filepath.name)
        try:
            with open(filepath, "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        all_sessions.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        except (OSError, IOError):
            continue

    date_range = {
        "start": session_files[0][0].isoformat(),
        "end": session_files[-1][0].isoformat(),
    }

    print(json.dumps({
        "sessions": all_sessions,
        "files_read": files_read,
        "date_range": date_range,
    }, ensure_ascii=False))


def write_export(rel_path):
    """Write stdin to a file under LEARNING_DIR/exports/."""
    safe = os.path.normpath(rel_path)
    if safe.startswith("..") or not safe.startswith("exports"):
        print(json.dumps({"error": "write-export only writes to exports/ directory"}))
        sys.exit(1)
    target = LEARNING_DIR / safe
    target.parent.mkdir(parents=True, exist_ok=True)
    content = sys.stdin.read()
    target.write_text(content, encoding="utf-8")
    print(json.dumps({"written": str(target), "bytes": len(content)}))


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: quiz_engine.py <select|grade|finish|status|add-cards|edit-card|add-grades|read-file|write-export> [args]"}))
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "select":
        select_cards(sys.argv[2:])
    elif cmd == "grade":
        if len(sys.argv) < 4:
            print(json.dumps({"error": "Usage: quiz_engine.py grade <card_id> <correct|incorrect|partial>"}))
            sys.exit(1)
        grade_card(sys.argv[2], sys.argv[3])
    elif cmd == "finish":
        finish_session()
    elif cmd == "status":
        status()
    elif cmd == "add-cards":
        add_cards_from_stdin()
    elif cmd == "edit-card":
        if len(sys.argv) < 3:
            print(json.dumps({"error": "Usage: quiz_engine.py edit-card <card_id>"}))
            sys.exit(1)
        edit_card_from_stdin(sys.argv[2])
    elif cmd == "add-grades":
        if len(sys.argv) < 5:
            print(json.dumps({"error": "Usage: quiz_engine.py add-grades <correct> <incorrect> <partial>"}))
            sys.exit(1)
        try:
            add_grades(int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]))
        except ValueError:
            print(json.dumps({"error": "Grade counts must be integers"}))
            sys.exit(1)
    elif cmd == "read-file":
        if len(sys.argv) < 3:
            print(json.dumps({"error": "Usage: quiz_engine.py read-file <relative-path>"}))
            sys.exit(1)
        read_file(sys.argv[2])
    elif cmd == "sessions-since":
        since_arg = sys.argv[2] if len(sys.argv) > 2 else None
        sessions_since(since_arg)
    elif cmd == "write-export":
        if len(sys.argv) < 3:
            print(json.dumps({"error": "Usage: quiz_engine.py write-export <relative-path>"}))
            sys.exit(1)
        write_export(sys.argv[2])
    else:
        print(json.dumps({"error": f"Unknown command: {cmd}"}))
        sys.exit(1)


if __name__ == "__main__":
    main()
