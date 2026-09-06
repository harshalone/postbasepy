from postbasepy._internal import (
    apply_aliases,
    parse_columns,
    parse_or_filter_string,
)


def test_parse_columns_no_alias():
    parsed = parse_columns("id, title, created_at")
    assert [p.col for p in parsed] == ["id", "title", "created_at"]
    assert [p.alias for p in parsed] == ["id", "title", "created_at"]


def test_parse_columns_with_alias():
    parsed = parse_columns("apis.id as api_id, apis.name, pricing_plans.id as plan_id")
    assert parsed[0].col == "apis.id"
    assert parsed[0].alias == "api_id"
    assert parsed[1].col == "apis.name"
    assert parsed[1].alias == "apis.name"
    assert parsed[2].col == "pricing_plans.id"
    assert parsed[2].alias == "plan_id"


def test_apply_aliases_renames_keys():
    parsed = parse_columns("apis.id as api_id, apis.name, pricing_plans.id as plan_id")
    rows = [{"api_id": "wrong", "id": "1", "name": "Foo", "plan_id": "2"}]
    # server response would key by bare column name; simulate that shape
    rows = [{"id": "1", "name": "Foo", "plan_id": "2"}]
    out = apply_aliases(rows, parsed)
    assert out == [{"api_id": "1", "name": "Foo", "plan_id": "2"}]


def test_apply_aliases_noop_without_alias():
    parsed = parse_columns("id, name")
    rows = [{"id": "1", "name": "Foo"}]
    assert apply_aliases(rows, parsed) == rows


def test_parse_or_filter_string_simple():
    filters = parse_or_filter_string("email.ilike.%alice%,name.ilike.%alice%")
    assert len(filters) == 2
    assert filters[0].column == "email"
    assert filters[0].operator == "ilike"
    assert filters[0].value == "%alice%"
    assert filters[1].column == "name"


def test_parse_or_filter_string_in_operator():
    filters = parse_or_filter_string("status.eq.active,status.in.(pending,review)")
    assert filters[0].value == "active"
    assert filters[1].operator == "in"
    assert filters[1].value == ["pending", "review"]


def test_parse_or_filter_string_booleans_and_null():
    filters = parse_or_filter_string("published.eq.true,archived.eq.false,deleted_at.eq.null")
    assert filters[0].value is True
    assert filters[1].value is False
    assert filters[2].value is None
