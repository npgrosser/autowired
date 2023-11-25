import importlib
import inspect
import pkgutil
import sys
from dataclasses import dataclass
from typing import Type, Iterable, Set, Optional

Module = type(sys)


@dataclass
class ClassComponentInfo:
    cls: Type
    transient: bool = False


def component(cls=None, *, transient: bool = False):
    def wrap_class(cls_to_wrap):
        cls_to_wrap._component_info = ClassComponentInfo(cls_to_wrap, transient)
        return cls_to_wrap

    if cls is None:
        # The decorator has been called like @component(transient=True)
        # Return the wrapper function to apply later with the class
        return wrap_class
    else:
        # The decorator has been called like @component without parentheses
        # Apply the wrapper function directly to the class
        return wrap_class(cls)


def get_component_info(cls) -> Optional[ClassComponentInfo]:
    return getattr(cls, "_component_info", None)


class ClassScanner:
    def __init__(self, root_module: Module):
        if not inspect.ismodule(root_module):
            raise TypeError(f"Expected a module, got {type(root_module)}")
        self.root_module = root_module

    def _get_classes(self) -> Iterable[Type]:
        for name, cls in inspect.getmembers(self.root_module, inspect.isclass):
            if cls.__module__ == self.root_module.__name__:
                yield cls

        path = self.root_module.__path__
        prefix = self.root_module.__name__ + "."

        for importer, modname, is_pkg in pkgutil.walk_packages(path, prefix):
            sub_module = importlib.import_module(modname)
            for name, cls in inspect.getmembers(sub_module, inspect.isclass):
                if cls.__module__ == sub_module.__name__:
                    yield cls

    def get_classes(self) -> Iterable[Type]:
        seen: Set[str] = set()

        def cls_to_key(cls: Type) -> str:
            return f"{cls.__module__}.{cls.__name__}"

        for cls in self._get_classes():
            key = cls_to_key(cls)
            if key not in seen:
                seen.add(key)
                yield cls


def component_scan(root_module: Module) -> Iterable[ClassComponentInfo]:
    scanner = ClassScanner(root_module)
    component_infos = (get_component_info(cls) for cls in scanner.get_classes())
    return (c for c in component_infos if c is not None)
