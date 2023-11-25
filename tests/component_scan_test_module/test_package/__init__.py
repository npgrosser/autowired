from autowired import component
from tests.component_scan_test_module.test_package.file_module import (
    TestPackageFileComponentInitExposed,
)


@component
class TestPackageRootComponent:
    pass


class TestPackageRootNotComponent:
    pass
