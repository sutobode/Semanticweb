"""VietHeritageLOD CLI dispatcher.

Mỗi subcommand tương ứng một Make target ở Section 30 (CLI Contract) của
PROJECT_SPEC.md. Logic thật của từng stage nằm trong module con của
``src/vietheritage/`` (registry, collector, normalization, identity, mapping,
rdf, linking, reasoning, validation, lpg, reporting); ``cli.py`` chỉ điều phối.
"""
from __future__ import annotations

import argparse
import sys


def _cmd_collect_sample(args: argparse.Namespace) -> int:
    from vietheritage.registry.collector import collect_sample

    return collect_sample()


def _cmd_collect(args: argparse.Namespace) -> int:
    from vietheritage.registry.collector import collect_full

    return collect_full()


def _cmd_normalize(args: argparse.Namespace) -> int:
    from vietheritage.normalization.normalizer import run as normalize_run

    return normalize_run(run_mode=args.run_mode)


def _cmd_resolve(args: argparse.Namespace) -> int:
    from vietheritage.identity.resolver import run as resolve_run

    return resolve_run(run_mode=args.run_mode)


def _cmd_map(args: argparse.Namespace) -> int:
    from vietheritage.mapping.mapper import run as map_run

    return map_run(run_mode=args.run_mode)


def _cmd_generate_rdf(args: argparse.Namespace) -> int:
    from vietheritage.rdf.generator import run as generate_rdf_run

    return generate_rdf_run(run_mode=args.run_mode)


def _cmd_link(args: argparse.Namespace) -> int:
    from vietheritage.linking.linker import run as link_run

    return link_run(run_mode=args.run_mode)


def _cmd_validate(args: argparse.Namespace) -> int:
    from vietheritage.validation.validator import run as validate_run

    return validate_run(run_mode=args.run_mode)


def _cmd_reason(args: argparse.Namespace) -> int:
    from vietheritage.reasoning.reasoner import run as reason_run

    return reason_run(run_mode=args.run_mode)


def _cmd_wait_fuseki(args: argparse.Namespace) -> int:
    from vietheritage.reporting.health import wait_fuseki

    return wait_fuseki()


def _cmd_fuseki_load(args: argparse.Namespace) -> int:
    from vietheritage.rdf.fuseki_loader import run as fuseki_load_run

    return fuseki_load_run(run_mode=args.run_mode)


def _cmd_linked_data_test(args: argparse.Namespace) -> int:
    from vietheritage.reporting.linked_data_test import run as linked_data_test_run

    return linked_data_test_run()


def _cmd_wait_neo4j(args: argparse.Namespace) -> int:
    from vietheritage.reporting.health import wait_neo4j

    return wait_neo4j()


def _cmd_neo4j_load(args: argparse.Namespace) -> int:
    from vietheritage.lpg.loader import run as neo4j_load_run

    return neo4j_load_run(run_mode=args.run_mode)


def _cmd_cypher_test(args: argparse.Namespace) -> int:
    from vietheritage.lpg.cypher_runner import run as cypher_test_run

    return cypher_test_run()


def _cmd_traceability_check(args: argparse.Namespace) -> int:
    from vietheritage.reporting.traceability import run as traceability_run

    return traceability_run()


def _cmd_query(args: argparse.Namespace) -> int:
    from vietheritage.reporting.query_runner import run_single

    return run_single(args.query)


def _cmd_cq_test(args: argparse.Namespace) -> int:
    from vietheritage.reporting.query_runner import run as cq_test_run

    return cq_test_run()


def _cmd_verify(args: argparse.Namespace) -> int:
    from vietheritage.reporting.verify import run as verify_run

    return verify_run(run_mode=args.run_mode)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="vietheritage")
    sub = parser.add_subparsers(dest="command", required=True)

    def add(name: str, handler, needs_run_mode: bool = False) -> None:
        p = sub.add_parser(name)
        if needs_run_mode:
            p.add_argument("--run-mode", default="sample", choices=["sample", "full"])
        p.set_defaults(handler=handler)

    add("collect-sample", _cmd_collect_sample)
    add("collect", _cmd_collect)
    add("normalize", _cmd_normalize, needs_run_mode=True)
    add("resolve", _cmd_resolve, needs_run_mode=True)
    add("map", _cmd_map, needs_run_mode=True)
    add("generate-rdf", _cmd_generate_rdf, needs_run_mode=True)
    add("link", _cmd_link, needs_run_mode=True)
    add("validate", _cmd_validate, needs_run_mode=True)
    add("reason", _cmd_reason, needs_run_mode=True)
    add("wait-fuseki", _cmd_wait_fuseki)
    add("fuseki-load", _cmd_fuseki_load, needs_run_mode=True)
    add("linked-data-test", _cmd_linked_data_test)
    add("wait-neo4j", _cmd_wait_neo4j)
    add("neo4j-load", _cmd_neo4j_load, needs_run_mode=True)
    add("cypher-test", _cmd_cypher_test)
    add("traceability-check", _cmd_traceability_check)

    p_query = sub.add_parser("query")
    p_query.add_argument("--query", required=True)
    p_query.set_defaults(handler=_cmd_query)

    add("cq-test", _cmd_cq_test)
    add("verify", _cmd_verify, needs_run_mode=True)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    sys.exit(main())
