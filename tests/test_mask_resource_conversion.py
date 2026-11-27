import json

import cv2
import numpy as np

from onmyoji_agentflow.convert.oas import convert_task
from onmyoji_agentflow.convert.coverage import source_obligations
from onmyoji_agentflow.workflow.schema import load_resource_file
from onmyoji_agentflow.yamlio import dump_yaml, load_yaml


def test_masked_source_method_and_optional_mask_are_preserved(tmp_path):
    source = tmp_path / "Demo/resource"
    source.mkdir(parents=True)
    image = np.random.default_rng(7).integers(0, 255, (20, 20, 3), dtype=np.uint8)
    cv2.imencode(".png", image)[1].tofile(str(source / "asset.png"))
    cv2.imencode(".png", np.ones((20, 20), np.uint8) * 255)[1].tofile(str(source / "asset_mask.png"))
    (source / "image.json").write_text(json.dumps([{"itemName": "asset", "imageName": "asset.png",
        "roiFront": "20,30,20,20", "roiBack": "10,20,40,40", "method": "Masked template matching"}]), encoding="utf-8")
    output = tmp_path / "converted"
    report = convert_task(source.parent, output, "Demo")
    spec = load_yaml(output / "Demo.yaml")["resources"]["I_ASSET"]
    assert report["images"] == 2
    assert spec["method"] == "Masked template matching" and spec["roi_expand"] == 2
    assert (output / spec["mask_file"]).is_file()
    loaded = load_resource_file(output / "Demo.yaml")["I_ASSET"]
    assert loaded["mask_path"].endswith("asset_mask.png")


def test_mask_bytes_are_part_of_independent_source_binding(tmp_path):
    folder = tmp_path / "resources/upstream/oas"
    folder.mkdir(parents=True)
    source = folder / "programs/src/tasks/Demo/script_task.py.txt"
    source.parent.mkdir(parents=True)
    source.write_text("def run(): pass\n", encoding="utf-8")
    (folder / "page.png").write_bytes(b"image fixture")
    (folder / "mask.png").write_bytes(b"mask fixture")
    (folder / "Demo.yaml").write_text(dump_yaml({"resources": {"page": {
        "type": "image", "file": "page.png", "mask_file": "mask.png"}}}), encoding="utf-8")
    entry = {"id": "oas:Demo", "source": "oas", "kind": "task", "fingerprint": "same",
             "files": ["tasks/Demo/script_task.py"], "resource_files": ["Demo.yaml"]}
    before = source_obligations(entry, tmp_path)
    (folder / "mask.png").write_bytes(b"changed mask")
    assert source_obligations(entry, tmp_path)["source_digest"] != before["source_digest"]
