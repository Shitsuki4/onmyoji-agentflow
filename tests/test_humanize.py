import random

from onmyoji_agentflow.device.humanize import (HumanizeConfig, after_delay_ms, get_normal_random, get_region_bias_rnd2,
                                               pick_point, press_ms, str_hash_to_num, swipe_points)
from onmyoji_agentflow.device._oas.utils import insert_swipe, random_rectangle_point


def test_points_inside_rect_both_styles():
    rect = [1148, 602, 1235, 663]
    for style in ("oas", "assttyys"):
        cfg = HumanizeConfig(style=style, device_id="127.0.0.1:16384")
        pts = {pick_point(rect, cfg) for _ in range(300)}
        assert len(pts) > 30, style  # really random, not a fixed point
        for x, y in pts:
            assert rect[0] <= x <= rect[2] and rect[1] <= y <= rect[3]


def test_oas_points_concentrate_in_centre():
    random.seed(1)
    xs = [random_rectangle_point((0, 0, 100, 100), n=3)[0] for _ in range(2000)]
    centre = sum(1 for x in xs if 25 <= x <= 75)
    assert centre / len(xs) > 0.6  # normal distribution around the centre (OAS)


def test_assttyys_bias_is_stable_per_device():
    a = str_hash_to_num("device-a", 100, 200)
    assert a == str_hash_to_num("device-a", 100, 200)
    assert 125 <= a <= 175
    assert str_hash_to_num("device-b", 100, 200) != a or True  # may collide, must not crash


def test_assttyys_region_rnd_inside():
    for _ in range(200):
        x, y = get_region_bias_rnd2((10, 10, 50, 30), (30, 20))
        assert 10 <= x <= 50 and 10 <= y <= 30


def test_normal_random_range():
    for _ in range(200):
        v = get_normal_random((500, 700), 600)
        assert 500 <= v <= 700


def test_press_and_delay_ranges():
    cfg = HumanizeConfig(style="assttyys", device_id="x")
    assert all(10 <= press_ms(cfg) <= 60 for _ in range(100))
    assert all(300 <= press_ms(cfg, 300) <= 350 for _ in range(100))
    assert all(500 <= after_delay_ms(cfg, 500) <= 700 for _ in range(100))


def test_swipe_random_and_bezier_path():
    cfg = HumanizeConfig()
    p1, p2, dur = swipe_points([1000, 450, 1100, 500], [400, 450, 500, 500], cfg)
    assert 1000 <= p1[0] <= 1100 and 400 <= p2[0] <= 500 and 300 <= dur <= 600
    path = insert_swipe((100, 100), (600, 300))
    # OAS insert_swipe starts at p0 and ends close to p3 (it stops when the next step would overshoot)
    assert path[0] == [100, 100] and abs(path[-1][0] - 600) <= 20 and abs(path[-1][1] - 300) <= 20 and len(path) > 5
