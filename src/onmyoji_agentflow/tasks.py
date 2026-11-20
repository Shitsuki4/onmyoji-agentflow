"""Read task rows without deriving game progress from click counts."""
from __future__ import annotations

import re


TASK_PATTERNS = (
    ("battle_15", r"挑战.*(?:探索|御魂|觉醒)"),
    ("realm_raid_wins", r"结界突破.*(?:胜利|获胜)|(?:胜利|获胜).*结界突破"),
    ("regional_boss", r"地域鬼王"),
    ("delegation", r"式神委派"),
    ("realm_experience", r"结界卡.*经验"),
    ("foster", r"寄养"),
    ("sign_in", r"签到"),
    ("friend_hearts", r"(?:赠送|好友).*红心"),
    ("bounty", r"悬赏封印"),
    ("soul_upgrade", r"御魂强化"),
)


def task_key(text: str) -> str:
    compact = re.sub(r"\s+", "", text)
    for key, pattern in TASK_PATTERNS:
        if re.search(pattern, compact):
            return key
    return "game:" + compact


def parse_task_page(boxes: list[tuple[str, int, int]]) -> list[dict]:
    out = []
    pattern = r"(?<!\d)(\d+)\s*[/／]\s*(\d+)(?!\d)"
    for text, center_x, center_y in sorted(boxes, key=lambda box: box[2]):
        if not (500 <= center_x < 900 and 230 <= center_y <= 585):
            continue
        if not re.search(r"已完成|已领取", text):
            continue
        counter = re.search(pattern, text)
        title = [(label, coord_x, coord_y) for label, coord_x, coord_y in boxes
                 if 550 <= coord_x < 920 and 18 <= center_y - coord_y <= 48]
        title.sort(key=lambda box: box[1])
        label = "".join(value for value, _, _ in title)
        if not label or (counter is None and "已领取" not in text):
            continue
        progress = re.search(pattern, label) or counter
        if progress is None:
            continue
        current, target = map(int, progress.groups())
        if not 0 <= current <= target <= 100000 or target == 0:
            continue
        label = re.sub(pattern, "", label)
        label = re.sub(r"\s", "", label)
        status_words = [value for value, coord_x, coord_y in boxes
                        if 980 <= coord_x <= 1120 and abs(coord_y - center_y) < 48]
        out.append({"key": task_key(label), "label": label, "current": current, "target": target,
                    "claimed": "已领取" in text or any(value in ("已完成", "已领取") for value in status_words),
                    "source": "game_ocr", "row_y": center_y, "text": text})
    return out


def remaining_task(rows, key):
    row = next((item for item in rows if item["task_key"] == key and item.get("verified")), None)
    if row is None or row.get("current") is None or row.get("target") is None:
        return None
    return max(0, row["target"] - row["current"])


class TaskScanner:
    """Bounded page scanning with explicit partial-coverage evidence."""

    def __init__(self, scope, max_pages):
        self.scope = scope
        self.max_pages = max_pages
        self.reset_remaining = max_pages
        self.pages = 0
        self.previous = None
        self.rows = {}
        self.complete = False
        self.finished = False

    def step(self, records):
        if self.reset_remaining:
            self.reset_remaining -= 1
            return {"swipe": {"from": [805, 245, 825, 260], "to": [805, 480, 825, 495]}, "delay": 800}, False
        fingerprint = tuple((row["key"], row["current"], row["target"], row["claimed"]) for row in records)
        if not fingerprint:
            self.finished = True
            return None, False
        self.pages += 1
        for row in records:
            self.rows[row["key"]] = row
        if fingerprint == self.previous:
            self.complete = True
            self.finished = True
            return None, True
        self.previous = fingerprint
        if self.pages >= self.max_pages:
            self.finished = True
            return None, True
        return {"swipe": {"from": [805, 480, 825, 495], "to": [805, 255, 825, 270]}, "delay": 1000}, True
