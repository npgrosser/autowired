from autowired import component
from tests.component_scan_test_module.controller import Controller


@component
class FileComponent(Controller):
    pass


@component
class FileComponentInitExposed(Controller):
    pass


class FileNotComponent(Controller):
    pass
