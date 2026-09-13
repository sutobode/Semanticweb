"""G0 smoke test — xác nhận CLI dispatcher dựng được và có đủ subcommand.

Đây là test đầu tiên của repository, tồn tại để make test không FAIL vì
'no tests collected' ngay từ Gate G0. Test logic thật của từng stage sẽ
được thêm ở Gate tương ứng (G3 collector, G4 normalizer, v.v.).
"""
from vietheritage.cli import build_parser


def test_cli_parser_builds() -> None:
    parser = build_parser()
    assert parser.prog == "vietheritage"


def test_cli_has_all_make_target_subcommands() -> None:
    parser = build_parser()
    subparsers_action = next(
        action
        for action in parser._actions
        if action.dest == "command"
    )
    expected = {
        "collect-sample",
        "collect",
        "normalize",
        "resolve",
        "map",
        "generate-rdf",
        "link",
        "validate",
        "reason",
        "wait-fuseki",
        "fuseki-load",
        "linked-data-test",
        "wait-neo4j",
        "neo4j-load",
        "cypher-test",
        "traceability-check",
        "query",
        "cq-test",
        "verify",
    }
    assert expected.issubset(set(subparsers_action.choices.keys()))
