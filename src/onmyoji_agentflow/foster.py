"""Pure foster-candidate ranking; device code only supplies OCR/colour evidence."""
from __future__ import annotations

from dataclasses import dataclass
import re


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


class FosterSelector:
    """Inspect every visible friend in both tabs before choosing; one input per step."""

    def __init__(self, max_pages=30):
        self.max_pages = max_pages
        self.phase = "tab"
        self.region = 0
        self.page = 0
        self.seen = set()
        self.candidates = []
        self.pending = None
        self.best = None
        self.unknown = []
        self.previous_page = None

    def step(self, boxes, card_boxes, frame=None, template_dir=None):
        from dataclasses import replace
        tabs = [[250, 115, 285, 135], [370, 115, 405, 135]]
        rows = [(text.strip(), coord_x, coord_y) for text, coord_x, coord_y in boxes
                if 315 <= coord_x <= 610 and 155 <= coord_y <= 590]
        rows.sort(key=lambda box: box[2])
        if self.phase == "tab":
            self.phase = "reset"
            return {"click": tabs[self.region], "delay": 1000}
        if self.phase == "reset":
            self.phase = "locate" if self.best else "scan"
            return {"click": [184, 185, 193, 196], "delay": 1200}
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
            return {"stop": {"reason": "最佳候选卡型和星级已复核，等待核对好友归属和白达摩等级",
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
        for name, _, row_y in rows:
            key = (self.region, name)
            if key not in self.seen:
                self.seen.add(key)
                self.pending = name
                self.phase = "detail"
                return {"click": [340, row_y - 10, 510, row_y + 10], "delay": 900}
        fingerprint = tuple(row[0] for row in rows)
        ended = self.previous_page == fingerprint
        self.previous_page = fingerprint
        if ended:
            if self.region == 0:
                self.region = 1
                self.phase = "tab"
                self.page = 0
                self.previous_page = None
                return self.step(boxes, card_boxes, frame, template_dir)
            if self.unknown:
                return {"stop": {"reason": f"{len(self.unknown)} 个候选卡型或星级未识别，不能确认全局最优", "result": "blocked"}}
            self.best = choose_foster(self.candidates)
            if self.best is None:
                return {"stop": {"reason": "同区和跨区均未找到有效结界卡，不使用基础经验寄养", "result": "skipped"}}
            self.region = int(self.best.region)
            self.page = 0
            self.phase = "tab"
            return self.step(boxes, card_boxes, frame, template_dir)
        self.page += 1
        if self.page >= self.max_pages:
            return {"stop": {"reason": "好友列表扫描达到上限，尚未完整比较", "result": "blocked"}}
        return {"swipe": {"from": [400, 525, 420, 540], "to": [400, 205, 420, 220]}, "delay": 1000}
