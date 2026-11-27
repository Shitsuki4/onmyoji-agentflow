"""Native OAS image-method contracts using inert arrays and local fixtures."""
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from onmyoji_agentflow.vision.template import ImageMatch, match_template, match_template_above


def textured(height=30, width=40):
    return np.random.default_rng(91).integers(0, 256, (height, width, 3), dtype=np.uint8)


def scene(template, x=35, y=27):
    image = np.random.default_rng(18).integers(0, 256, (140, 180, 3), dtype=np.uint8)
    image[y:y + template.shape[0], x:x + template.shape[1]] = template
    return image


def test_template_above_prefers_column_alignment_and_respects_search_bounds(tmp_path):
    icon = textured(12, 16)
    path = tmp_path / "sword.png"
    cv2.imencode(".png", icon)[1].tofile(str(path))
    image = textured(160, 220)
    anchor = (104, 110, 20, 20)
    limits = dict(x_pad=50, max_above=90, min_gap=18, x_weight=3, threshold=.99)

    for x, y in ((106, 28), (140, 69), (106, 91), (171, 69)):
        image[y:y + 12, x:x + 16] = icon

    assert match_template_above(image, str(path), anchor, **limits) == (106, 28, 16, 12)
    image[28:40, 106:122] = 0
    assert match_template_above(image, str(path), anchor, **limits) == (140, 69, 16, 12)
    image[69:81, 140:156] = 0
    assert match_template_above(image, str(path), anchor, **limits) is None


def test_legacy_positional_api_roi_growth_threshold_and_tuple_behavior(monkeypatch):
    template = textured()
    matched = match_template(scene(template), template, [35, 27, 1, 1], .99)
    assert isinstance(matched, tuple) and isinstance(matched, ImageMatch) and len(matched) == 3
    ok, score, box = matched
    assert ok and score > .99 and box == (35, 27, 40, 30)
    assert matched.scale is None and matched.method == "Template matching"
    monkeypatch.setattr(cv2, "matchTemplate", lambda *args, **kwargs: np.array([[.8]], np.float64))
    assert match_template(scene(template), template, None, .8)[0]
    with pytest.raises(TypeError):
        match_template(scene(template), template, None, .8, "Sift Flann")


@pytest.mark.parametrize("method", ["Masked template matching", "Multi-scale template matching"])
def test_oas_correlation_methods_use_strict_threshold(monkeypatch, method):
    template = textured()
    monkeypatch.setattr(cv2, "matchTemplate", lambda *args, **kwargs: np.array([[.8]], np.float64))
    result = match_template(scene(template), template, threshold=.8, method=method)
    assert not result.matched and result.score == .8


def test_mask_uses_nonzero_selected_pixels_and_preserves_roi_offset():
    template = textured()
    changed = template.copy()
    changed[:, 20:] = np.random.default_rng(55).integers(0, 256, (30, 20, 3), dtype=np.uint8)
    image = scene(changed)
    mask = np.zeros(template.shape[:2], np.uint8)
    mask[:, :20] = 7  # source semantics: any nonzero mask pixel participates
    result = match_template(image, template, [30, 20, 60, 50], .99,
                            method="Masked template matching", mask=mask)
    assert result.matched and result.score > .99 and result.box == (35, 27, 40, 30)
    assert result.mask_used and result.mask_fallback is None and result.roi == (30, 20, 60, 50)
    assert not match_template(image, template, threshold=.99).matched


def test_mask_is_autodiscovered_for_unicode_template_path(tmp_path):
    template = textured()
    mask = np.zeros(template.shape[:2], np.uint8)
    mask[:, :20] = 255
    path = tmp_path / "庭院.png"
    cv2.imencode(".png", template)[1].tofile(str(path))
    cv2.imencode(".png", mask)[1].tofile(str(tmp_path / "庭院_mask.png"))
    changed = template.copy()
    changed[:, 20:] = 0
    result = match_template(scene(changed), path, method="Masked template matching", threshold=.99)
    assert result.matched and result.mask_used and result.box == (35, 27, 40, 30)


def test_explicit_mask_string_path_works_with_array_template(tmp_path):
    template = textured()
    mask = np.zeros(template.shape[:2], np.uint8)
    mask[:, :20] = 255
    path = tmp_path / "显式掩码.png"
    cv2.imencode(".png", mask)[1].tofile(str(path))
    changed = template.copy()
    changed[:, 20:] = 0
    result = match_template(scene(changed), template, method="Masked template matching",
                            mask=str(path), threshold=.99)
    assert result.matched and result.mask_used and result.mask_fallback is None


@pytest.mark.parametrize("kind", ["missing", "missing_string", "undecodable", "wrong_size", "float", "color", "list"])
def test_missing_or_malformed_mask_has_explicit_source_plain_fallback(tmp_path, kind):
    template = textured()
    mask = None
    if kind in ("missing", "missing_string", "undecodable"):
        mask = tmp_path / "mask.png"
        if kind == "undecodable":
            mask.write_bytes(b"not an encoded image")
        elif kind == "missing_string":
            mask = str(mask)
    elif kind == "wrong_size":
        mask = np.ones((2, 2), np.uint8)
    elif kind == "float":
        mask = np.ones(template.shape[:2], np.float32)
    elif kind == "color":
        mask = np.ones(template.shape, np.uint8)
    else:
        mask = [[1, 1]]
    result = match_template(scene(template), template, method="Masked template matching", mask=mask)
    assert result.matched and not result.mask_used and result.mask_fallback
    assert result.box == (35, 27, 40, 30)


@pytest.mark.parametrize("empty", [True, False])
def test_valid_empty_or_selected_flat_mask_rejects_without_fallback(empty):
    template = textured()
    mask = np.zeros(template.shape[:2], np.uint8)
    if not empty:
        mask[0, 0] = 255  # each channel has zero variance across the selected region
    result = match_template(scene(template), template, method="Masked template matching", mask=mask)
    assert not result.matched and result.score == -1 and result.mask_used
    assert result.mask_fallback is None


def test_masked_roi_is_not_silently_grown_even_when_mask_falls_back():
    template = textured()
    result = match_template(scene(template), template, [35, 27, 1, 1], method="Masked template matching")
    assert not result.matched and result.roi == (35, 27, 1, 1)
    assert result.mask_fallback == "not_provided"


@pytest.mark.parametrize("method", ["Template matching", "Masked template matching", "Multi-scale template matching"])
def test_original_per_channel_flat_template_is_never_evidence(method):
    template = np.empty((30, 40, 3), np.uint8)
    template[:] = (30, 90, 150)
    result = match_template(scene(template), template, method=method)
    assert not result.matched and result.score == -1


def test_new_method_clips_roi_without_negative_slice_wrap_or_offset_loss():
    template = textured()
    result = match_template(scene(template, x=0, y=0), template, [-5, -7, 60, 50],
                            method="Masked template matching")
    assert result.matched and result.box == (0, 0, 40, 30) and result.roi == (0, 0, 55, 43)


@pytest.mark.parametrize("method", ["Template matching", "Masked template matching", "Multi-scale template matching"])
@pytest.mark.parametrize("value", [np.nan, np.inf, -np.inf])
def test_nonfinite_scores_never_become_evidence_even_with_negative_threshold(monkeypatch, method, value):
    template = textured()
    monkeypatch.setattr(cv2, "matchTemplate", lambda *args, **kwargs: np.array([[value]], np.float32))
    result = match_template(scene(template), template, threshold=-2, method=method)
    assert not result.matched and np.isfinite(result.score)


def test_multiscale_preserves_winning_scale_dimensions_and_absolute_box():
    template = textured(40, 50)
    scaled = cv2.resize(template, (30, 24))
    result = match_template(scene(scaled), template, [25, 15, 90, 80], .99,
                            method="Multi-scale template matching")
    assert result.matched and result.score > .99 and result.scale == .6
    assert result.box == (35, 27, 30, 24) and result.roi == (25, 15, 90, 80)


def test_multiscale_searches_all_scales_and_keeps_best_not_first(monkeypatch):
    template = textured(20, 20)
    seen = []

    def score(area, scaled, method):
        seen.append(scaled.shape[0])
        value = {.6: .9, .9: .98, 1.2: .95}.get(round(scaled.shape[0] / 20, 1), .2)
        return np.array([[0, 0, 0], [0, 0, value]], np.float32)

    monkeypatch.setattr(cv2, "matchTemplate", score)
    result = match_template(scene(template), template, [10, 12, 80, 80], .8,
                            method="Multi-scale template matching", scales=[1.2, .6, .9, .6])
    assert seen == [12, 18, 24]
    assert result.matched and result.scale == .9 and result.box == (12, 13, 18, 18)


def test_multiscale_range_retains_source_rounding_and_end_plus_step(monkeypatch):
    template = textured(20, 20)
    seen = []

    def score(area, scaled, method):
        seen.append(scaled.shape[0])
        return np.array([[.5]], np.float32)

    monkeypatch.setattr(cv2, "matchTemplate", score)
    result = match_template(scene(template), template, method="Multi-scale template matching",
                            scale_range=(.6, .9, .2))
    assert seen == [12, 16, 20]  # source arange(start, end+step, step), including 1.0
    assert not result.matched and result.scale == .6  # ties retain the earlier scale


def test_multiscale_can_fit_when_original_exceeds_roi_but_skips_tiny_sizes():
    template = textured(40, 50)
    smaller = cv2.resize(template, (30, 24))
    image = scene(smaller)
    result = match_template(image, template, [35, 27, 30, 24], .99,
                            method="Multi-scale template matching", scales=[.1, .6, 2])
    assert result.matched and result.scale == .6 and result.box == (35, 27, 30, 24)
    impossible = match_template(image, template, [35, 27, 5, 5], method="Multi-scale template matching")
    assert not impossible.matched and impossible.scale is None


def test_flat_resized_template_cannot_create_false_multiscale_evidence(monkeypatch):
    template = textured(40, 40)
    monkeypatch.setattr(cv2, "resize", lambda *args: np.full((20, 20, 3), 80, np.uint8))
    monkeypatch.setattr(cv2, "matchTemplate", lambda *args: pytest.fail("flat scaled template must be rejected"))
    result = match_template(scene(template), template, method="Multi-scale template matching", scales=[.5])
    assert not result.matched and result.scale is None


@pytest.mark.parametrize("kwargs", [
    {"scales": [np.nan]}, {"scales": [0]}, {"scales": [True]},
    {"scale_range": (1, .5)}, {"scale_range": (.5, 1, 0)},
    {"scale_range": (.5, 1, .000001)}, {"scale_range": (.5, np.inf)},
    {"scales": [np.complex64(1 + 2j)]},
])
def test_invalid_or_unbounded_scale_grids_are_explicit_errors(kwargs):
    template = textured()
    with pytest.raises(ValueError):
        match_template(scene(template), template, method="Multi-scale template matching", **kwargs)


def test_oversized_finite_scale_is_skipped_without_resize_or_overflow(monkeypatch):
    template = textured()
    monkeypatch.setattr(cv2, "resize", lambda *args: pytest.fail("oversized scale cannot allocate an image"))
    result = match_template(scene(template), template, method="Multi-scale template matching", scales=[1e308])
    assert not result.matched and result.scale is None


def features(monkeypatch, count=12, ratio=.5, matrix=None, missing=False, short_pairs=False):
    recorded = {"images": []}
    keypoints = [SimpleNamespace(pt=(float(i % 4 * 8), float(i // 4 * 8))) for i in range(count)]
    descriptors = np.zeros((count, 128), np.float32)

    class Sift:
        def detectAndCompute(self, image, mask):
            recorded["images"].append(image.copy())
            assert mask is None
            return keypoints, None if missing else descriptors

    class Flann:
        def __init__(self, index, search):
            recorded["flann"] = (index, search)

        def knnMatch(self, query, train, k):
            assert k == 2
            return [([SimpleNamespace(distance=ratio, queryIdx=i, trainIdx=i)] if short_pairs else [
                SimpleNamespace(distance=ratio, queryIdx=i, trainIdx=i), SimpleNamespace(distance=1.)])
                    for i in range(count)]

    def homography(source, target, method, threshold):
        recorded["homography"] = (source.copy(), target.copy(), method, threshold)
        return matrix, np.ones((count, 1), np.uint8)

    monkeypatch.setattr(cv2, "SIFT_create", Sift)
    monkeypatch.setattr(cv2, "FlannBasedMatcher", Flann)
    monkeypatch.setattr(cv2, "findHomography", homography)
    monkeypatch.setattr(cv2, "matchTemplate", lambda *args, **kwargs: pytest.fail("SIFT cannot fall back to correlation"))
    return recorded


@pytest.mark.parametrize("method", ["Sift Flann", "Default"])
def test_sift_uses_source_parameters_rgb_inputs_and_unscaled_box(monkeypatch, method):
    matrix = np.array([[2., 0, 12], [0, 2., 20], [0, 0, 1]])
    recorded = features(monkeypatch, matrix=matrix)
    template = textured(30, 40)
    image = scene(template)
    result = match_template(image, template, [10, 11, 120, 110], threshold=99, method=method)
    assert result.matched and result.score == -1 and result.scale is None
    assert result.method == method and result.effective_method == "Sift Flann"
    assert result.box == (22, 31, 40, 30)  # source only moves roi_front origin for SIFT
    assert result.corners == ((22, 31), (22, 89), (100, 89), (100, 31))
    assert result.good_matches == 12
    assert recorded["flann"] == ({"algorithm": 1, "trees": 5}, {"checks": 50})
    assert recorded["homography"][2:] == (cv2.RANSAC, 5.)
    assert np.array_equal(recorded["images"][0], image[11:121, 10:130, ::-1])
    assert np.array_equal(recorded["images"][1], template[:, :, ::-1])


@pytest.mark.parametrize("options", [{"count": 9}, {"ratio": .6}, {"missing": True}, {"short_pairs": True},
                                     {"matrix": None}, {"matrix": np.full((3, 3), np.nan)},
                                     {"matrix": np.array([[1., 1.5, 0], [0, 1, 0], [0, 0, 1]])}])
def test_sift_insufficient_invalid_or_nonrectangular_evidence_fails_closed(monkeypatch, options):
    settings = {"matrix": np.eye(3), **options}
    features(monkeypatch, **settings)
    template = textured()
    result = match_template(scene(template), template, method="Sift Flann")
    assert not result.matched and result.score == -1 and result.reason


@pytest.mark.parametrize("method", ["Sift Flann", "Default"])
def test_sift_missing_opencv_capability_is_explicit(monkeypatch, method):
    monkeypatch.delattr(cv2, "SIFT_create")
    template = textured()
    with pytest.raises(NotImplementedError, match="SIFT_create"):
        match_template(scene(template), template, method=method)


def test_default_literal_does_not_fall_back_to_plain_when_sift_has_no_descriptors(monkeypatch):
    features(monkeypatch, missing=True)
    template = textured()
    result = match_template(scene(template), template, method="Default", threshold=-100)
    assert not result.matched and result.score == -1 and result.reason == "insufficient SIFT descriptors"
    assert result.method == "Default" and result.effective_method == "Sift Flann"


@pytest.mark.skipif(not hasattr(cv2, "SIFT_create"), reason="OpenCV lacks SIFT")
@pytest.mark.parametrize("method", ["Sift Flann", "Default"])
def test_real_sift_flann_recovers_translated_fixture_without_upstream_execution(method):
    template = textured(160, 160)
    cv2.putText(template, "OAS", (15, 75), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 0, 0), 4)
    image = np.zeros((300, 380, 3), np.uint8)
    image[70:230, 100:260] = template
    result = match_template(image, template, [50, 30, 280, 240], method=method)
    assert result.matched and result.good_matches >= 10 and result.score == -1
    assert abs(result.box[0] - 100) <= 1 and abs(result.box[1] - 70) <= 1
    assert result.box[2:] == (160, 160)


def test_unknown_method_never_silently_falls_back():
    template = textured()
    with pytest.raises(ValueError, match="Unsupported image matching method"):
        match_template(scene(template), template, method="Untranslated custom matcher")
