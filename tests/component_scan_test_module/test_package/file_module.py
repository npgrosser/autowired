from autowired import component


@component
class TestPackageFileComponent:
    pass


@component
class TestPackageFileComponentInitExposed:
    pass


@component(transient=True)
class TransientComponent:
    pass


class TestPackageFileNotComponent:
    pass
