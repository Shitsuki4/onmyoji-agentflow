"""CI: check the answers `oaf mcp` (stdio) gave to the smoke-test requests. Not a pytest module."""
import json
import sys

lines = [json.loads(x) for x in open(sys.argv[1], encoding="utf-8").read().splitlines() if x.strip()]
by_id = {m["id"]: m for m in lines if "id" in m}
assert set(by_id) == {1, 2, 3, 4}, by_id.keys()
assert by_id[1]["result"]["serverInfo"]["name"] == "onmyoji-agentflow", by_id[1]
tools = {t["name"] for t in by_id[2]["result"]["tools"]}
assert {"run_workflow", "approve", "set_config", "sync", "screenshot"} <= tools, tools
wfs = json.loads(by_id[3]["result"]["content"][0]["text"])["workflows"]
assert "orochi" in {w["name"] for w in wfs}, wfs
budget = json.loads(by_id[4]["result"]["content"][0]["text"])["value"]
assert all(v is None for v in budget.values()), budget
print(f"MCP stdio OK: {len(tools)} tools, {len(wfs)} workflows, llm.budget unlimited")
