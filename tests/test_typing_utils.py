import sys

import pytest
from typing import List, Dict, Tuple, Union, Any, Set

# noinspection PyProtectedMember
from autowired._typing_utils import is_subtype, get_list_element_type


def test_non_generic_types():
    assert is_subtype(int, object) is True
    assert is_subtype(bool, int) is True
    assert is_subtype(Union[int, str], object) is True
    assert is_subtype(int, Union[int, str]) is True
    assert is_subtype(int, str) is False


def test_generic_with_non_generic():
    assert is_subtype(List[int], List) is True
    assert is_subtype(Dict, Dict[Any, Any]) is True


def test_generic_types():
    assert is_subtype(List[int], List[int]) is True
    assert (
        is_subtype(List[int], List[object]) is True
    )  # Not type-safe, but expected by the function's behavior
    assert is_subtype(Dict[str, int], Dict[object, object]) is True  # Same as above
    assert is_subtype(Tuple[int, ...], Tuple[object, ...]) is True  # Same as above
    assert is_subtype(Dict[str, int], Dict[str, str]) is False


def test_generic_types_with_different_lengths():
    assert is_subtype(Tuple[int, int], Tuple) is True
    assert is_subtype(Tuple, Tuple[Any, ...]) is True


def test_variant_generic_types():
    # For fully correct subtype checks, these should be False, but the
    # implementation as it stands will return True.
    assert is_subtype(List[int], List[object]) is True
    assert is_subtype(Dict[str, int], Dict[Any, Any]) is True


def test_complex_generic_types():
    assert (
        is_subtype(List[Dict[str, int]], List[Dict[object, object]]) is True
    )  # Not type-safe due to variance, but expected by the function's behavior
    assert (
        is_subtype(
            Dict[Tuple[int, str], List[int]],
            Dict[Tuple[object, object], List[object]],
        )
        is True
    )  # Same as above


def test_any_type():
    assert is_subtype(Any, int) is True
    assert is_subtype(int, Any) is True
    assert is_subtype(Any, List[int]) is True
    assert is_subtype(List[int], Any) is True
    assert is_subtype(Any, List) is True
    assert is_subtype(List, Any) is True
    assert is_subtype(Any, Any) is True
    assert is_subtype(List[int], List[Any]) is True
    assert is_subtype(Dict[Any, Any], Dict) is True


def test_inheritance():
    class MyBase:
        pass

    class MyDerived(MyBase):
        pass

    assert is_subtype(MyDerived, MyBase) is True
    assert is_subtype(MyBase, MyDerived) is False
    assert (
        is_subtype(List[MyDerived], List[MyBase]) is True
    )  # Not type-safe, but expected by the function's behavior


def test_mixed_generic_non_generic():
    assert is_subtype(List[int], List) is True
    assert is_subtype(List, List[int]) is True
    assert is_subtype(List[int], list) is True
    assert is_subtype(list, List[int]) is True

    assert is_subtype(List[int], Set) is False
    assert is_subtype(Set, List[int]) is False
    assert is_subtype(List[int], set) is False
    assert is_subtype(set, List[int]) is False


_version_info = sys.version_info
if _version_info.major >= 3 and _version_info.minor >= 10:
    new_union_syntax = [True, False]
else:
    new_union_syntax = [False]


@pytest.mark.parametrize("new_union_syntax", new_union_syntax)
def test_union_types(new_union_syntax: bool):
    def union(*args):
        if new_union_syntax:
            if len(args) == 1:
                return args[0]
            if len(args) == 2:
                return args[0] | args[1]
            if len(args) == 3:
                return args[0] | args[1] | args[2]
        else:
            return Union[args]

    # case 1: both types are unions
    # 1.1: same types
    assert is_subtype(union(int, str), union(int, str)) is True
    assert is_subtype(union(int, str), union(str, int)) is True
    # 1.2: all types in left are subtypes of at least one type in right
    assert is_subtype(union(int, str), union(object, str)) is True
    assert is_subtype(union(int, str), union(str, object)) is True
    # 1.3: not all types in left are subtypes of at least one type in right
    assert is_subtype(union(int, str), union(float, str)) is False
    assert is_subtype(union(int, str), union(str, float)) is False

    assert is_subtype(union(int, str), Any) is True

    # case 2: only the left type is union
    assert is_subtype(union(int, str), int) is False
    assert is_subtype(union(int, str), str) is False
    assert is_subtype(union(int, str), object) is True

    # case 3: only the right type is union
    assert is_subtype(int, union(int, str)) is True
    assert is_subtype(str, union(int, str)) is True
    assert is_subtype(float, union(int, str)) is False

    # case 4: one is Any
    assert is_subtype(Any, union(int, str)) is True
    assert is_subtype(union(int, str), Any) is True


def test_get_list_type():
    assert get_list_element_type(List[int]) == int
    assert get_list_element_type(List) is None
    assert get_list_element_type(List[object]) is object
    assert get_list_element_type(int) is None
