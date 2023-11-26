from autowired import component
from tests.component_scan_test_module import Controller


@component
class TestPackageFileComponent(Controller):
    pass


@component
class TestPackageFileComponentInitExposed(Controller):
    pass


@component(transient=True)
class TransientComponent(Controller):
    pass


class TestPackageFileNotComponent(Controller):
    pass
