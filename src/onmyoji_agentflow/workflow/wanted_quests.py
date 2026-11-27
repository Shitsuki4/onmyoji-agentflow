"""Read the four visible location rows on the OAS wanted-quest detail panel."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


LOCATION_KINDS = {"式神": "挑战", "式神碎片": "挑战", "秘闻": "秘闻", "探索": "探索"}
SECRET_LAYERS = ("壹", "贰", "叁", "肆", "伍", "陆", "柒", "捌", "玖", "拾", "番外")
READOUT = r"(?P<place>[^():]+)\(数量:(?P<count>[1-9][0-9]?)\)"
CHAPTER = r"第[一二三四五六七八九十]+章"
PROGRESS = re.compile(r"([0-9]{1,2})/([0-9]{1,2})")


def _compact(value: str) -> str:
    return "".join(unicodedata.normalize("NFKC", value).split())


@dataclass(frozen=True)
class WantedLocation:
    slot: int
    kind: str
    destination: str
    runs: int
    signature: str
    progress: str


def unfinished_progress(value: str) -> tuple[int, int] | None:
    match = PROGRESS.fullmatch(_compact(value))
    if not match:
        return None
    current, total = map(int, match.groups())
    return (current, total) if 0 <= current < total <= 14 else None


def first_tracked_badge(boxes, read_counter):
    rail = [(text, x, y) for text, x, y in boxes if 12 <= x < 112 and 119 <= y < 512]
    labels = sorted((y, x) for text, x, y in rail if _compact(text) == "悬赏封印")
    for y, x in labels:
        counters = {
            value for text, cx, cy in rail
            if abs(cx - x) <= 22 and 10 <= abs(cy - y) <= 34
            and (value := unfinished_progress(text))
        }
        if not counters:
            # Labels appear above or below the counter depending on the map layout.
            counters = {
                value for top in (max(119, y - 35), y + 8) if top + 26 <= 512
                and (value := unfinished_progress(read_counter((26, top, 62, 26))))
            }
        if len(counters) == 1:
            current, total = counters.pop()
            return (x, y), f"{current}/{total}"
    return None


def choose_location(boxes, progress: str, heading: str, *, priority: str, secret_cutoff: str,
                    excluded: str, tickets: int) -> WantedLocation | None:
    progress = unfinished_progress(progress)
    heading = re.fullmatch(r"悬赏目标:(?:击败|击杀)([0-9]{1,2})个([\u3400-\u9fff]{1,16})", _compact(heading))
    if not progress or not heading:
        return None
    current, total = progress
    monster = heading[2]
    if int(heading[1]) != total:
        return None
    if any(name and name in monster for name in re.split(r"[,，]", _compact(excluded))):
        return None
    order = _compact(priority).split(">")
    kinds = set(LOCATION_KINDS.values())
    if not set(order) <= kinds or len(order) != len(set(order)):
        return None
    forbidden = SECRET_LAYERS[SECRET_LAYERS.index(secret_cutoff):] if secret_cutoff in SECRET_LAYERS else ()
    candidates = []
    for slot, center in enumerate((301, 377, 452, 528), 1):
        row = sorted((x, _compact(word)) for word, x, y in boxes
                     if 625 <= x < 1031 and abs(y - center) <= 17 and word.strip())
        if not row or len(row) > 4:
            continue
        line = "".join(word for _, word in row)
        category = next((label for label in sorted(LOCATION_KINDS, key=len, reverse=True)
                         if line.startswith(label)), "")
        match = re.fullmatch(READOUT, line[len(category):]) if category else None
        if not match:
            continue
        kind = LOCATION_KINDS[category]
        if kind not in order or (kind == "挑战" and tickets < 1):
            continue
        place = match["place"]
        if kind == "秘闻":
            if not place.endswith(SECRET_LAYERS) or (forbidden and place.endswith(forbidden)):
                continue
        elif not re.fullmatch(CHAPTER, place):
            continue
        count = int(match["count"])
        remaining = total - current
        # OAS challenge() enters exactly one ticket battle; its outer loop rereads progress.
        runs = 1 if kind == "挑战" else (remaining + count - 1) // count
        counter = f"{current}/{total}"
        signature = f"{monster}:{counter}:{slot}:{kind}:{place}:{count}:{tickets if kind == '挑战' else ''}"
        candidates.append((order.index(kind), WantedLocation(slot, kind, place, runs, signature, counter)))
    return min(candidates, key=lambda entry: (entry[0], entry[1].slot))[1] if candidates else None
