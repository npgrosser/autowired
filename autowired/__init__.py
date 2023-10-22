import dataclasses
import inspect
import re
from abc import ABC
from dataclasses import dataclass
from functools import cached_property
from types import FunctionType
from typing import TypeVar, Any, Type, Callable, Optional, Union, List, Dict

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
    name: str
    type: Type[_T]
    required: bool = True


@dataclass(frozen=True)
class Provider:
    name: str
    type: Type[_T]
    getter: Callable[[], _T]

    def __str__(self):
        return f"Provider(name={self.name}, type={self.type.__name__})"

    def __repr__(self):
        return str(self)

    @staticmethod
    def from_instance(instance: Any, name: str = None) -> "Provider":
        if name is None:
            name = _camel_to_snake(type(instance).__name__)
        return Provider(name, type(instance), lambda: instance)


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


class InitializationError(DependencyError):
    """
    Raised when an object cannot be initialized.
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
    A container for resolving and storing dependencies.
    """

    _providers: List[Provider]

    def __init__(self):
        self._providers = []

    def get_providers(self, dependency: Optional[Dependency] = None) -> List[Provider]:
        if dependency is None:
            return list(self._providers)
        else:
            return [p for p in self._providers if issubclass(p.type, dependency.type)]

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

    def register(self, provider_or_instance: Union[Provider, Any], /):
        if not isinstance(provider_or_instance, Provider):
            provider = Provider.from_instance(provider_or_instance)
        else:
            provider = provider_or_instance

        for existing in self._providers:
            if existing.name == provider.name and existing.type == provider.type:
                raise ProviderConflictException(
                    f"Provider with name {provider.name} and type {provider.type.__name__} "
                    f"conflicts with existing provider {existing}"
                )
        self._providers.append(provider)

    def unregister(self, name: str):
        self._providers = [r for r in self._providers if r.name != name]

    def resolve(self, dependency: Union[Dependency, Type[_T]]) -> _T:
        if not isinstance(dependency, Dependency):
            logger.trace(f"Resolving type {dependency.__name__} for container {self}")
            dependency = Dependency(
                _camel_to_snake(dependency.__name__), dependency, True
            )

        logger.trace(f"Resolving {dependency} for container {self}")

        existing = self.get_provider(dependency)
        if existing:
            logger.trace(f"Found existing {existing}")
            return existing.getter()

        logger.trace(f"Existing not found, auto-wiring {dependency}")

        result = self.autowire(dependency.type)

        self.register(Provider(dependency.name, dependency.type, lambda: result))

        logger.trace(f"Successfully autowired {dependency} to {result}")
        return result

    def autowire(
        self,
        t: Type[_T],
        **explicit_kw_args,
    ) -> _T:
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
                logger.trace(
                    f"Getting argument {dep.name} for {t.__name__} from {existing.getter}"
                )
                resolved_kw_args[dep.name] = existing.getter()
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
            raise InitializationError(f"Failed to initialize {t.__name__}") from e


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
    Marks a field as autowired.
    Auto-wired fields are converted to cached properties on the class.
    :param eager: eagerly initialize the field on object creation
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
            value = self.autowire(field_type, **attr_value.get_all_kw_args(self))

            if not attr_value.transient:
                self.__dict__[item] = value

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
            self.container.register(provider)

    @cached_property
    def container(self) -> Container:
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

            container.register(Provider(name_normalized, prop.type, getter))

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


def _get_field_type(field_name: str, obj: Any) -> Type[_T]:
    if not hasattr(obj, "__annotations__"):
        raise MissingTypeAnnotation(
            f"Cannot determine type of field {type(obj).__name__}.{field_name}"
        )
    field_type = obj.__annotations__.get(field_name, None)
    if field_type is None:
        raise MissingTypeAnnotation(
            f"Cannot determine type of field {type(obj).__name__}.{field_name}"
        )

    return field_type


def _get_obj_properties(self) -> List[_PropertyInfo]:
    properties = []
    for name, attr in inspect.getmembers(type(self)):
        is_cached_property = isinstance(attr, cached_property)
        is_normal_property = isinstance(attr, property)

        if is_cached_property or is_normal_property:
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
    "InitializationError",
    "IllegalContextClass",
    "MissingTypeAnnotation",
    "NotProvidedException",
    "IllegalAutoWireType",
    "cached_property",
    "Context",
    "Container",
    "Dependency",
    "Provider",
    "autowired",
    "provided",
]
