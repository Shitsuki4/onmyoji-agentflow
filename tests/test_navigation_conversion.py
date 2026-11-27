"""Navigation extraction is static and must not silently omit compound pages."""
from pathlib import Path

from onmyoji_agentflow.convert.navigation import read_navigation
from onmyoji_agentflow.convert.programs import build_catalog
from onmyoji_agentflow.yamlio import dump_yaml, load_yaml


def put(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_aliases_composites_hooks_keyword_edges_and_local_pages(tmp_path):
    put(tmp_path / "GameUi/default_pages.py", """
from tasks.GameUi.assets import GameUiAssets as G
page_main = Page(G.I_MAIN)
page_mall = Page(any_of(G.I_MALL, G.I_PURPLE), priority=75, cost=3)
page_mall.add_enter_success_hooks(conditional_action(G.I_OVERLAY, G.C_CLOSE), G.I_RED)
page_mall.connect(destination=page_main, action=G.I_BACK, cost=2, key='mall-out')
page_main.connect(page_mall, sequence(G.I_FIRST, G.C_SECOND, success_index=1))
""")
    put(tmp_path / "Demo/page.py", """
from tasks.Demo.assets import DemoAssets as D
page_demo = Page(all_of(D.I_A, not_(D.I_B)))
page_demo.connect(page_main, D.I_EXIT)
""")
    graph = read_navigation(tmp_path, {"GameUiAssets": "GameUi", "DemoAssets": "Demo"})
    assert set(graph["pages"]) == {"page_main", "page_mall", "page_demo"}
    assert graph["pages"]["page_mall"]["priority"] == 75
    assert graph["pages"]["page_mall"]["cost"] == 3
    assert len(graph["pages"]["page_mall"]["check"]["any"]) == 2
    hook = graph["pages"]["page_mall"]["hooks"]["enter_success"][0]
    assert hook["condition"] == {"task": "GameUi", "name": "I_OVERLAY"}
    edge = next(row for row in graph["links"] if row["key"] == "mall-out")
    assert edge["cost"] == 2 and edge["to"] == "page_main"
    assert next(row for row in graph["links"] if row["from"] == "page_main")["button"]["success_index"] == 1
    assert graph["pages"]["page_demo"]["check"]["all"][1] == {"not": {"task": "Demo", "name": "I_B"}}
    assert not graph["diagnostics"]


def test_unrecognised_page_expression_and_changed_inheritance_are_explicit(tmp_path):
    put(tmp_path / "GameUi/default_pages.py", """
page_main = Page(G.I_MAIN)
page_other = Page(custom_matcher(G.I_OTHER))
def inherit_transitions(source, target):
    raise RuntimeError('different semantics')
inherit_transitions(page_main, page_other)
page_other.remove_transition(key='something')
""")
    graph = read_navigation(tmp_path, {"G": "GameUi"})
    assert "unsupported" in graph["pages"]["page_other"]["check"]
    reasons = [row["reason"] for row in graph["diagnostics"]]
    assert "unsupported action factory" in reasons
    assert "transition inheritance implementation is not audited" in reasons
    assert "unsupported page mutation" in reasons


def test_arbitrary_module_statements_and_callable_actions_stay_inert(tmp_path):
    marker = tmp_path / "must-not-exist"
    put(tmp_path / "GameUi/default_pages.py", f"""
open({str(marker)!r}, 'w').write('executed')
raise RuntimeError('must never import this module')
page_main = Page(G.I_MAIN)
page_result = Page(G.I_RESULT)
def result_hook(task):
    return task.click(G.C_SAFE)
page_result.add_enter_success_hooks(result_hook, lambda task: random_click())
""")
    graph = read_navigation(tmp_path, {"G": "GameUi"})
    assert not marker.exists()
    assert "result_hook" in graph["pages"]["page_result"]["hooks"]["enter_success"][0]["callable"]["name"]
    assert "lambda" in graph["pages"]["page_result"]["hooks"]["enter_success"][1]["callable"]
    assert graph["functions"]["GameUi/default_pages.py:result_hook"]["source"].startswith("def result_hook")
    assert any("module statement" in row["reason"] for row in graph["diagnostics"])
    assert any("module call" in row["reason"] for row in graph["diagnostics"])


def test_catalog_includes_dynamic_page_modules_and_their_asset_dependencies(tmp_path):
    root = tmp_path / "source"
    put(root / "tasks/GotoMain/script_task.py", "from tasks.GameUi.game_ui import GameUi\nclass ScriptTask(GameUi): pass\n")
    put(root / "tasks/GameUi/game_ui.py", "class GameUi: pass\n")
    put(root / "tasks/Side/page.py", "from tasks.Side.assets import SideAssets\npage_side = Page(SideAssets.I_SIDE)\n")
    put(root / "tasks/Side/assets.py", "class SideAssets: pass\n")
    converted = tmp_path / "converted"
    for name in ("GameUi", "GotoMain", "Side"):
        put(converted / (name + ".yaml"), dump_yaml({"resources": {}}))
    build_catalog("oas", root, converted)
    entry = load_yaml(converted / "programs/index.yaml")["entries"][0]
    assert "tasks/Side/page.py" in entry["entry_files"]
    assert "tasks/Side/assets.py" in entry["files"]
    assert "Side.yaml" in entry["resource_files"]
    assert (converted / "programs/src/tasks/Side/assets.py.txt").is_file()


def test_runtime_unknown_closers_are_parsed_as_inert_source_data(tmp_path):
    put(tmp_path / "GameUi/default_pages.py", "page_main = Page(G.I_MAIN)\n")
    put(tmp_path / "GameUi/navigator.py", """
from tasks.GlobalGame.assets import GlobalGameAssets as GGA
class GameUi:
    DEFAULT_UNKNOWN_CLOSERS = [GGA.I_UI_BACK_RED, GGA.I_UI_CONFIRM]
    def dangerous(self):
        raise RuntimeError('inert')
""")
    graph = read_navigation(tmp_path, {"G": "GameUi", "GlobalGameAssets": "GlobalGame"})
    assert graph["unknown_closers"]["alternatives"][0] == {"task": "GlobalGame", "name": "I_UI_BACK_RED"}
    assert any(row["path"] == "tasks/GameUi/navigator.py" for row in graph["source_files"])
