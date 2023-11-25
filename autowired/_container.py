import inspect
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from types import FunctionType
from typing import Type, Callable, Any, List, Optional, Union, Generic, Dict, TypeVar

from ._exceptions import (
    MissingTypeAnnotation,
    AmbiguousDependencyException,
    IllegalAutoWireType,
    InstantiationError,
    UnresolvableDependencyException,
    AutowiredException,
)
from ._logging import logger
from ._typing_utils import is_subtype, get_sequence_type

_T = TypeVar("_T")


@dataclass(frozen=True)
class Dependency:
    """
    A dependency specification.
    """

    name: str
    type: Type[_T]
    required: bool = True


class Provider(ABC, Generic[_T]):
    @abstractmethod
    def get_instance(
        self, dependency: Dependency, container: "Container"
    ) -> _T:  # pragma: no cover
        """
        Returns an instance that satisfies the given dependency specification.

        :param dependency: The dependency specification.
        :param container: The container that is currently resolving the dependency.
        :return: An instance that satisfies the given dependency specification
        """
        ...

    @abstractmethod
    def get_name(self) -> str:  # pragma: no cover
        """
        Returns the name of the provider.
        Used by the container to resolve ambiguous dependencies.
        If a container contains multiple dependencies that satisfy the same dependency specification,
        the name of the dependency is compared to the provider name to try to resolve the ambiguity.

        :return: The name of the provider
        """
        ...

    @abstractmethod
    def satisfies(self, dependency: Dependency) -> bool:  # pragma: no cover
        """
        Returns whether this provider satisfies the given dependency specification.

        :param dependency: The dependency specification.
        :return: Whether this provider satisfies the given dependency specification
        """
        ...

    @staticmethod
    def from_instance(instance: _T, name: str = None) -> "Provider[_T]":
        """
        Creates a singleton provider from the given instance.

        :param instance: The instance. Will always be returned by self.get_instance(...)
        :param name: The name of the provider. If None, the type name of the instance is used (snake case).
        :return: The newly created provider
        """
        if name is None:
            name = _camel_to_snake(type(instance).__name__)
        return _SimpleProvider(name, type(instance), lambda: instance)

    # noinspection PyShadowingBuiltins
    @staticmethod
    def from_supplier(
        supplier: Callable[[], _T],
        type: Optional[Type[_T]] = None,
        name: Optional[str] = None,
    ) -> "Provider[_T]":
        """
        Creates a provider from the given supplier function.
        :param supplier: The supplier function. Will be called every time self.get_instance(...) is called.
        :param type: The type of the component this provider provides.
                        If None, the return type of the supplier function is used, or if supplier is a class,
                        the class itself is used.
        :param name: The name of the provider. If None, the type name of the supplier is used (snake case).
        :return: The newly created provider
        """
        if type is None:
            # if getter is a class, use the class as a type
            if inspect.isclass(supplier):
                type = supplier
            else:
                type = inspect.signature(supplier).return_annotation
                if type == inspect.Signature.empty:
                    raise MissingTypeAnnotation(
                        f"Failed to determine type of {supplier.__name__}. "
                    )

        if name is None:
            name = _camel_to_snake(type.__name__)

        return _SimpleProvider(name, type, supplier)


@dataclass(frozen=True)
class _SimpleProvider(Provider[_T]):
    name: str
    type: Type[_T]
    getter: Callable[[], _T] = field(repr=False)

    def get_instance(self, dependency: Dependency, container: "Container") -> _T:
        return self.getter()

    def get_name(self) -> str:
        return self.name

    def satisfies(self, dependency: Dependency) -> bool:
        return is_subtype(self.type, dependency.type)


_illegal_autowiredType_modules = ["builtins", "typing", "dataclasses", "abc", "object"]


class Container:
    """
    A container for resolving and storing dependencies.
    """

    _providers: List[Provider]

    def __init__(self):
        self._providers = []

    def get_providers(self, dependency: Optional[Dependency] = None) -> List[Provider]:
        """
        Returns all providers that match the given dependency specification.

        :param dependency: Optional dependency specification, if None, all providers are returned
        :return:
        """

        if dependency is None:
            return list(self._providers)
        else:
            return [p for p in self._providers if p.satisfies(dependency)]

    def get_provider(self, dependency: Dependency) -> Optional[Provider]:
        """
        Returns an existing provider that matches the given dependency specification.

        :param dependency:
        :return:
        :raises AmbiguousDependencyException: If multiple matching providers are found and there is no name match
        """
        candidates = self.get_providers(dependency)

        if len(candidates) == 1:
            return candidates[0]
        if len(candidates) > 1:
            by_name = _group_by(lambda obj: obj.name, candidates)
            if dependency.name in by_name and len(by_name[dependency.name]) == 1:
                return by_name[dependency.name][0]
            else:
                raise AmbiguousDependencyException(
                    f"Failed to resolve dependency {dependency.name}"
                    f" of type {dependency.type.__name__}."
                    f" Multiple candidates found: {candidates}"
                )

        return None

    def add(self, provider_or_instance: Union[Provider, Any], /):
        """
        Adds a provider or instance (as singleton provider) to the container.

        :param provider_or_instance: If not a provider, a singleton provider is created from the instance.
                                     The name of the provider is derived from the type name of the instance.
        """
        if not isinstance(provider_or_instance, Provider):
            provider = Provider.from_instance(provider_or_instance)
        else:
            provider = provider_or_instance

        self._providers.append(provider)

    def remove(self, provider: Union[str, Provider, Type[_T]], /):
        """
        Remove a provider from the container.

        :param provider: Provider name or provider instance
        """

        def predicate(p: Provider) -> bool:
            if isinstance(provider, Provider):
                return p == provider
            else:
                return p.get_name() == provider

        remove_index = None
        for i, p in enumerate(self._providers):
            if predicate(p):
                remove_index = i
                break

        if remove_index is not None:
            self._providers.pop(remove_index)

    def resolve(self, dependency: Union[Dependency, Type[_T]]) -> _T:
        """
        Resolves a dependency from the container.
        If no existing provider satisfies the dependency specification,
        the container tries to auto-wire the object as defined by `self.autowire(...)`
        and stores the result instance as a new singleton provider.
        The same is true for the dependencies of the object (recursively).
        If multiple matching providers are found,
        the name of the dependency is compared to the provider name to try to resolve the ambiguity.

        :param dependency: Dependency specification or target type
        :return: the resolved dependency
        :raises UnresolvableDependencyException: if the dependency cannot be resolved
        :raises AmbiguousDependencyException: if multiple matching providers are found and there is no name match
        """
        if not isinstance(dependency, Dependency):
            logger.trace(f"Resolving type {dependency.__name__} for container {self}")
            dependency = Dependency(
                _camel_to_snake(dependency.__name__), dependency, True
            )

        logger.trace(f"Resolving {dependency} for container {self}")

        existing = self.get_provider(dependency)
        if existing:
            logger.trace(f"Found existing {existing}")
            return existing.get_instance(dependency, self)

        logger.trace(f"Existing not found, auto-wiring {dependency}")

        # region list injection special case
        # check if the dependency type is a list
        sequence_type, element_type = get_sequence_type(dependency.type)
        if element_type is not None:
            element_type: Any
            element_dependency = Dependency(dependency.name, element_type, True)
            elements = []
            for provider in self.get_providers(element_dependency):
                elements.append(provider.get_instance(element_dependency, self))
            return sequence_type(elements)

        # endregion

        result = self.autowire(dependency.type)

        self.add(
            Provider.from_supplier(lambda: result, dependency.type, dependency.name)
        )

        logger.trace(f"Successfully autowired {dependency} to {result}")
        return result

    def autowire(
        self,
        t: Type[_T],
        **explicit_kw_args,
    ) -> _T:
        """
        Auto-wires an object of the given type. Meaning that all dependencies of the object are resolved
        as defined by `self.resolve(...)` and the object is initialized with the resolved dependencies.
        In contrast to `self.resolve(...)`, this function does not store the result as a singleton provider.

        :param t:
        :param explicit_kw_args:
        :return: The auto-wired object
        :raises AutowiredException: if the object cannot be auto-wired
        """
        logger.trace(f"Auto-wiring {t} with {len(explicit_kw_args)} explicit args")
        if t.__module__.split(".")[0] in _illegal_autowiredType_modules:
            raise IllegalAutoWireType(f"Cannot auto-wire object of type {t}")

        dependencies = _get_dependencies_for_type(t)

        resolved_kw_args = dict(explicit_kw_args) if explicit_kw_args else {}

        for dep in dependencies:
            if dep.name in resolved_kw_args:
                continue

            existing = self.get_provider(dep)
            if existing:
                logger.trace(f"Found existing {existing} provider for {dep}")

                resolved_kw_args[dep.name] = existing.get_instance(dep, self)
            else:
                try:
                    auto = self.resolve(dep)
                    resolved_kw_args[dep.name] = auto
                except AutowiredException as e:
                    if dep.required:
                        raise UnresolvableDependencyException(
                            f"Failed to resolve dependency {dep.name} "
                            f"of type {dep.type} for {t}. "
                        ) from e

        try:
            return t(**resolved_kw_args)
        except Exception as e:
            raise InstantiationError(f"Failed to initialize {t.__name__}") from e


# region utils


def _get_dependencies_for_type(t: type) -> List[Dependency]:
    init = _get_actual_init(t)
    dependencies = []
    if init:
        sig = inspect.signature(init)

        for name, param in sig.parameters.items():
            if name == "self":
                continue
            annotation = param.annotation
            default = param.default
            has_default = default != inspect.Parameter.empty

            if annotation == inspect.Parameter.empty:
                if has_default:
                    # falling back to the type of the default value
                    annotation = type(param.default)
                else:
                    annotation = object

            dependency = Dependency(name, annotation, not has_default)
            dependencies.append(dependency)

    return dependencies


def _camel_to_snake(name: str) -> str:
    return re.sub("([a-z0-9])([A-Z])", r"\1_\2", name).lower()


def _group_by(key_fn: Callable[[Any], Any], items: List[Any]) -> Dict[Any, List[Any]]:
    result = {}
    for item in items:
        key = key_fn(item)
        if key not in result:
            result[key] = []
        result[key].append(item)
    return result


def _get_actual_init(t: type) -> Optional[FunctionType]:
    if "__init__" in t.__dict__:
        return getattr(t, "__init__")
    else:
        for base in t.__bases__:
            if base == object:
                continue
            init = _get_actual_init(base)
            if init:
                return init
        return None


# endregion
