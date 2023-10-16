from dataclasses import dataclass

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
    InitializationError,
    BeanConflictException,
    NotProvidedException,
    IllegalContextClass,
    MissingTypeAnnotation,
    Bean,
    provided,
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
            self.parent_context = parent_context

    derived_context = DerivedContext(ctx)
    derived_context.container.register(Bean.from_instance(ServiceX("foo")))
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

    with pytest.raises(InitializationError):
        container.autowire(TestService)


def test_unregister_dependency():
    container = Container()
    s0 = Service0()
    container.register(Bean.from_instance(s0))

    s0_resolved = container.resolve(Service0)

    assert id(s0) == id(s0_resolved)

    container.unregister("service0")

    s0_resolved2 = container.resolve(Service0)

    assert id(s0) != id(s0_resolved2)


def test_conflicting_bean():
    container = Container()
    container.register(Bean.from_instance(Service0()))
    with pytest.raises(BeanConflictException):
        container.register(Bean.from_instance(Service0()))


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
    ctx.container.register(Bean.from_instance(service_b))

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
    ctx.container.register(x)

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


def test_component_reuses_base_init():
    class Dep:
        pass

    class BaseComponent:
        def __init__(self, dep: Dep):
            self.dep = dep

    class Component(BaseComponent):
        pass

    class TestContext(Context):
        component: Component = autowired()

    ctx = TestContext()
    assert isinstance(ctx.component.dep, Dep)
