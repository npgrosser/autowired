from threading import local, Lock
from typing import Any, Callable, Optional, Type, TypeVar, Union

T = TypeVar("T")


# noinspection PyPep8Naming
class thread_local_cached_property:
    def __init__(self, func: Callable[[Any], T]):
        self.func: Callable[[Any], T] = func
        self.attr_name: Optional[str] = None
        self.__doc__: Optional[str] = func.__doc__
        self.lock: Lock = Lock()

    def __set_name__(self, owner: Type[Any], name: str) -> None:
        if self.attr_name is None:
            self.attr_name = name
        elif name != self.attr_name:
            raise TypeError(
                f"Cannot assign the same {type(self).__name__} to two different names "
                f"({self.attr_name!r} and {name!r})."
            )

    def __get__(
        self, instance: Any, owner: Optional[Type[Any]] = None
    ) -> Union[T, "thread_local_cached_property"]:
        if instance is None:
            return self
        if self.attr_name is None:
            raise TypeError(
                f"Cannot use {type(self).__name__}  instance without calling __set_name__ on it."
            )

        with self.lock:
            if not hasattr(instance, "__local_dict__"):
                instance.__local_dict__ = local()
            cache = instance.__local_dict__

            if not hasattr(cache, self.attr_name):
                setattr(cache, self.attr_name, self.func(instance))

        return getattr(cache, self.attr_name)
