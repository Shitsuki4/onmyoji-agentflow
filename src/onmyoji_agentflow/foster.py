"""Pure foster-candidate ranking; device code only supplies OCR/colour evidence."""
from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata


CARD_PRIORITY = {"太鼓": 0, "斗鱼": 1, "伞室内": 2, "其他变异结界卡": 3, "太阴": 4}
STAR_ORIGINS = {3: (835, 321), 4: (836, 322), 5: (834, 320), 6: (833, 320)}


@dataclass(frozen=True)
class FosterCandidate:
    friend: str
    stars: int | None
    card_type: str | None
    remaining_s: int | None = None
    region: str | None = None
    evidence: dict | None = None

    @property
    def recognized(self) -> bool:
        return (type(self.stars) is int and 1 <= self.stars <= 6 and self.card_type in CARD_PRIORITY
                and (self.remaining_s is None or self.remaining_s > 0))


def foster_sort_key(candidate: FosterCandidate):
    """Return descending star order then user's same-star card preference."""
    return (-int(candidate.stars or 0), CARD_PRIORITY.get(candidate.card_type or "", 99),
            -(int(candidate.remaining_s or 0)))


def choose_foster(candidates: list[FosterCandidate]) -> FosterCandidate | None:
    known = [c for c in candidates if c.recognized]
    return min(known, key=foster_sort_key) if known else None


def read_countdown(text: str | None) -> int | None:
    """Parse a visible ``HH:MM:SS`` countdown without guessing a due time."""
    if not text:
        return None
    match = re.search(r"(?<!\d)(\d{1,2})\s*[:：]\s*(\d{2})\s*[:：]\s*(\d{2})(?!\d)", str(text))
    if not match:
        return None
    hours, minutes, seconds = (int(value) for value in match.groups())
    if minutes > 59 or seconds > 59:
        return None
    return hours * 3600 + minutes * 60 + seconds


def _read_star_template(frame, template_dir):
    from pathlib import Path

    import cv2
    import numpy as np

    if frame.shape[:2] != (720, 1280):
        return None
    matches = []
    for level, (x, y) in STAR_ORIGINS.items():
        path = Path(template_dir) / f"utilize_u_big_{level}.png"
        if not path.is_file():
            return None
        template = cv2.imdecode(np.fromfile(path, np.uint8), cv2.IMREAD_COLOR)
        if template is None:
            return None
        h, w = template.shape[:2]
        crop = frame[y - 2:y + h + 2, x - 2:x + w + 2]
        score = float(cv2.minMaxLoc(cv2.matchTemplate(crop, template, cv2.TM_CCOEFF_NORMED))[1])
        matches.append((score, level))
    matches.sort(reverse=True)
    return matches[0][1] if matches[0][0] >= 0.85 and matches[0][0] - matches[1][0] >= 0.04 else None


def read_card(boxes, frame=None, template_dir=None):
    values = [re.sub(r"\s", "", value) for value, _, _ in boxes]
    text = " ".join(values)
    if "已占用" in text:
        return None, "occupied"
    if "未放置" in text:
        return None, "empty"
    card_types = {name for name in CARD_PRIORITY if name in text}
    if "伞内室" in text:
        card_types.add("伞室内")
    if not card_types and any(name in text for name in ("变异", "美食", "胧车", "口水蛙", "葫芦酒", "孟婆汤", "绵绵冰")):
        card_types.add("其他变异结界卡")
    if len(card_types) != 1:
        return None, "unknown"
    ocr_stars = {int(value) for value in re.findall(r"(?<!\d)([1-6])\s*星", text)}
    if len(ocr_stars) > 1:
        return None, "unknown"
    image_stars = _read_star_template(frame, template_dir) if frame is not None and template_dir is not None else None
    stars = next(iter(ocr_stars), None)
    if image_stars is not None and stars is not None and image_stars != stars:
        return None, "unknown"
    stars = stars or image_stars
    if stars is None:
        return None, "unknown"
    remaining = read_countdown(text)
    if remaining == 0:
        return None, "expired"
    return FosterCandidate("", stars, card_types.pop(), remaining), "known"


def selected_friend(frame, rows):
    """Read the nickname inside the unique highlighted row on the 1280x720 friend panel."""
    import cv2
    import numpy as np

    if frame is None or frame.shape != (720, 1280, 3):
        return None
    top, bottom = 162, 605
    panel = cv2.cvtColor(frame[top:bottom, 320:600], cv2.COLOR_BGR2HSV)
    purple = cv2.inRange(panel, (116, 105, 115), (157, 255, 255))
    lines = np.flatnonzero(np.count_nonzero(purple, axis=1) >= panel.shape[1] * 0.8) + top
    bands = [band for band in np.split(lines, np.flatnonzero(np.diff(lines) > 8) + 1) if len(band) >= 2]
    if len(bands) == 2:
        upper, lower = [float(np.mean(band)) for band in bands]
        if not 89 <= lower - upper <= 112:
            return None
        center = (upper + lower) / 2
    elif len(bands) == 1:
        border = float(np.mean(bands[0]))
        # The list can clip one edge of the highlighted top or bottom row.
        # Require a continuous coloured wall toward the clipping edge as well.
        row_height = 100
        if border + row_height >= bottom - 4:
            wall_top, wall_bottom, center = int(border) + 8, bottom - 2, border + row_height / 2
        elif border - 89 < top:
            wall_top, wall_bottom, center = top + 2, int(border) - 8, border - row_height / 2
        else:
            return None
        wall = cv2.cvtColor(frame[wall_top:wall_bottom, 206:222], cv2.COLOR_BGR2HSV)
        if wall.shape[0] < 20:
            return None
        wall_purple = cv2.inRange(wall, (116, 105, 115), (157, 255, 255))
        if np.mean(np.count_nonzero(wall_purple, axis=1) >= 3) < .8:
            return None
    else:
        return None
    matches = [name for name, _, y in rows if abs(y - center) <= 24]
    return matches[0] if len(matches) == 1 else None


def foster_friend_key(name):
    """Unify OCR width variants while retaining the nickname and its punctuation."""
    return "".join(unicodedata.normalize("NFKC", char)
                   if unicodedata.east_asian_width(char) in {"F", "H"} else char for char in name).strip()


def read_foster_friend_rows(frame, reader, *, cross_region=False):
    """Read each nickname, excluding coloured server names and account badges."""
    if cross_region and frame.shape == (720, 1280, 3):
        import cv2

        frame = frame.copy()
        labels = frame[145:605, 318:611]
        hsv = cv2.cvtColor(labels, cv2.COLOR_BGR2HSV)
        text = cv2.inRange(hsv, (0, 0, 0), (179, 102, 124))
        labels[text == 0] = 255
    return reader(frame, [200, 145, 430, 460])


def _unread_cross_friend_centers(frame, rows):
    """Locate visible dark nickname lines without a recognized OCR row."""
    if frame.shape != (720, 1280, 3):
        return []
    import cv2
    import numpy as np

    top = 165
    area = cv2.cvtColor(frame[top:599, 330:590], cv2.COLOR_BGR2HSV)
    text = cv2.inRange(area, (0, 0, 0), (179, 102, 124))
    ink = np.count_nonzero(text, axis=1)
    lines = np.flatnonzero(ink >= 8)
    groups = np.split(lines, np.flatnonzero(np.diff(lines) > 4) + 1)
    centers = [top + (int(group[0]) + int(group[-1])) / 2
               for group in groups if 8 <= len(group) <= 33 and sum(ink[group]) >= 180]
    return [center for center in centers if 180 <= center <= 590
            and not any(315 <= x <= 610 and abs(y - center) <= 15 for _name, x, y in rows)]


def missing_cross_friend_rows(frame, rows):
    """Count visible dark nickname lines without a recognized OCR row."""
    return len(_unread_cross_friend_centers(frame, rows))


def supplement_cross_friend_rows(frame, rows, nickname_templates):
    """Use local nickname calibrations only for unique, otherwise unread rows."""
    from .vision.template import match_template

    centers = _unread_cross_friend_centers(frame, rows)
    recognized = {foster_friend_key(name) for name, x, _ in rows if 315 <= x <= 610}
    matched = {center: [] for center in centers}
    for name, path in nickname_templates.items():
        if foster_friend_key(name) in recognized:
            continue
        hits = []
        for center in centers:
            hit, _, box = match_template(frame, path, (318, int(center) - 22, 284, 45),
                                         threshold=.95, strict_roi=True)
            if hit:
                hits.append((center, box[0] + box[2] // 2))
        if len(hits) == 1:
            center, x = hits[0]
            matched[center].append((name, x, int(center)))
    return [*rows, *(hits[0] for hits in matched.values() if len(hits) == 1)]


class FosterSelector:
    """Inspect every visible friend in both tabs before choosing; one input per step."""

    def __init__(self, max_pages=30, *, require_highlight=False):
        self.max_pages = max_pages
        self.require_highlight = require_highlight
        self.phase = "tab"
        self.region = 0
        self.page = 0
        self.seen = set()
        self.candidates = []
        self.pending = None
        self.best = None
        self.unknown = []
        self.previous_page = None
        self.selection_checks = 0

    def step(self, boxes, card_boxes, frame=None, template_dir=None, *, active_region=None):
        from dataclasses import replace
        tabs = [[250, 115, 285, 135], [370, 115, 405, 135]]
        rows = [(text.strip(), coord_x, coord_y) for text, coord_x, coord_y in boxes
                if 315 <= coord_x <= 610 and 155 <= coord_y <= 590 and text.strip()]
        if self.require_highlight:
            rows = [(foster_friend_key(name), x, y) for name, x, y in rows if "最近寄养" not in name.replace(" ", "")]
            if len({row[0] for row in rows}) != len(rows):
                return {"stop": {"reason": "当前好友列表有重复昵称，暂停核对寄养", "result": "blocked"}}
        rows.sort(key=lambda box: box[2])
        if self.require_highlight and active_region is None:
            return {"stop": {"reason": "未能明确识别当前好友列表标签", "result": "blocked"}}
        if self.phase == "tab":
            if self.require_highlight and active_region != self.region:
                return {"click": tabs[self.region], "delay": 1000}
            self.phase = "reset"
            if not self.require_highlight:
                return {"click": tabs[self.region], "delay": 1000}
        if self.require_highlight and active_region != self.region:
            return {"stop": {"reason": "好友列表切换后归属未通过核对", "result": "blocked"}}
        if self.phase == "reset":
            self.phase = "locate" if self.best else "scan"
            return {"click": [184, 185, 193, 196], "delay": 1200}
        if self.require_highlight and self.phase in ("detail", "verify"):
            expected = self.pending if self.phase == "detail" else self.best.friend
            if selected_friend(frame, rows) != expected:
                self.selection_checks += 1
                if self.selection_checks < 4:
                    return {"wait": 300}
                return {"stop": {"reason": "选中框与本次目标好友不符，未采用当前卡片", "result": "blocked"}}
            self.selection_checks = 0
        if self.phase == "detail":
            card, status = read_card(card_boxes, frame, template_dir)
            if card:
                self.candidates.append(replace(card, friend=self.pending, region=str(self.region),
                                                evidence={"page": self.page}))
            elif status == "unknown":
                self.unknown.append((self.region, self.pending))
            self.phase = "scan"
        if self.phase == "verify":
            card, status = read_card(card_boxes, frame, template_dir)
            if status != "known" or (card.stars, card.card_type) != (self.best.stars, self.best.card_type):
                return {"stop": {"reason": "候选结界卡已变化或无法复核，暂停寄养", "result": "blocked"}}
            self.phase = "previewed"
        if self.phase == "previewed":
            reason = ("最佳候选好友、卡型和星级已复核，等待核对空位与寄养式神" if self.require_highlight else
                      "最佳候选卡型和星级已复核，等待核对好友归属和白达摩等级")
            return {"stop": {"reason": reason,
                             "result": "blocked", "evidence": {"stars": self.best.stars,
                             "card_type": self.best.card_type, "region": self.best.region}}}
        if self.phase == "locate":
            for name, _, row_y in rows:
                if name == self.best.friend:
                    self.phase = "verify"
                    return {"click": [340, row_y - 10, 510, row_y + 10], "delay": 900}
            self.page += 1
            if self.page >= self.max_pages:
                return {"stop": {"reason": "重新定位最佳好友失败", "result": "blocked"}}
            return {"swipe": {"from": [400, 520, 420, 535], "to": [400, 205, 420, 220]}, "delay": 1000}
        if not rows:
            return {"stop": {"reason": "好友列表昵称识别不足，暂停选卡", "result": "blocked"}}
        fingerprint = tuple(row[0] for row in rows)
        if self.require_highlight and self.previous_page is not None and not set(fingerprint).intersection(self.previous_page):
            return {"stop": {"reason": "滚动后两屏好友没有重叠，无法确认所有结界卡均已检查", "result": "blocked"}}
        for name, _, row_y in rows:
            key = (self.region, name)
            if key not in self.seen:
                self.seen.add(key)
                self.pending = name
                self.phase = "detail"
                return {"click": [340, row_y - 10, 510, row_y + 10], "delay": 900}
        ended = self.previous_page == fingerprint
        self.previous_page = fingerprint
        if ended:
            if self.region == 0:
                self.region = 1
                self.phase = "tab"
                self.page = 0
                self.previous_page = None
                return self.step(boxes, card_boxes, frame, template_dir, active_region=active_region)
            if self.unknown:
                return {"stop": {"reason": f"{len(self.unknown)} 个候选卡型或星级未识别，不能确认全局最优", "result": "blocked"}}
            self.best = choose_foster(self.candidates)
            if self.best is None:
                return {"stop": {"reason": "同区和跨区均未找到有效结界卡，不使用基础经验寄养", "result": "skipped"}}
            self.region = int(self.best.region)
            self.page = 0
            self.phase = "tab"
            return self.step(boxes, card_boxes, frame, template_dir, active_region=active_region)
        self.page += 1
        if self.page >= self.max_pages:
            return {"stop": {"reason": "好友列表扫描达到上限，尚未完整比较", "result": "blocked"}}
        if self.require_highlight:
            return {"swipe": {"from": [400, 480, 420, 490], "to": [400, 340, 420, 350]},
                    "duration_ms": [650, 700], "delay": 1100}
        return {"swipe": {"from": [400, 525, 420, 540], "to": [400, 205, 420, 220]}, "delay": 1000}
