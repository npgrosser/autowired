from typing import List

import pytest

import tests.component_scan_test_module
from autowired import Container, Dependency
from tests.component_scan_test_module import Controller


def test_component_scan():
    container = Container()

    container.component_scan(tests.component_scan_test_module)

    providers = container.get_providers()
    assert len(providers) == 7

    components = container.resolve(Dependency("components", List[Controller]))

    assert len(components) == 7

    component_class_names = set(type(c).__name__ for c in components)

    assert component_class_names == {
        "FileComponent",
        "FileComponentInitExposed",
        "RootModuleComponent",
        "TestPackageRootComponent",
        "TestPackageFileComponent",
        "TestPackageFileComponentInitExposed",
        "TransientComponent",
    }

    for provider in providers:
        expect_singleton = provider.get_name() != "transient_component"

        instance1 = provider.get_instance(Dependency("instance1", object), container)
        instance2 = provider.get_instance(Dependency("instance2", object), container)

        assert (instance1 is instance2) == expect_singleton


def test_component_scan_invalid_module():
    container = Container()

    with pytest.raises(TypeError):
        container.component_scan("tests.component_scan_test_module")
