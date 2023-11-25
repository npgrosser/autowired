from autowired import component
from tests.component_scan_test_module.file_module import FileComponentInitExposed


@component
class RootModuleComponent:
    pass


class RootModuleNotComponent:
    pass
