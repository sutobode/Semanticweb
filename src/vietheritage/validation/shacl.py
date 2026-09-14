"""SHACL validation for the public asserted RDF graph."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pyshacl import validate
from rdflib import Graph

REPO_ROOT = Path(__file__).resolve().parents[3]
SHAPES_PATH = REPO_ROOT / "shapes" / "vietheritage.shacl.ttl"


def validate_graph(data_path: Path, shapes_path: Path = SHAPES_PATH) -> tuple[bool, str, Graph]:
    data_graph = Graph().parse(data_path, format="turtle")
    shapes_graph = Graph().parse(shapes_path, format="turtle")
    conforms, results_graph, results_text = validate(
        data_graph=data_graph,
        shacl_graph=shapes_graph,
        inference="none",
        abort_on_first=False,
        allow_infos=True,
        allow_warnings=True,
        advanced=True,
    )
    return bool(conforms), str(results_text), results_graph


def run(run_mode: str = "sample", data_path: Path | None = None, metadata_path: Path | None = None) -> int:
    data = data_path or (REPO_ROOT / "data" / "rdf" / "vietheritage.ttl")
    metadata = metadata_path or (REPO_ROOT / "data" / "rdf" / "dataset-metadata.ttl")
    out = REPO_ROOT / "reports" / run_mode
    out.mkdir(parents=True, exist_ok=True)
    paths = {"asserted": data, "metadata": metadata}
    missing = [name for name, path in paths.items() if not path.exists()]
    if missing or not SHAPES_PATH.exists():
        report = {"status": "FAIL", "conforms": False, "errors": [f"SHACL artifact missing: {', '.join(missing or ['shapes'])}"]}
        (out / "shacl.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"shacl ({run_mode}): FAIL")
        return 1
    reports: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    for name, path in paths.items():
        try:
            conforms, results_text, results_graph = validate_graph(path)
            reports[name] = {"conforms": conforms, "result_triples": len(results_graph), "results_text": results_text, "data": str(path)}
            if not conforms:
                errors.append(f"{name}: SHACL_CONSTRAINT_VIOLATION")
        except Exception as exc:
            reports[name] = {"conforms": False, "data": str(path), "errors": [str(exc)]}
            errors.append(f"{name}: {exc}")
    report = {"status": "PASS" if not errors else "FAIL", "conforms": not errors, "shapes": str(SHAPES_PATH), "graphs": reports, "errors": errors}
    (out / "shacl.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"shacl ({run_mode}): {report['status']}")
    return 0 if report["status"] == "PASS" else 1
