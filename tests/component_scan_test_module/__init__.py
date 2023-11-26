from autowired import component
from tests.component_scan_test_module.controller import Controller
from tests.component_scan_test_module.file_module import FileComponentInitExposed


@component
class RootModuleComponent(Controller):
    pass


class RootModuleNotComponent(Controller):
    pass
