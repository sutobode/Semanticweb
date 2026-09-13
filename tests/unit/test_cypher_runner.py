from decimal import Decimal

from vietheritage.lpg.cypher_runner import _normalize_value


def test_normalize_float_preserves_coordinate_precision() -> None:
    assert _normalize_value(21.3682242) == "21.3682242"
    assert _normalize_value(105.3214424) == "105.3214424"


def test_normalize_decimal_lexical_form_is_stable() -> None:
    assert _normalize_value({"value": "20.9000"}) == "20.9"
    assert _normalize_value(Decimal("105.32144240")) == "105.3214424"
