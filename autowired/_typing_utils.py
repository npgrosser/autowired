from typing import Type, get_args, get_origin, Union, Any


def is_subtype(t1: Type, t2: Type) -> bool:
    """
    Checks if t1 is a subtype of t2.
    Similar to issubclass, but also works for generic types.

    Note that this is a simple implementation that does not take invariant type arguments into account.
    Meaning is_subtype(List[int], List[object]) will return True, although strictly speaking
    List[int] is not a subtype of List[object], since it is a mutable container and therefore invariant.

    :param t1:
    :param t2:
    :return:
    """

    if t1 is Any or t2 is Any:
        return True

    # both types are not generic -> we can use issubclass
    if get_origin(t1) is None and get_origin(t2) is None:
        return issubclass(t1, t2)

    origin1 = get_origin(t1) or t1
    origin2 = get_origin(t2) or t2

    # origin1 must not be Union
    if origin1 is Union:
        raise ValueError("Union types are not supported for the first argument")

    # union support: if origin2 is a union, check if t1 is a subtype of any of the union's types using recursion
    if origin2 is Union:
        return any(is_subtype(t1, arg) for arg in get_args(t2))

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
