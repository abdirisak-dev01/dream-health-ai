from decimal import Decimal

import pytest

from app.meals.text_parser import parse_line, split_lines


def test_split_lines():
    assert split_lines("150 g chicken, 1 cup rice and 2 eggs; 1 banana\n1 apple") == [
        "150 g chicken", "1 cup rice", "2 eggs", "1 banana", "1 apple"]


def test_decimal_comma_is_not_a_separator():
    assert split_lines("1,5 cups rice, 2 eggs") == ["1,5 cups rice", "2 eggs"]


@pytest.mark.parametrize("line,qty,unit,food", [
    ("150 g chicken breast", "150", "g", "chicken breast"),
    ("150g chicken breast", "150", "g", "chicken breast"),
    ("1.5 cups rice", "1.5", "cup", "rice"),
    ("1,5 cups rice", "1.5", "cup", "rice"),
    ("1/2 cup oats", "0.5", "cup", "oats"),
    ("1 1/2 cup oats", "1.5", "cup", "oats"),
    ("2 eggs", "2", None, "eggs"),
    ("a cup of milk", "1", "cup", "milk"),
    ("half cup rice", "0.5", "cup", "rice"),
    ("2 tablespoons olive oil", "2", "tbsp", "olive oil"),
    ("8 oz salmon", "8", "oz", "salmon"),
    ("2 slices bread", "2", "slice", "bread"),
])
def test_parse_line(line, qty, unit, food):
    p = parse_line(line)
    assert p.problem is None
    assert p.quantity == Decimal(qty)
    assert p.unit == unit
    assert p.food_query == food


@pytest.mark.parametrize("line,problem", [
    ("chicken", "quantity_missing"),
    ("some rice", "quantity_missing"),
    ("150 g", "food_missing"),
    ("1/0 cup rice", "quantity_invalid"),
])
def test_parse_problems(line, problem):
    assert parse_line(line).problem == problem


@pytest.mark.parametrize("text,lines", [
    ("i eat 150g of chicj 200g of rice", ["150g of chicj", "200g of rice"]),
    ("For lunch I had 1 cup rice and 2 eggs", ["1 cup rice", "2 eggs"]),
    ("I just ate a banana", ["a banana"]),
    ("150 g chicken 1 1/2 cup oats", ["150 g chicken", "1 1/2 cup oats"]),  # mixed number stays whole
])
def test_everyday_sentences(text, lines):
    assert split_lines(text) == lines


def test_has_any_amount():
    from app.meals.text_parser import has_any_amount
    assert has_any_amount("i had 2 eggs")
    assert has_any_amount("a banana")
    assert not has_any_amount("hi")
    assert not has_any_amount("what should I eat?")
