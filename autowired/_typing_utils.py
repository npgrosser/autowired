from typing import Type, get_args, get_origin, Union, Any, Optional, List, Tuple

try:
    from types import UnionType
except ImportError:  # pragma: no cover
    UnionType = None


def is_subtype(t1: Type, t2: Type) -> bool:
    """
    Checks if t1 is a subtype of t2 (instances of t1 can be used where instances of t2 are expected).
    Similar to issubclass, but also works for generic types.

    Note that this is a simple implementation that does not take invariant type arguments into account.
    Meaning is_subtype(List[int], List[object]) will return True, although strictly speaking
    List[int] is not a subtype of List[object], since it is a mutable container and therefore invariant.

    :param t1:
    :param t2:
    :return:
    """

    # region union type support
    # union type similarity check rule: all types of t1 must be subtypes of at least one type of t2
    t1_union_types = _as_union_types(t1)
    t2_union_types = _as_union_types(t2)

    if len(t1_union_types) > 1 or len(t2_union_types) > 1:
        return all(
            any(is_subtype(t1_arg, t2_arg) for t2_arg in t2_union_types)
            for t1_arg in t1_union_types
        )
    # endregion

    if t1 is Any or t2 is Any:
        return True

    # both types are not generic -> we can use issubclass
    if get_origin(t1) is None and get_origin(t2) is None:
        return issubclass(t1, t2)

    origin1 = get_origin(t1) or t1
    origin2 = get_origin(t2) or t2

    # base condition: t1 must be a subclass of t2, otherwise we can already return False
    if not issubclass(origin1, origin2):
        return False

    # from now on t1 is a subclass of t2
    # -> we only need to check type arguments now

    # only the one type is generic -> we consider the argument to be Any
    #   -> t1 = t1[Any, Any, ...] and t2 = t2[x, y, ...]
    #   or t1 = t1[x, y, ...] and t2 = t2[Any, Any, ...]
    if get_origin(t1) is None or get_origin(t2) is None:
        return True

    args1 = get_args(t1)
    args2 = get_args(t2)

    # if one of the types has no type arguments, same as above
    if not args1 or not args2:
        return True

    # compare each of the type arguments recursively
    # as above,
    for arg1, arg2 in zip(args1, args2):
        if arg1 is Ellipsis or arg2 is Ellipsis:
            # again, handle as Any
            continue
        if not is_subtype(arg1, arg2):
            return False

    return True


def _as_union_types(t) -> Tuple[Type, ...]:
    """
    Returns the types of a Union type, or a tuple containing only t if t is not a Union type.
    """

    if get_origin(t) is Union:
        return get_args(t)

    if UnionType is not None:
        if get_origin(t) is UnionType:
            return get_args(t)

    return (t,)


def get_list_element_type(t: Type) -> Optional[Type]:
    """
    Returns the type of the elements of a list type, or None if t is not a list type.
    """
    origin = get_origin(t)
    if origin is list or origin is List:
        args = get_args(t)
        if args:
            return args[0]
    return None


def get_sequence_type(t: Type) -> Union[Tuple[Type, Type], Tuple[None, None]]:
    """
    Returns the type of the elements of a list type, or None if t is not a list type.
    """
    origin = get_origin(t)
    if origin is list or origin is List:
        args = get_args(t)
        if args:
            return list, args[0]

    if origin is tuple or origin is Tuple:
        args = get_args(t)
        if len(args) == 2 and args[1] is Ellipsis:
            return tuple, args[0]

    return None, None
