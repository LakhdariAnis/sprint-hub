"""Trim a real graphify graph.json to a few files, for the contract test.

cd tests/fixtures/graphify && uv run python trim.py <path>/graph.json > graph.json
"""

import json
import sys

FILES = {"src/split.py", "src/test_held_out.py", "src/envelope_features.py", "src/test_envelope.py",
         "src/load_data.py", "src/windowing.py", "src/test_combined.py"}  # fmt: skip

graph = json.load(open(sys.argv[1]))
keep = {n["id"] for n in graph["nodes"] if n.get("source_file") in FILES}
links = [link for link in graph["links"] if link["source"] in keep]
keep |= {link["target"] for link in links}  # the libraries and nodes they point to
graph["nodes"] = [n for n in graph["nodes"] if n["id"] in keep]
graph["links"] = [link for link in graph["links"] if {link["source"], link["target"]} <= keep]
json.dump(graph, sys.stdout, indent=1)
