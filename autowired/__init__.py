import dataclasses
import inspect
import re
import threading
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass
from functools import cached_property
from types import FunctionType
from typing import (
    TypeVar,
    Any,
    Type,
    Callable,
    Optional,
    Union,
    List,
    Dict,
    Generic,
)

from autowired._thread_local_cached_property import thread_local_cached_property

try:  # pragma: no cover
    # noinspection PyPackageRequirements
    from loguru import logger
except ImportError:  # pragma: no cover
    import logging

    # noinspection PyMethodMayBeStatic
    class _SimpleLogger:
        def trace(self, msg: str):
            logging.debug(msg)

    logger = _SimpleLogger()

_T = TypeVar("_T")


@dataclass(frozen=True)
class _PropertyInfo:
    name: str
    type: Type[_T]


@dataclass
class _PropertyGetter(Callable[[], Any]):
    obj: Any
    property: _PropertyInfo

    def __call__(self) -> Any:
        logger.trace(f"Getting property {self.property.name} for {self.obj}")
        return getattr(self.obj, self.property.name)


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
        :return: an instance that satisfies the given dependency specification
        """
        ...

    @abstractmethod
    def get_name(self) -> str:  # pragma: no cover
        """
        Returns the name of the provider.
        Use by the container to resolve ambiguous dependencies.
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
            # if getter is a class, use the class as type
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
    getter: Callable[[], _T]

    def __str__(self):
        return f"Provider(name={self.name}, type={self.type.__name__})"

    def __repr__(self):
        return str(self)

    def get_instance(self, dependency: Dependency, container: "Container") -> _T:
        return self.getter()

    def get_name(self) -> str:
        return self.name

    def satisfies(self, dependency: Dependency) -> bool:
        return issubclass(self.type, dependency.type)


class AutowiredException(Exception, ABC):
    """
    Base class for all library exceptions.
    """

    pass


class IllegalContextClass(AutowiredException):
    """
    Raised when a class is used as a context class that is not allowed to be used as such.
    """

    pass


class MissingTypeAnnotation(IllegalContextClass):
    """
    Raised when a field or property in a context class is missing a type annotation.
    """

    pass


class ProviderConflictException(AutowiredException):
    """
    Raised when a provider conflicts with an existing provider.
    """

    pass


class DependencyError(AutowiredException, ABC):
    """
    Base class for all dependency-related errors.
    """

    pass


class IllegalAutoWireType(DependencyError):
    """
    Raised when an object of a type that is not allowed to be auto-wired is auto-wired.
    """

    pass


class AmbiguousDependencyException(DependencyError):
    """
    Raised when a dependency cannot be resolved because multiple candidates are found
    and none of them matches the name of the dependency.
    """

    pass


class UnresolvableDependencyException(DependencyError):
    """
    Raised when a dependency cannot be resolved.
    """

    pass


class InstantiationError(DependencyError):
    """
    Raised when an object cannot be instantiated.
    """

    pass


class NotProvidedException(AutowiredException):
    """
    Raised when a provided field is not initialized.
    """

    pass


# types from these modules are not allowed to be auto-wired
_illegal_autowired_type_modules = ["builtins", "typing", "dataclasses", "abc"]


class Container:
    """
    A container for resolving and storing dependencies / providers.
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
        Adds a provider to the container.

        :param provider_or_instance: If not a provider, a singleton provider is created from the instance.
                                     The name of the provider is derived from the type name of the instance.
        """
        if not isinstance(provider_or_instance, Provider):
            provider = Provider.from_instance(provider_or_instance)
        else:
            provider = provider_or_instance

        for existing in self._providers:
            if existing.get_name() == provider.get_name():
                raise ProviderConflictException(
                    f"Provider with name {provider.get_name()} "
                    f"conflicts with existing provider {existing}"
                )
        self._providers.append(provider)

    def remove(self, provider: Union[str, Provider, Type[_T]], /):
        """
        Remove a provider from the container.

        :param provider: provider name or provider instance
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
        If multiple matching providers are found,
        the name of the dependency is compared to the provider name to try to resolve the ambiguity.

        :param dependency: dependency specification or target type
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
        The object itself is always a new instance and not automatically stored in the container.

        :param t:
        :param explicit_kw_args:
        :return: the auto-wired object
        :raises IllegalAutoWireType: if the type is not allowed to be auto-wired (e.g. built-in types)
        :raises UnresolvableDependencyException: if resolving a dependency fails
        :raises InitializationError: if initializing the object fails
        """
        logger.trace(
            f"Auto-wiring {t.__name__} with {len(explicit_kw_args)} explicit args"
        )
        if t.__module__.split(".")[0] in _illegal_autowired_type_modules:
            raise IllegalAutoWireType(f"Cannot auto-wire object of type {t.__name__}")

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
                except DependencyError as e:
                    if dep.required:
                        raise UnresolvableDependencyException(
                            f"Failed to resolve dependency {dep.name} "
                            f"of type {dep.type.__name__} for {t.__name__}. "
                        ) from e

        try:
            return t(**resolved_kw_args)
        except Exception as e:
            raise InstantiationError(f"Failed to initialize {t.__name__}") from e


class _ContextProperty(ABC):
    pass


@dataclass(frozen=True)
class _Autowired(_ContextProperty):
    eager: bool
    transient: bool
    kw_args_factory: Callable[["Context"], Dict[str, Any]]
    kw_args: Dict[str, Any]

    def get_all_kw_args(self, ctx: "Context") -> Dict[str, Any]:
        explicit_kw_args = self.kw_args_factory(ctx) if self.kw_args_factory else {}
        explicit_kw_args.update(self.kw_args)
        return explicit_kw_args


def autowired(
    kw_args_factory: Callable[["Context"], Dict[str, Any]] = None,
    /,
    *,
    eager: bool = False,
    transient: bool = False,
    **kw_args,
) -> Any:
    """
    Marks a context field as autowired.
    Auto-wired fields are converted to cached properties on the class.
    :param eager: Eagerly initialize the field on object creation
    :param transient: every access to the field returns a new instance
    :param kw_args_factory: return a dict of keyword arguments for initialization of the field
    :param kw_args: keyword arguments for initialization of the field
    :return:
    """
    return _Autowired(
        eager=eager,
        transient=transient,
        kw_args_factory=kw_args_factory,
        kw_args=kw_args,
    )


class _Provided(_ContextProperty):
    pass


def provided() -> Any:
    """
    Marks a field as provided.
    Meaning that the field is set explicitly rather than auto-wired.
    If not set, an exception is raised on context initialization.
    :return:
    """
    return _Provided()


class _ContextMeta(type):
    """
    Metaclass for Context classes.
    Converts all fields with autowired(...) value to cached properties.
    """

    _auto_wire_locks = defaultdict(threading.Lock)  # lock per context and field name

    def __new__(mcs, name, bases, class_dict):
        eager_fields = [
            key
            for key, value in class_dict.items()
            if isinstance(value, _Autowired) and value.eager
        ]
        provided_fields = [
            key for key, value in class_dict.items() if isinstance(value, _Provided)
        ]

        original_init = class_dict.get("__init__", None)

        def new_init(self, *args, **kwargs):
            if dataclasses.is_dataclass(self):
                raise IllegalContextClass(
                    f"Context class {name} must not be a dataclass"
                )
            if original_init:
                original_init(self, *args, **kwargs)

            for field_name in eager_fields:
                getattr(self, field_name)

            for field_name in provided_fields:
                value = getattr(self, field_name)
                if isinstance(value, _Provided):
                    raise NotProvidedException(
                        f"Field {field_name} is marked as provided but is not initialized"
                    )

        class_dict["__init__"] = new_init

        result = super().__new__(mcs, name, bases, class_dict)

        def __getattribute__(self, item):
            attr_value = super(result, self).__getattribute__(item)

            if not isinstance(attr_value, _Autowired):
                return attr_value

            field_type = _get_field_type(item, self)

            if not attr_value.transient:
                lock = mcs._auto_wire_locks[(id(self), item)]
                print("lock key", (id(self), item))
                with lock:
                    attr_value = super(result, self).__getattribute__(item)
                    if isinstance(attr_value, _Autowired):
                        # is still an autowired field, auto-wire it
                        value = self.autowire(
                            field_type, **attr_value.get_all_kw_args(self)
                        )
                        self.__dict__[item] = value
                    else:
                        value = self.__dict__[item]
            else:
                value = self.autowire(field_type, **attr_value.get_all_kw_args(self))

            return value

        result.__getattribute__ = __getattribute__

        return result


class Context(metaclass=_ContextMeta):
    def derive_from(self, ctx: Union["Context", Container]) -> None:
        """
        Registers all providers from the given context or container in this context.
        """
        container = ctx.container if isinstance(ctx, Context) else ctx
        for provider in container.get_providers():
            self.container.add(provider)

    @cached_property
    def container(self) -> Container:
        """
        Returns the container for this context.
        """
        container = Container()

        for prop in _get_obj_properties(self):
            if prop.name == "container":
                continue

            getter = _PropertyGetter(self, prop)
            if prop.type is None:
                raise MissingTypeAnnotation(
                    f"Failed to determine type of {type(self).__name__}.{prop.name}. "
                )

            name_normalized = prop.name.lstrip("_")

            container.add(Provider.from_supplier(getter, prop.type, name_normalized))

        return container

    def autowire(self, t: Union[Type[_T], type], **explicit_kw_args) -> _T:
        return self.container.autowire(t, **explicit_kw_args)


# region utils
def _camel_to_snake(name: str) -> str:
    name = re.sub("(.)([A-Z][a-z]+)", r"\1_\2", name)
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


def _get_dependencies_for_type(t: type) -> List[Dependency]:
    init = _get_actual_init(t)

    if init:
        sig = inspect.signature(init)
        return [
            Dependency(name, param.annotation, param.default == inspect.Parameter.empty)
            for name, param in sig.parameters.items()
            if name != "self"
        ]
    return []


def _get_annotations_for_type(t: type) -> Dict[str, Any]:
    annotations = {}

    if hasattr(t, "__annotations__"):
        annotations = t.__annotations__

    # base classes (do not overwrite from derived classes)
    for base in t.__bases__:
        if base == object:
            continue
        base_annotations = _get_annotations_for_type(base)
        annotations = {
            **base_annotations,
            **annotations,
        }

    return annotations


def _get_field_type(field_name: str, obj: Any) -> Type[_T]:
    annotations = _get_annotations_for_type(type(obj))
    field_type = annotations.get(field_name, None)
    if field_type is None:
        raise MissingTypeAnnotation(
            f"Cannot determine type of field {type(obj).__name__}.{field_name}"
        )

    return field_type


def _get_obj_properties(self) -> List[_PropertyInfo]:
    properties = []
    for name, attr in inspect.getmembers(type(self)):
        is_cached_property = isinstance(attr, cached_property)
        is_thread_local_cached_property = isinstance(attr, thread_local_cached_property)
        is_normal_property = isinstance(attr, property)

        if is_cached_property or is_normal_property or is_thread_local_cached_property:
            getter = attr.fget if is_normal_property else attr.func
            prop_type = getter.__annotations__.get("return", None)
            if prop_type is None and hasattr(self, "__annotations__"):
                # try to get from class annotations
                prop_type = type(self).__annotations__.get(name, None)

            properties.append(_PropertyInfo(name, prop_type))
        elif isinstance(attr, _Autowired) or isinstance(attr, _Provided):
            properties.append(_PropertyInfo(name, _get_field_type(name, self)))

    return properties


# endregion

__all__ = [
    "AutowiredException",
    "ProviderConflictException",
    "DependencyError",
    "UnresolvableDependencyException",
    "AmbiguousDependencyException",
    "InstantiationError",
    "IllegalContextClass",
    "MissingTypeAnnotation",
    "NotProvidedException",
    "IllegalAutoWireType",
    "cached_property",
    "thread_local_cached_property",
    "Context",
    "Container",
    "Dependency",
    "Provider",
    "autowired",
    "provided",
]
