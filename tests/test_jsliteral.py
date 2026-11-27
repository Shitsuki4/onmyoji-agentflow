import pytest

from onmyoji_agentflow.convert.jsliteral import extract_literal_after, find_consts, parse


def test_parse_values():
    src = """[{ // comment
        desc: [1280, 720, [[left, 1, 2, 0xF3CC8A], [center, 3, 4, 0x000000],]],
        oper: [[center, 1280, 720, 429 + 10, 855 - 5, -1, 1000]],
        'quoted': "s\\"x", flag: true, none: undefined,
    }]"""
    v = parse(src, {"left": 0, "center": 1})
    assert v[0]["desc"][2][0] == [0, 1, 2, 0xF3CC8A]
    assert v[0]["oper"][0][3:5] == [439, 850]
    assert v[0]["oper"][0][5] == -1
    assert v[0]["quoted"] == 's"x' and v[0]["flag"] is True and v[0]["none"] is None


def test_rejects_code():
    with pytest.raises(ValueError):
        parse("[foo(1)]")
    with pytest.raises(ValueError):
        parse("[x => 1]")


def test_whole_literal_and_arithmetic_precedence():
    assert parse("[10 + 2 * 3, 10 - 2 * 3]") == [16, 4]
    assert parse("[] /* only a comment */") == []
    for text in ("[]; dangerous()", "{} + arbitrary", "[1", "{value: 1"):
        with pytest.raises(ValueError):
            parse(text)


def test_extract_and_consts():
    src = "const left = 0;\n// const right = 2;\nexport const a: IFoo = { k: [1, ']', 2] };"
    lit, end = extract_literal_after(src, r"a\s*:\s*\w+\s*=")
    assert parse(lit) == {"k": [1, "]", 2]}
    assert find_consts(src) == {"left": 0}
