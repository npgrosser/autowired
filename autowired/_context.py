import dataclasses
import inspect
import threading
from abc import ABC
from collections import defaultdict
from functools import cached_property
from typing import Optional, Union, Any, Callable, Dict, Type, List, TypeVar
from dataclasses import dataclass
from ._container import Provider, Container
from ._exceptions import (
    MissingTypeAnnotation,
    IllegalContextClass,
    NotProvidedException,
)
from ._logging import logger
from ._thread_local_cached_property import thread_local_cached_property


_T = TypeVar("_T")


class _ContextValueSelector:
    def __init__(
        self,
        parent: Optional["_ContextValueSelector"] = None,
        key: Optional[str] = None,
    ):
        self.parent = parent
        self.key = key

    def __getattr__(self, item: str) -> "_ContextValueSelector":
        return _ContextValueSelector(self, item)

    def select(self, ctx: "Context") -> Any:
        assert self.parent is not None
        assert self.key is not None

        parent_value = self.parent.select(ctx)
        return getattr(parent_value, self.key)


class _ContextProperty(ABC, _ContextValueSelector):
    name: str = None

    def __setattr__(self, key, value):
        if key == "name":
            assert self.name is None, f"Cannot set {self.__class__.__name__} name twice"
        super().__setattr__(key, value)

    def select(self, ctx: "Context") -> Any:
        assert self.name is not None
        return getattr(ctx, self.name)


class _Autowired(_ContextProperty):
    def __init__(
        self,
        eager: bool,
        transient: bool,
        thread_local: bool,
        kw_args_factory: Optional[Callable[["Context"], Dict[str, Any]]],
        kw_args: Dict[str, Any],
    ):
        super().__init__()
        self.eager = eager
        self.transient = transient
        self.thread_local = thread_local
        self.kw_args_factory = kw_args_factory
        self.kw_args = kw_args

    def get_all_kw_args(self, ctx: "Context") -> Dict[str, Any]:
        explicit_kw_args = self.kw_args_factory(ctx) if self.kw_args_factory else {}
        explicit_kw_args.update(self.kw_args)

        for key, value in explicit_kw_args.items():
            if isinstance(value, _ContextValueSelector):
                explicit_kw_args[key] = value.select(ctx)
        return explicit_kw_args

    def __getattr__(self, item):
        return _ContextValueSelector(self, item)


class _Provided(_ContextProperty):
    def __getattr__(self, item):
        return _ContextValueSelector(self, item)


def autowired(
    kw_args_factory: Optional[Callable[["Context"], Dict[str, Any]]] = None,
    /,
    *,
    eager: bool = False,
    transient: bool = False,
    thread_local: bool = False,
    **kw_args,
) -> Any:
    """
    Marks a context field as autowired.
    Auto-wired fields are converted to cached properties on the class.
    :param kw_args_factory: Return a dict of keyword arguments for initialization of the field
    :param eager: Eagerly initialize the field on object creation
    :param transient: Every access to the field returns a new instance
    :param thread_local: Create on instance per-thread
    :param kw_args: keyword arguments for initialization of the field
    :return:
    """
    return _Autowired(
        eager=eager,
        transient=transient,
        thread_local=thread_local,
        kw_args_factory=kw_args_factory,
        kw_args=kw_args,
    )


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
    Responsible for evaluating context properties (autowired and provided fields).
    """

    def __new__(mcs, name, bases, class_dict):
        autowired_fields = [
            key for key, value in class_dict.items() if isinstance(value, _Autowired)
        ]
        eager_fields = [
            key
            for key, value in class_dict.items()
            if isinstance(value, _Autowired) and value.eager
        ]
        provided_fields = [
            key for key, value in class_dict.items() if isinstance(value, _Provided)
        ]
        for key, value in class_dict.items():
            if isinstance(value, _ContextProperty):
                value.name = key

        original_init = class_dict.get("__init__", None)

        def new_init(self, *args, **kwargs):
            self._autowire_locks = defaultdict(threading.Lock)
            for field in autowired_fields:
                self._autowire_locks[field] = threading.Lock()

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

            if attr_value.transient:
                value = self.autowire(field_type, **attr_value.get_all_kw_args(self))
            elif attr_value.thread_local:
                thread_local_storage = self.__dict__.setdefault(
                    f"_{item}_thread_local", threading.local()
                )

                if not hasattr(thread_local_storage, "value"):
                    thread_local_storage.value = self.autowire(
                        field_type, **attr_value.get_all_kw_args(self)
                    )

                value = thread_local_storage.value
            else:
                lock = self._autowire_locks[item]
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
                # if no return type annotation is present,
                # try to get from class annotations
                prop_type = type(self).__annotations__.get(name, None)

            properties.append(_PropertyInfo(name, prop_type))
        elif isinstance(attr, _Autowired) or isinstance(attr, _Provided):
            properties.append(_PropertyInfo(name, _get_field_type(name, self)))

    return properties


# endregion
