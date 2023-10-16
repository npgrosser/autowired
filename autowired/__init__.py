import dataclasses
import inspect
import re
from abc import ABC
from dataclasses import dataclass
from enum import Enum
from functools import cached_property
from types import FunctionType
from typing import TypeVar, Any, Type, Callable, Optional, Union

try:  # pragma: no cover
    # noinspection PyPackageRequirements
    from loguru import logger
except ImportError:  # pragma: no cover
    import logging


    class _SimpleLogger:
        def trace(self, msg: str):
            logging.debug(msg)


    logger = _SimpleLogger()

_T = TypeVar("_T")


def _camel_to_snake(name: str) -> str:
    name = re.sub("(.)([A-Z][a-z]+)", r"\1_\2", name)
    return re.sub("([a-z0-9])([A-Z])", r"\1_\2", name).lower()


def _group_by(key_fn: Callable[[Any], Any], items: list[Any]) -> dict[Any, list[Any]]:
    result = {}
    for item in items:
        key = key_fn(item)
        if key not in result:
            result[key] = []
        result[key].append(item)
    return result


class FieldType(Enum):
    NORMAL = 1
    CACHED = 2
    AUTO_WIRED = 3


@dataclass(frozen=True)
class PropertyInfo:
    name: str
    type: type


@dataclass
class _PropertyGetter(Callable[[], Any]):
    obj: Any
    property: PropertyInfo

    def __call__(self) -> Any:
        logger.trace(f"Getting property {self.property.name} for {self.obj}")
        return getattr(self.obj, self.property.name)


@dataclass(frozen=True)
class Dependency:
    name: str
    type: Type[_T]
    required: bool = True


def cached(getter: Callable[[], Any]) -> Callable[[], Any]:
    """
    Caches the result of the given getter function.
    :param getter:
    :return:
    """
    value = None

    def wrapper():
        nonlocal value
        if value is None:
            value = getter()
        return value

    return wrapper


@dataclass(frozen=True)
class Bean:
    name: str
    type: type
    getter: Callable[[], Any]

    def __str__(self):
        return f"Bean(name={self.name}, type={self.type.__name__})"

    def __repr__(self):
        return str(self)

    @staticmethod
    def from_instance(instance: Any, name: str = None) -> "Bean":
        if name is None:
            name = _camel_to_snake(type(instance).__name__)
        return Bean(name, type(instance), cached(lambda: instance))


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


class BeanConflictException(AutowiredException):
    """
    Raised when a bean conflicts with an existing bean.
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


_illegal_module_names = ["builtins", "typing", "dataclasses", "abc"]


def _get_actual_init(t: type[_T]) -> Optional[FunctionType]:
    if "__init__" in t.__dict__:
        return t.__init__
    else:
        for base in t.__bases__:
            if base == object:
                continue
            init = _get_actual_init(base)
            if init:
                return init
        return None


def _get_dependencies_for_type(t: type[_T]) -> list[Dependency]:
    init = _get_actual_init(t)

    if init:
        sig = inspect.signature(init)
        return [
            Dependency(name, param.annotation, param.default == inspect.Parameter.empty)
            for name, param in sig.parameters.items()
            if name != "self"
        ]
    return []


# def _get_dependencies_for_type(t: type[_T]) -> list[Dependency]:
#     if "__init__" in t.__dict__:
#         init = t.__init__
#         if isinstance(init, FunctionType):
#             sig = inspect.signature(init)
#             return [
#                 Dependency(
#                     name, param.annotation, param.default == inspect.Parameter.empty
#                 )
#                 for name, param in sig.parameters.items()
#                 if name != "self"
#             ]
#     return []


class Container:
    """
    A container for resolving and storing dependencies.
    """

    _beans: list[Bean]

    def __init__(self):
        self._beans = []

    def derive(self) -> "Container":
        derived = Container()
        derived._beans.extend(self._beans)
        return derived

    def get_existing(self, dependency: Dependency) -> Optional[Bean]:
        """
        Returns an existing bean that matches the given dependency specification.
        :param dependency:
        :return:
        """
        candidates = []

        for r in self._beans:
            if issubclass(r.type, dependency.type):
                candidates.append(r)

        if len(candidates) == 1:
            return candidates[0]
        if len(candidates) > 1:
            by_name = _group_by(lambda obj: obj.name, candidates)
            if dependency.name in by_name and len(by_name[dependency.name]) == 1:
                return by_name[dependency.name][0]
            else:
                raise AmbiguousDependencyException(
                    f"Failed to resolve dependency {dependency.name} of type {dependency.type.__name__}. "
                    f"Multiple candidates found: {candidates}"
                )

        return None

    def register(self, bean: Union[Bean, Any]):
        if not isinstance(bean, Bean):
            bean = Bean.from_instance(bean)

        for existing in self._beans:
            if existing.name == bean.name and existing.type == bean.type:
                raise BeanConflictException(
                    f"Bean with name {bean.name} and type {bean.type.__name__} "
                    f"conflicts with existing bean {existing}"
                )
        self._beans.append(bean)

    def unregister(self, name: str):
        self._beans = [r for r in self._beans if r.name != name]

    def resolve(self, dependency: Union[Dependency, type[_T]]) -> _T:
        if not isinstance(dependency, Dependency):
            logger.trace(f"Resolving type {dependency.__name__} for container {self}")
            dependency = Dependency(
                _camel_to_snake(dependency.__name__), dependency, True
            )

        logger.trace(f"Resolving {dependency} for container {self}")

        existing = self.get_existing(dependency)
        if existing:
            logger.trace(f"Found existing {existing}")
            return existing.getter()

        logger.trace(f"Existing not found, auto-wiring {dependency}")

        result = self.autowire(dependency.type)

        self.register(Bean(dependency.name, dependency.type, lambda: result))

        logger.trace(f"Successfully autowired {dependency} to {result}")
        return result

    def autowire(
            self,
            t: type[_T],
            **explicit_kw_args,
    ) -> _T:
        logger.trace(
            f"Auto-wiring {t.__name__} with {len(explicit_kw_args)} explicit args"
        )
        if t.__module__.split(".")[0] in _illegal_module_names:
            raise IllegalAutoWireType(f"Cannot auto-wire object of type {t.__name__}")

        dependencies = _get_dependencies_for_type(t)

        resolved_kw_args = dict(explicit_kw_args) if explicit_kw_args else {}

        for dep in dependencies:
            if dep.name in resolved_kw_args:
                continue

            existing = self.get_existing(dep)
            if existing:
                logger.trace(f"Found existing {existing} bean for {dep}")
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


@dataclass
class _Autowired(_ContextProperty):
    eager: bool
    kw_args_factory: Callable[["Context"], dict[str, Any]]
    kw_args: dict[str, Any]

    def get_all_kw_args(self, ctx: "Context") -> dict[str, Any]:
        explicit_kw_args = self.kw_args_factory(ctx) if self.kw_args_factory else {}
        explicit_kw_args.update(self.kw_args)
        return explicit_kw_args


def autowired(
        kw_args_factory: Callable[[], dict[str, Any]] = None,
        *,
        eager: bool = False,
        **kw_args,
) -> Any:
    """
    Marks a field as autowired.
    Auto-wired fields are converted to cached properties on the class.
    :param eager: eagerly initialize the field on object creation
    :param kw_args_factory: a function that returns a dict of keyword arguments for initialization of the field
    :param kw_args: keyword arguments for initialization of the field
    :return:
    """
    return _Autowired(eager=eager, kw_args_factory=kw_args_factory, kw_args=kw_args)


class _Provided(_ContextProperty):
    pass


def provided() -> Any:
    return _Provided()


def _get_field_type(field_name: str, obj: Any) -> type:
    field_type = obj.__annotations__.get(field_name, None)
    if field_type is None:
        raise MissingTypeAnnotation(
            f"Cannot determine type of field {type(obj).__name__}.{field_name}")

    return field_type


def _resolve_autowired_field(field_name: str, _autowired: _Autowired, ctx: "Context"):
    field_type = _get_field_type(field_name, ctx)
    return ctx.autowire(field_type, **_autowired.get_all_kw_args(ctx))


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

        def __getattribute__(self, name):
            attr_value = super(result, self).__getattribute__(name)

            if not isinstance(attr_value, _Autowired):
                return attr_value

            autowired = attr_value

            value = _resolve_autowired_field(name, autowired, self)
            self.__dict__[name] = value
            return value

        result.__getattribute__ = __getattribute__

        return result


def _get_obj_properties(self) -> list[PropertyInfo]:
    properties = []
    for name, attr in inspect.getmembers(type(self)):
        is_cached_property = isinstance(attr, cached_property)
        is_normal_property = isinstance(attr, property)

        if is_cached_property or is_normal_property:
            getter = attr.fget if is_normal_property else attr.func
            prop_type = getter.__annotations__.get("return", None)
            properties.append(PropertyInfo(name, prop_type))
        elif isinstance(attr, _Autowired) or isinstance(attr, _Provided):
            properties.append(PropertyInfo(name, _get_field_type(name, self)))
    return properties


class Context(metaclass=_ContextMeta):
    parent_context: Optional["Context"] = None

    @cached_property
    def container(self) -> Container:
        container = (
            self.parent_context.container.derive()
            if self.parent_context
            else Container()
        )

        for prop in _get_obj_properties(self):
            if prop.name == "container":
                continue

            getter = _PropertyGetter(self, prop)
            if prop.type is None:
                raise MissingTypeAnnotation(
                    f"Failed to determine type of {type(self).__name__}.{prop.name}. "
                )
            container.register(Bean(prop.name, prop.type, cached(getter)))

        return container

    def autowire(self, t: Union[type[_T], type], **explicit_kw_args) -> _T:
        return self.container.autowire(t, **explicit_kw_args)


__all__ = [
    "AutowiredException",
    "BeanConflictException",
    "DependencyError",
    "UnresolvableDependencyException",
    "AmbiguousDependencyException",
    "InitializationError",
    "IllegalContextClass",
    "MissingTypeAnnotation",
    "NotProvidedException",
    "cached",
    "cached_property",
    "IllegalAutoWireType",
    "Context",
    "Container",
    "Dependency",
    "Bean",
    "autowired",
    "provided",
]
