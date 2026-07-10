"""Fixture tests for indexer.parse.

Every expected value below was verified against the real 272-row census file
(.planning/phases/01-foundation-data-indexer/01-RESEARCH.md, "Known fixture
rows"). Comments cite the census ids that make each edge case REAL data.
"""
from indexer.parse import name_key, parse_price, parse_rating_positive, parse_sold

# A stand-in for the 493-1245 char description paragraphs that 4 real rows
# (ids 2169, 3091, 3092, 4188) carry in their `positive` column.
PARAGRAPH = "long paragraph description text here"


# --- parse_sold -------------------------------------------------------------

def test_parse_sold_plain():
    assert parse_sold("539 sold") == 539  # id 3345


def test_parse_sold_plain_census_max():
    assert parse_sold("547 sold") == 547  # id 2023 (highest plain count in census)


def test_parse_sold_k_suffix():
    assert parse_sold("1.55K sold") == 1550  # id 3118 CoinWM Open API


def test_parse_sold_k_suffix_second_real_row():
    assert parse_sold("1.37K sold") == 1370  # id 2013 CoinAnk OpenAPI


def test_parse_sold_zero():
    assert parse_sold("0 sold") == 0  # 150 census rows


def test_parse_sold_lowercase_k():
    assert parse_sold("1.55k sold") == 1550


def test_parse_sold_m_suffix():
    assert parse_sold("3M sold") == 3_000_000


def test_parse_sold_comma_grouped():
    assert parse_sold("2,500 sold") == 2500


def test_parse_sold_blank_is_zero():
    assert parse_sold("") == 0  # locked rule: missing/blank -> 0


def test_parse_sold_whitespace_only_is_zero():
    assert parse_sold("   ") == 0


def test_parse_sold_prose_returns_none():
    # id 4137: the sold cell holds a 417-char English paragraph.
    # fullmatch fails -> None; the caller stores 0 and logs a warning.
    prose = (
        "ASP Market Competition Intelligence - analyzes marketplace listings, "
        "pricing tiers, and competitor positioning so agent builders know "
        "where to launch."
    )
    assert parse_sold(prose) is None


# --- parse_price ------------------------------------------------------------

def test_parse_price_plain():
    assert parse_price("0.01 USDT") == 0.01  # id 3345


def test_parse_price_small_decimal():
    assert parse_price("0.002 USDT") == 0.002  # id 3118


def test_parse_price_integer():
    assert parse_price("1 USDT") == 1.0


def test_parse_price_census_max():
    assert parse_price("50 USDT") == 50.0


def test_parse_price_zero():
    assert parse_price("0.00 USDT") == 0.0  # 8 census rows


def test_parse_price_subscript_four():
    # id 2023: subscript 4 = FOUR zeros TOTAL after the decimal point
    # (the displayed literal 0 is stylistic, NOT an extra zero).
    assert parse_price("0.0₄15 USDT") == 0.000015


def test_parse_price_subscript_five():
    # ids 1851/2088/2087/1888: 0.0₅1 -> 0.000001 (never the 10x off-by-one)
    assert parse_price("0.0₅1 USDT") == 0.000001


def test_parse_price_blank_is_none():
    assert parse_price("") is None  # 28 real rows have an empty price


def test_parse_price_unrecognized_is_none():
    assert parse_price("free") is None


# --- parse_rating_positive (rule A) ------------------------------------------

def test_rating_rule_a_rated_with_pct():
    # id 3345 这个能吃吗？: genuinely rated
    assert parse_rating_positive("5.0", "100% positive", "0.01 USDT") == (5.0, 100.0)


def test_rating_rule_a_decimal_pct():
    # id 2023 Onchain Data Explorer
    assert parse_rating_positive("4.9", "92.86% positive", "0.0₄15 USDT") == (4.9, 92.86)


def test_rating_rule_a_price_echo_decimal():
    # id 2013 CoinAnk: rating cell '0.01' is the price echoed, positive empty
    assert parse_rating_positive("0.01", "", "0.01 USDT") == (None, None)


def test_rating_rule_a_price_echo_that_looks_like_perfect_rating():
    # id 4489 OK 飞行: '5' with empty positive is the 5 USDT price echo,
    # NOT a five-star rating (would pass a naive 0-5 range check)
    assert parse_rating_positive("5", "", "5 USDT") == (None, None)


def test_rating_rule_a_price_echo_half():
    # id 4137: echo '0.5' of '0.5 USDT'
    assert parse_rating_positive("0.5", "", "0.5 USDT") == (None, None)


def test_rating_rule_a_paragraph_positive_with_real_rating():
    # id 2169 FundingArb: positive holds a paragraph; rating 5.0 != price
    # token '1' -> rating kept, pct None
    assert parse_rating_positive("5.0", PARAGRAPH, "1 USDT") == (5.0, None)


def test_rating_rule_a_paragraph_positive_with_price_echo():
    # id 3091 八字精批: paragraph positive, rating '1' == price token '1' -> echo
    assert parse_rating_positive("1", PARAGRAPH, "1 USDT") == (None, None)


def test_rating_rule_a_all_empty():
    # 22 census rows have rating, positive, and price all empty
    assert parse_rating_positive("", "", "") == (None, None)


def test_rating_rule_a_rated_agent_with_empty_price():
    # id 2791 链上任务助手: 6 rated agents have an EMPTY price cell —
    # empty price must never suppress a genuine rating
    assert parse_rating_positive("5.0", "100% positive", "") == (5.0, 100.0)


def test_rating_rule_a_out_of_range_rating_pct_still_parses():
    assert parse_rating_positive("7.5", "100% positive", "1 USDT") == (None, 100.0)


def test_rating_rule_a_non_numeric_rating_pct_still_parses():
    assert parse_rating_positive("abc", "100% positive", "1 USDT") == (None, 100.0)


def test_rating_rule_a_pct_requires_space_before_positive():
    # Strict fullmatch: every valid row in the real file uses 'N% positive'
    # (with the space). Missing space -> pct None; rating gate still passes
    # because positive is non-empty and '4.9' is not the price token.
    rating, pct = parse_rating_positive("4.9", "92.86%positive", "1 USDT")
    assert pct is None
    assert rating == 4.9


# --- name_key ----------------------------------------------------------------

def test_name_key_folds_fullwidth_question_mark():
    # id 3345: NFKC folds U+FF1F '？' to ASCII '?'
    assert name_key("这个能吃吗？") == "这个能吃吗?"


def test_name_key_casefolds_ascii():
    assert name_key("AlphaCopy") == "alphacopy"  # id 1500


def test_name_key_middle_dot_preserved_casefold_collides():
    # ids 4517/4353: NFKC keeps U+00B7 '·'; casefold makes the pair collide —
    # which is why name_key must NOT be UNIQUE in the schema
    assert name_key("人生说明书 · Life Book") == name_key("人生说明书 · life book")


def test_name_key_strips_whitespace():
    assert name_key(" Padded ") == "padded"
