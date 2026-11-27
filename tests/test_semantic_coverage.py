"""Source-independent obligation accounting, stale revisions and draft honesty."""
import copy
import hashlib
import json

import pytest

from onmyoji_agentflow.convert.coverage import (
    bind_manifest, candidate_digest, manifest_status, source_obligations,
)
from onmyoji_agentflow.yamlio import dump_yaml, load_yaml
from test_program_pipeline import app, job, reply  # shared isolated, device-forbidden fixture


def put(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture
def sources(tmp_path):
    entry = {"id": "oas:Example", "source": "oas", "kind": "task", "title": "Example",
             "workflow": "example", "fingerprint": "pinned", "commit": "upstream-revision",
             "files": ["tasks/Example/script_task.py", "tasks/Shared/helper.py"],
             "entry_files": ["tasks/Example/script_task.py"]}
    folder = tmp_path / "resources/upstream/oas/programs/src"
    put(folder / "tasks/Example/script_task.py.txt", """from tasks.Shared.helper import Base
class ScriptTask(Base):
    def run(self):
        if self.config.enabled:
            self.buy()
        else:
            self.stop()
""")
    put(folder / "tasks/Shared/helper.py.txt", """# MUST remain inert
raise RuntimeError('never execute this source')
class Base:
    limit = 3
    def buy(self):
        for _ in range(self.limit):
            self.click()
""")
    raw = {"format": 1, "name": "example", "states": [
        {"id": "buy", "when": {"text": "Purchase"}, "do": [{"click": [1, 1, 2, 2]}]},
        {"id": "done", "when": {"text": "Done"}, "do": [{"stop": "done"}]},
    ]}
    return entry, tmp_path, raw


def claimed(entry, inventory, raw, all_obligations=True):
    manifest = bind_manifest(entry, inventory, raw)
    selected = inventory["obligations"] if all_obligations else inventory["obligations"][:1]
    manifest["claims"] = [{"id": obligation["id"], "status": "implemented", "states": [raw["states"][0]["id"]],
                           "note": "Example mapping for review; this claim alone proves no equivalence"}
                          for obligation in selected]
    return manifest


def review_record(manifest):
    # An independent artifact: the proposal itself cannot submit this record.
    claims = sorted(manifest["claims"], key=lambda claim: claim["id"])
    digest = hashlib.sha256(json.dumps(claims, ensure_ascii=False, sort_keys=True,
                                      separators=(",", ":")).encode()).hexdigest()
    return {**{key: value for key, value in manifest.items() if key != "claims"},
            "claims_digest": digest, "semantic_complete": True,
            "review_note": "Fixture independently reviewed against the exact source and candidate"}


def test_inventory_includes_imported_implementation_config_and_each_branch(sources):
    entry, root, raw = sources
    inventory = source_obligations(entry, root)
    assert not inventory["errors"]
    assert any(item["path"].endswith("helper.py") and item["label"] == "buy"
               for item in inventory["obligations"])
    assert {"If.body", "If.orelse", "For.body"} <= {item["label"] for item in inventory["obligations"]}
    assert {"self.buy", "self.stop", "self.click"} <= {item["label"] for item in inventory["obligations"]}
    assert len({item["id"] for item in inventory["obligations"]}) == len(inventory["obligations"])
    assert inventory == source_obligations(entry, root)
    helper = root / "resources/upstream/oas/programs/src/tasks/Shared/helper.py.txt"
    helper.write_text(helper.read_text(encoding="utf-8").replace("limit = 3", "limit = 4"), encoding="utf-8")
    changed = source_obligations(entry, root)
    # Independent byte anchors invalidate coverage even if a caller reuses the catalog fingerprint.
    assert entry["fingerprint"] == "pinned" and changed["source_digest"] != inventory["source_digest"]
    assert changed["obligations_digest"] != inventory["obligations_digest"]


def test_unrecognized_ts_logic_is_retained_as_source_obligations(tmp_path):
    entry = {"id": "assttyys:func:999", "source": "assttyys", "kind": "component",
             "workflow": "component", "fingerprint": "pinned", "files": ["component.ts"]}
    put(tmp_path / "resources/upstream/assttyys/programs/src/component.ts.txt",
        "operatorFunc() {\n  unfamiliar?.dynamic('never execute');\n  return false;\n}\n")
    inventory = source_obligations(entry, tmp_path)
    assert not inventory["errors"]
    assert len(inventory["obligations"]) == 5  # entire file plus every nonempty source line
    assert {item["line"] for item in inventory["obligations"]} == {1, 2, 3, 4}


def test_returned_inventory_cannot_mutate_independent_cached_anchors(sources):
    entry, root, raw = sources
    first = source_obligations(entry, root)
    original = first["obligations"][0]["id"]
    first["obligations"][0]["id"] = "caller-forged"
    assert source_obligations(entry, root)["obligations"][0]["id"] == original


def test_expression_and_comprehension_branches_are_explicit_obligations(sources):
    entry, root, raw = sources
    put(root / "resources/upstream/oas/programs/src/tasks/Shared/helper.py.txt",
        "choice = buy() if enabled else skip()\nitems = [x for x in candidates if allowed(x)]\n")
    labels = {item["label"] for item in source_obligations(entry, root)["obligations"]}
    assert {"IfExp", "comprehension", "buy", "skip", "allowed"} <= labels


def test_resource_documents_and_images_are_independently_digest_bound(sources):
    entry, root, raw = sources
    entry["resource_files"] = ["recognition.yaml"]
    folder = root / "resources/upstream/oas"
    put(folder / "recognition.yaml", "resources:\n  page: {type: image, file: page.png}\n")
    (folder / "page.png").write_bytes(b"first image fixture")
    original = source_obligations(entry, root)
    assert not original["errors"]
    (folder / "page.png").write_bytes(b"changed image fixture")
    changed = source_obligations(entry, root)
    assert changed["source_digest"] != original["source_digest"]
    put(folder / "recognition.yaml", "resources:\n  page: {type: image, file: missing.png}\n")
    assert source_obligations(entry, root)["errors"]


@pytest.mark.parametrize("defect", ["missing", "outside", "syntax", "unlisted_entry", "missing_func"])
def test_source_defects_cannot_be_reviewed_away(sources, defect):
    entry, root, raw = sources
    if defect == "missing":
        entry["files"].append("missing.py")
    elif defect == "outside":
        entry["files"].append("../../../../outside.py")
    elif defect == "syntax":
        put(root / "resources/upstream/oas/programs/src/tasks/Shared/helper.py.txt", "def broken(\n")
    elif defect == "unlisted_entry":
        entry["entry_files"].append("unlisted.py")
    else:
        entry["missing_funcs"] = [24]
    inventory = source_obligations(entry, root)
    assert inventory["errors"]
    raw["coverage_manifest"] = claimed(entry, inventory, raw)
    put(root / "translations/coverage/example.json", json.dumps(review_record(raw["coverage_manifest"])))
    status = manifest_status(entry, inventory, raw, review_root=root)
    assert not status["mapping_complete"] and not status["semantic_complete"]
    assert status["gaps"]


def test_all_claims_are_only_mapped_until_independent_exact_review(sources):
    entry, root, raw = sources
    inventory = source_obligations(entry, root)
    raw["coverage_manifest"] = claimed(entry, inventory, raw)
    status = manifest_status(entry, inventory, raw, review_root=root)
    assert status["valid"] and status["mapping_complete"] and status["status"] == "mapped"
    assert not status["semantic_complete"] and status["gaps"]
    put(root / "translations/coverage/example.json", json.dumps(review_record(raw["coverage_manifest"])))
    reviewed = manifest_status(entry, inventory, raw, review_root=root)
    assert reviewed["semantic_complete"] and reviewed["status"] == "reviewed" and not reviewed["gaps"]
    # A digest-bound mapping change invalidates the independently stored review too.
    raw["coverage_manifest"]["claims"][0]["note"] += " changed"
    assert not manifest_status(entry, inventory, raw, review_root=root)["semantic_complete"]


def test_partial_and_blocked_obligations_never_count_as_complete(sources):
    entry, root, raw = sources
    inventory = source_obligations(entry, root)
    raw["coverage_manifest"] = claimed(entry, inventory, raw, all_obligations=False)
    raw["coverage_manifest"]["claims"].append({"id": inventory["obligations"][1]["id"],
        "status": "blocked", "states": [], "note": "Unsupported source effect remains explicit"})
    status = manifest_status(entry, inventory, raw)
    assert status["status"] == "partial" and status["mapped"] == 1 and status["blocked"] == 1
    assert status["unmapped"] == len(inventory["obligations"]) - 2
    assert not status["semantic_complete"]


@pytest.mark.parametrize("defect", ["unknown", "duplicate", "state", "no_states", "no_note", "waiver",
                                    "self_review", "source", "scope", "count", "revision", "empty"])
def test_forged_stale_and_malformed_manifests_fail_closed(sources, defect):
    entry, root, raw = sources
    inventory = source_obligations(entry, root)
    manifest = claimed(entry, inventory, raw)
    if defect == "unknown":
        manifest["claims"][0]["id"] = "invented source obligation"
    elif defect == "duplicate":
        manifest["claims"].append(copy.deepcopy(manifest["claims"][0]))
    elif defect == "state":
        manifest["claims"][0]["states"] = ["invented_state"]
    elif defect == "no_states":
        manifest["claims"][0]["states"] = []
    elif defect == "no_note":
        manifest["claims"][0]["note"] = " "
    elif defect == "waiver":
        manifest["claims"][0]["status"] = "not_applicable"
    elif defect == "self_review":
        manifest["semantic_complete"] = True
    elif defect == "source":
        manifest["source_digest"] = "forged"
    elif defect == "scope":
        manifest["scope"]["variant"] = "smaller_scope"
    elif defect == "count":
        manifest["obligation_count"] = True
    elif defect == "revision":
        raw["states"][0]["do"][0]["click"] = [5, 5, 6, 6]
    else:
        manifest = {}
    raw["coverage_manifest"] = manifest
    status = manifest_status(entry, inventory, raw, review_root=root)
    assert status["status"] == "invalid" and not status["valid"] and not status["semantic_complete"]
    assert status["gaps"]


def test_scoped_review_cannot_certify_parent_or_source_update(sources):
    entry, root, raw = sources
    scoped = {**entry, "id": "oas:Example#limited", "variant": "limited", "scope_description": "One branch"}
    inventory = source_obligations(scoped, root)
    raw["coverage_manifest"] = claimed(scoped, inventory, raw)
    put(root / "translations/coverage/example.json", json.dumps(review_record(raw["coverage_manifest"])))
    assert manifest_status(scoped, inventory, raw, review_root=root)["semantic_complete"]
    parent = manifest_status(entry, source_obligations(entry, root), raw, review_root=root)
    assert parent["status"] == "invalid" and not parent["semantic_complete"]
    changed = {**scoped, "fingerprint": "new-source-fingerprint"}
    assert not manifest_status(changed, source_obligations(changed, root), raw, review_root=root)["semantic_complete"]


def persisted(app, change_id):
    change = app.store.query("SELECT * FROM changes WHERE id=?", (change_id,))[0]
    entry = app.programs.source(job(app)["id"])["entry"]
    blob = app.ws.read_bytes(f"workflows/{entry['workflow']}.yaml", change["commit_id"])
    return entry, change, load_yaml(blob)


def test_legacy_draft_persists_unmapped_manifest_and_retains_gaps(app, monkeypatch):
    before = app.ws.head()
    result = app.programs.propose(job(app)["id"], reply())
    assert result["status"] == "waiting_user" and app.ws.head() == before
    entry, change, raw = persisted(app, result["change_id"])
    assert raw["coverage_manifest"]["candidate_digest"] == candidate_digest(raw)
    assert raw["coverage_manifest"]["claims"] == []
    validation = json.loads(change["validation"])
    assert not validation["semantic_coverage"]["semantic_complete"]
    original_list = app.programs.list
    monkeypatch.setattr(app.programs, "list", lambda **kwargs: [row for row in original_list(**kwargs)
        if row["entry_id"] == entry["id"]])
    audit = app.programs.audit()
    row, = audit["entries"]
    assert row["translation_available"] and row["coverage"] == "draft" and row["gaps"]
    assert row["candidate_commit"] == change["commit_id"]
    assert audit["summary"]["original_tasks_converted"] == 0
    assert audit["summary"]["all_original_tasks_converted"] is False


def test_stale_external_manifest_does_not_replace_pending_draft(app):
    first = app.programs.propose(job(app)["id"], reply())
    entry = app.programs.source(job(app)["id"])["entry"]
    data = reply()
    inventory = source_obligations(entry, app.ws.path)
    data["coverage_manifest"] = claimed(entry, inventory, data["workflow"])
    data["workflow"]["states"][0]["do"][-1]["stop"]["reason"] = "edited after mapping"
    second = app.programs.propose(job(app)["id"], data, replace_pending=True)
    assert second["status"] == "blocked" and "candidate_digest" in second["message"]
    assert job(app)["change_id"] == first["change_id"] and job(app)["status"] == "waiting_user"


def test_complete_mapping_requires_review_in_pinned_base_not_live_workspace(app):
    entry = app.programs.source(job(app)["id"])["entry"]
    data = reply()
    inventory = source_obligations(entry, app.ws.path)
    data["coverage_manifest"] = claimed(entry, inventory, data["workflow"])
    proposed = app.programs.propose(job(app)["id"], data)
    assert proposed["status"] == "waiting_user"
    entry, change, raw = persisted(app, proposed["change_id"])
    assert raw["coverage_manifest"]["candidate_digest"] == candidate_digest(raw)
    review_path = f"translations/coverage/{entry['workflow']}.json"
    put(app.ws.path / review_path, json.dumps(review_record(raw["coverage_manifest"])))
    row = next(row for row in app.programs.audit()["entries"] if row["entry_id"] == entry["id"])
    assert row["semantic_coverage"]["mapping_complete"] and not row["semantic_complete"]
    app.ws.git("add", "--", review_path)
    app.ws.git("commit", "-qm", "fixture independent semantic review")
    app.programs.index(app.ws.path, "main")
    row = next(row for row in app.programs.audit()["entries"] if row["entry_id"] == entry["id"])
    assert row["coverage"] == "task" and row["semantic_complete"] and not row["gaps"]
    # Semantic review is not workflow activation, approval or live verification.
    assert job(app)["status"] == "waiting_user" and not row["live_verified"]
    assert not app.ws.workflow_path(entry["workflow"]).exists()


def test_audit_detects_changed_candidate_even_with_matching_source_metadata(app):
    proposed = app.programs.propose(job(app)["id"], reply())
    entry, change, raw = persisted(app, proposed["change_id"])
    raw["states"][0]["do"][-1]["stop"]["reason"] = "tampered revision"
    branch, commit = app.ws.propose(entry["workflow"], "workflow",
        {f"workflows/{entry['workflow']}.yaml": dump_yaml(raw)}, "fixture changed candidate",
        base=change["commit_id"], prefix="coverage-test")
    app.store.execute("UPDATE changes SET branch=?,commit_id=? WHERE id=?", (branch, commit, proposed["change_id"]))
    row = next(row for row in app.programs.audit()["entries"] if row["entry_id"] == entry["id"])
    assert row["translation_available"] and row["coverage"] == "draft" and row["gaps"]
    assert row["semantic_coverage"]["status"] == "invalid" and not row["semantic_complete"]


def test_unreadable_candidate_does_not_abort_other_audit_entries(app):
    proposed = app.programs.propose(job(app)["id"], reply())
    entry, change, raw = persisted(app, proposed["change_id"])
    branch, commit = app.ws.propose(entry["workflow"], "workflow",
        {f"workflows/{entry['workflow']}.yaml": "states: [ malformed yaml"},
        "fixture malformed candidate", base=change["commit_id"], prefix="coverage-malformed")
    app.store.execute("UPDATE changes SET branch=?,commit_id=? WHERE id=?", (branch, commit, proposed["change_id"]))
    audit = app.programs.audit()
    assert len(audit["entries"]) == 2 and audit["summary"]["original_tasks_converted"] == 0
    row = next(row for row in audit["entries"] if row["entry_id"] == entry["id"])
    assert any("候选内容不可读" in gap for gap in row["gaps"]) and not row["semantic_complete"]


@pytest.mark.parametrize("guarded", [True, False])
def test_navigate_proposal_is_input_and_requires_mandatory_outer_visual_guard(app, guarded):
    data = reply()
    data["workflow"].update({"vars": {"arrived": 0}, "navigation": {"format": 1,
        "pages": {"home": {"when": {"text": "Home"}}}, "links": []}})
    data["workflow"]["states"][0].update({
        "when": {"text": "Home"} if guarded else {"any": [{"expr": "True"}, {"text": "Home"}]},
        "do": [{"navigate": {"destination": "home", "done_var": "arrived"}}]})
    result = app.programs.propose(job(app)["id"], data)
    if guarded:
        assert result["status"] == "waiting_user"
        assert app.programs.audit()["summary"]["original_tasks_converted"] == 0
    else:
        assert result["status"] == "blocked" and "正向画面" in result["message"]
        assert not app.store.query("SELECT * FROM changes")
