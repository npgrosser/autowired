import pytest
from typing import List, Dict, Tuple, Union, Any, Set

# noinspection PyProtectedMember
from autowired._typing_utils import is_subtype


def test_non_generic_types():
    assert is_subtype(int, object) is True
    assert is_subtype(bool, int) is True
    with pytest.raises(ValueError):
        is_subtype(Union[int, str], object)
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
