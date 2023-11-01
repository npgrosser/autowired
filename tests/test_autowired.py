import threading
from dataclasses import dataclass
from unittest.mock import Mock

import pytest

from autowired import (
    autowired,
    cached_property,
    Context,
    Container,
    Dependency,
    UnresolvableDependencyException,
    AmbiguousDependencyException,
    IllegalAutoWireType,
    InstantiationError,
    Provider,
    NotProvidedException,
    IllegalContextClass,
    MissingTypeAnnotation,
    ProviderConflictException,
    provided,
    thread_local_cached_property,
)


class Service0:
    pass


@dataclass
class Service1:
    service0: Service0


class Service2:
    def __init__(self, service1: Service1, blabla: str = "blabla"):
        self.service1 = service1
        self.blabla = blabla


@dataclass
class Service3:
    service0: Service0
    service1: Service1
    foo: str = "bar"


##


class ExampleContext(Context):
    service2: Service2 = autowired()

    @cached_property
    def service1(self) -> Service1:
        return self.autowire(Service1)

    @cached_property
    def service3(self) -> Service3:
        return self.autowire(Service3, foo="baz")


def test_service_instances():
    ctx = ExampleContext()

    service2 = ctx.service2
    service3 = ctx.service3
    service2b = ctx.service2

    # Assert that the same instance is returned by the context
    assert id(service2) == id(service2b), "Different instances of service2"

    # Assert that property `foo` is overridden
    assert service3.foo == "baz", "Incorrect foo value"

    # Assert that service2 in service3 and service2 are same
    assert id(service3.service1) == id(ctx.service1)

    assert isinstance(ctx.service1, Service1)
    assert isinstance(ctx.service2, Service2)
    assert isinstance(ctx.service3, Service3)


@dataclass
class ServiceX:
    s: str


@dataclass
class Service4:
    x: ServiceX
    service1: Service1


def test_derived_context():
    ctx = ExampleContext()

    class DerivedContext(Context):
        service4: Service4 = autowired()

        def __init__(self, parent_context: Context):
            self.derive_from(parent_context)

    derived_context = DerivedContext(ctx)
    derived_context.container.add(Provider.from_instance(ServiceX("foo")))
    assert isinstance(derived_context.service4, Service4)
    assert id(derived_context.service4.service1) == id(ctx.service1)
    assert derived_context.service4.x.s == "foo"


def test_unresolvable_dependency():
    class TestContext(Context):
        service4: Service4 = autowired()

    ctx = TestContext()

    with pytest.raises(UnresolvableDependencyException):
        print(ctx.service4)


def test_ambiguous_dependency():
    class TestContext(Context):
        service1_a: Service1 = autowired()
        service1_b: Service1 = autowired()

    ctx = TestContext()

    with pytest.raises(AmbiguousDependencyException):
        ctx.autowire(Service2)

    with pytest.raises(AmbiguousDependencyException):
        ctx.container.resolve(Dependency("service1", Service1, True))

    s1a = ctx.container.resolve(Dependency("service1_a", Service1, True))
    s1b = ctx.container.resolve(Dependency("service1_b", Service1, True))

    assert isinstance(s1a, Service1)
    assert isinstance(s1b, Service1)
    assert id(s1a) != id(s1b)


def test_not_instantiable():
    class TestContext(Context):
        service_x: ServiceX = autowired()

    ctx = TestContext()
    try:
        ctx.service_x
    except Exception as e:
        assert isinstance(e, UnresolvableDependencyException)
        cause = e.__cause__
        assert isinstance(cause, IllegalAutoWireType)


def test_resolve_by_type():
    ctx = ExampleContext()
    service1 = ctx.container.resolve(Service1)

    assert id(ctx.service1) == id(service1)


def test_eager_init():
    names_initiated = []

    class TestService:
        def __init__(self, name: str):
            nonlocal names_initiated
            names_initiated.append(name)
            self.name = name

    class TestContext(Context):
        service1: TestService = autowired(eager=True, name="service1")
        service2: TestService = autowired(eager=False, name="service2")

    ctx = TestContext()

    assert len(names_initiated) == 1
    assert names_initiated[0] == "service1"

    service1 = ctx.service1

    assert len(names_initiated) == 1

    service2 = ctx.service2

    assert len(names_initiated) == 2

    assert service1.name == "service1"
    assert service2.name == "service2"


def test_autowire_initialization_error():
    container = Container()

    class TestService:
        def __init__(self):
            raise Exception("Test exception")

    with pytest.raises(InstantiationError):
        container.autowire(TestService)


def test_unregister_dependency():
    container = Container()
    s0 = Service0()
    container.add(Provider.from_instance(s0))

    s0_resolved = container.resolve(Service0)

    assert id(s0) == id(s0_resolved)

    container.remove("service0")

    s0_resolved2 = container.resolve(Service0)

    assert id(s0) != id(s0_resolved2)


def test_conflicting_bean():
    container = Container()
    container.add(Provider.from_instance(Service0()))
    with pytest.raises(ProviderConflictException):
        container.add(Provider.from_instance(Service0()))


def test_use_correct_subtype():
    class ServiceA:
        pass

    class ServiceB(ServiceA):
        pass

    @dataclass
    class OtherService:
        a: ServiceA

    class TestContext(Context):
        other: OtherService = autowired()

    ctx = TestContext()
    service_b = ServiceB()
    ctx.container.add(Provider.from_instance(service_b))

    assert isinstance(ctx.other.a, ServiceB)
    assert id(ctx.other.a) == id(service_b)

    # same test with cached_property instead of register
    class TestContext2(Context):
        other: OtherService = autowired()

        @cached_property
        def service_b(self) -> ServiceB:
            return self.autowire(ServiceB)

    ctx2 = TestContext2()

    assert isinstance(ctx2.other.a, ServiceB)
    assert id(ctx2.other.a) == id(ctx2.service_b)


def test_provided():
    class TestContext(Context):
        service1: Service1 = provided()
        service2: Service2 = autowired()

        def __init__(self, service1: Service1 = None):
            if service1 is not None:
                self.service1 = service1

    with pytest.raises(NotProvidedException):
        TestContext()

    ctx = TestContext(Service1(Service0()))

    assert isinstance(ctx.service1, Service1)

    assert id(ctx.service1) == id(ctx.service2.service1)


def test_dataclass_as_context():
    @dataclass
    class TestContext(Context):
        service1: Service1 = autowired()

    with pytest.raises(IllegalContextClass):
        TestContext()


def test_missing_type_annotation():
    class TestContext(Context):
        service1 = autowired()

    ctx = TestContext()

    with pytest.raises(MissingTypeAnnotation):
        print(ctx.service1)


def test_register_instance():
    class TestContext(Context):
        service1: Service1 = autowired()
        service4: Service4 = autowired()

    ctx = TestContext()

    with pytest.raises(UnresolvableDependencyException):
        print(ctx.service4)

    x = ServiceX("foo")
    ctx.container.add(x)

    assert isinstance(ctx.service4, Service4)
    assert id(ctx.service4.x) == id(x)


def test_property_not_annotated():
    class TestContext1(Context):
        service1 = autowired()

    ctx = TestContext1()

    with pytest.raises(MissingTypeAnnotation):
        print(ctx.service1)

    class TestContext2(Context):
        @cached_property
        def service1(self):
            return self.autowire(Service1)

    with pytest.raises(MissingTypeAnnotation):
        print(TestContext2().container)

    class TestContext3(Context):
        # partially annotated
        service1: Service1 = autowired()
        service2 = autowired()

    with pytest.raises(MissingTypeAnnotation):
        print(TestContext3().container)


def test_provider_reuses_base_init():
    class Dep:
        pass

    class BaseProvider:
        def __init__(self, dep: Dep):
            self.dep = dep

    class Provider(BaseProvider):
        pass

    class TestContext(Context):
        provider: Provider = autowired()

    ctx = TestContext()
    assert isinstance(ctx.provider.dep, Dep)


def test_hidden_provider_is_singleton():
    class HiddenDep:
        pass

    class A:
        def __init__(self, hidden_dep: HiddenDep):
            self.hidden_dep = hidden_dep

    class B:
        def __init__(self, hidden_dep: HiddenDep):
            self.hidden_dep = hidden_dep

    class TestContext(Context):
        a: A = autowired()
        b: B = autowired()

    ctx = TestContext()

    assert id(ctx.a.hidden_dep) == id(ctx.b.hidden_dep)


def test_property_with_underscore():
    class TestContext(Context):
        _service1: Service1 = autowired()

        @cached_property
        def _service2(self) -> Service2:
            return self.autowire(Service2)

    ctx = TestContext()

    providers = ctx.container.get_providers()
    assert len(providers) == 2

    provider_names = [c.get_name() for c in providers]

    assert "service1" in provider_names
    assert "service2" in provider_names


def test_singletons():
    class ServiceA:
        pass

    class ServiceB:
        pass

    class ServiceC:
        def __init__(self, a: ServiceA, b: ServiceB):
            self.a = a
            self.b = b

    class ServiceD:
        def __init__(self, a: ServiceA, b: ServiceB):
            self.a = a
            self.b = b

    class ServiceE:
        pass

    class ServiceF:
        pass

    class TestContext(Context):
        service_c: ServiceC = autowired()
        service_d: ServiceD = autowired()
        service_f: ServiceF = provided()

        def __init__(self, service_f: ServiceF):
            self.service_f = service_f

        @property
        def service_b(self) -> ServiceB:
            return self.autowire(ServiceB)

        @cached_property
        def service_e(self) -> ServiceE:
            return self.autowire(ServiceE)

    f = ServiceF()
    ctx = TestContext(f)

    # property should not be singleton
    assert id(ctx.service_c.b) != id(ctx.service_d.b)
    # autowired should be singleton
    assert id(ctx.service_c) == id(ctx.service_c)
    # cached_property should be singleton
    assert id(ctx.service_e) == id(ctx.service_e)
    # provided should be singleton
    assert id(ctx.service_f) == id(ctx.service_f)


def test_property_fields():
    class ServiceA:
        pass

    class ServiceB:
        pass

    @dataclass
    class ServiceC:
        a: ServiceA
        b: ServiceB

    class ServiceD:
        def __init__(self, a: ServiceA, b: ServiceB):
            self.a = a
            self.b = b

    class TestContext(Context):
        service_a: ServiceA = cached_property(lambda self: self.autowire(ServiceA))
        service_b: ServiceB = property(lambda self: self.autowire(ServiceB))

        service_c: ServiceC = autowired()
        service_d: ServiceD = autowired()

    ctx = TestContext()

    assert isinstance(ctx.service_a, ServiceA)
    assert isinstance(ctx.service_b, ServiceB)
    assert isinstance(ctx.service_c, ServiceC)
    assert isinstance(ctx.service_d, ServiceD)

    # cached_property should be singleton
    assert id(ctx.service_c.a) == id(ctx.service_a)
    # property should not be singleton
    assert id(ctx.service_c.b) != id(ctx.service_b)


def test_transient_autowired_field():
    class ServiceA:
        pass

    class ServiceB:
        pass

    class ServiceC:
        def __init__(self, a: ServiceA, b: ServiceB):
            self.a = a
            self.b = b

    class ServiceD:
        def __init__(self, a: ServiceA, b: ServiceB):
            self.a = a
            self.b = b

    class TestContext(Context):
        service_a: ServiceA = autowired()
        service_b: ServiceB = autowired(transient=True)
        service_c: ServiceC = autowired()
        service_d: ServiceD = autowired()

    ctx = TestContext()

    assert id(ctx.service_c.b) != id(ctx.service_d.b)
    assert id(ctx.service_c.a) == id(ctx.service_d.a)

    assert id(ctx.service_b) != id(ctx.service_b)
    assert id(ctx.service_a) == id(ctx.service_a)


def test_inherited_context():
    class ServiceA:
        pass

    class BaseContext(Context):
        service_a: ServiceA = autowired()

    class ServiceB:
        pass

    class ExtendedContext(BaseContext):
        service_b: ServiceB = autowired()

    ctx = ExtendedContext()

    assert isinstance(ctx.service_a, ServiceA)
    assert isinstance(ctx.service_b, ServiceB)


def test_provider_from_supplier():
    instance = Service0()

    def singleton_supplier():
        return instance

    container = Container()
    container.add(Provider.from_supplier(singleton_supplier, Service0))

    assert container.resolve(Service0) is instance
    assert container.resolve(Service0) is container.resolve(Service0)

    # provider should be removed by equality
    def singleton_supplier2():
        return instance

    # should not remove anything
    container.remove(Provider.from_supplier(singleton_supplier2, Service0))
    assert len(container.get_providers()) == 1
    # should remove the provider
    container.remove(Provider.from_supplier(singleton_supplier, Service0))
    assert len(container.get_providers()) == 0

    container = Container()

    def transient_supplier():
        return Service0()

    container.add(Provider.from_supplier(transient_supplier, Service0))

    assert container.resolve(Service0) is not container.resolve(Service0)


def test_provider_factory_methods():
    singleton_provider = Provider.from_instance(Service0())

    assert isinstance(singleton_provider.get_instance(Mock(), Mock()), Service0)
    assert singleton_provider.get_instance(
        Mock(), Mock()
    ) is singleton_provider.get_instance(Mock(), Mock())

    provider_from_type = Provider.from_supplier(Service0)
    assert isinstance(provider_from_type.get_instance(Mock(), Mock()), Service0)
    assert provider_from_type.get_instance(
        Mock(), Mock()
    ) is not provider_from_type.get_instance(Mock(), Mock())

    def supplier_untyped():
        return Service0()

    with pytest.raises(MissingTypeAnnotation):
        Provider.from_supplier(supplier_untyped)

    assert isinstance(
        Provider.from_supplier(supplier_untyped, Service0).get_instance(Mock(), Mock()),
        Service0,
    )

    def supplier_typed() -> Service0:
        return Service0()

    assert isinstance(
        Provider.from_supplier(supplier_typed).get_instance(Mock(), Mock()),
        Service0,
    )


def test_thread_local_component():
    import threading

    class ServiceA:
        def __init__(self):
            self.thread_id = threading.get_ident()

    class ServiceB:
        def __init__(self, service_a: ServiceA):
            self.service_a = service_a
            self.thread_id = threading.get_ident()

    class TestContext(Context):
        service_a: ServiceA = autowired()

        @thread_local_cached_property
        def service_b(self) -> ServiceB:
            return self.autowire(ServiceB)

    ctx = TestContext()
    main_thread_service_b = ctx.service_b

    assert isinstance(main_thread_service_b, ServiceB)
    assert main_thread_service_b is ctx.service_b

    def in_new_thread():
        new_thread_service_b = ctx.service_b
        assert new_thread_service_b is not main_thread_service_b
        assert new_thread_service_b is ctx.service_b

        assert new_thread_service_b.service_a is main_thread_service_b.service_a

    thread = threading.Thread(target=in_new_thread)
    thread.start()
    thread.join()


def test_thread_safe_autowired_field():
    class SlowInitService:
        def __init__(self):
            import time

            time.sleep(0.1)

    class MyContext(Context):
        service: SlowInitService = autowired()

    ctx = MyContext()

    from_thread = None

    def in_thread():
        nonlocal from_thread
        from_thread = ctx.service

    thread = threading.Thread(target=in_thread)
    thread.start()

    from_main = ctx.service

    thread.join()
    assert from_main is from_thread


def test_context_value_selector():
    @dataclass
    class ServiceA:
        foo: str = "bar"

    @dataclass
    class ServiceB:
        foo: str = "baz"

    @dataclass
    class ServiceC:
        foo: object

    @dataclass
    class ServiceD:
        foo: object

    @dataclass
    class InnerConfig:
        foo: str

    class Config:
        def __init__(self, inner: InnerConfig):
            self.inner = inner

    class MyContext(Context):
        config: Config = provided()
        a: ServiceA = autowired(foo=config.inner.foo)
        # noinspection PyUnresolvedReferences
        b: ServiceB = autowired(foo=config.wrong)
        c: ServiceC = autowired(foo=object())
        d: ServiceD = autowired(foo=c.foo)

        def __init__(self, config: Config):
            self.config = config

    ctx = MyContext(Config(InnerConfig("bar")))

    assert ctx.a.foo == "bar"

    with pytest.raises(AttributeError):
        print(ctx.b)

    assert ctx.d.foo is ctx.c.foo
