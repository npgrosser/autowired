import pytest

from autowired import thread_local_cached_property


def test_thread_local_cached_property_value():
    next_id = 0

    class TestClass:
        @thread_local_cached_property
        def value(self):
            nonlocal next_id
            next_id += 1
            return next_id

    instance = TestClass()
    assert instance.value == 1
    assert instance.value == 1

    def in_new_thread():
        assert instance.value == 2
        assert instance.value == 2

    import threading

    thread = threading.Thread(target=in_new_thread)
    thread.start()
    thread.join()

    assert instance.value == 1


def test_double_assignment_thread_local_cached_property():
    class MyClass:
        pass

    def f():
        pass

    descriptor = thread_local_cached_property(f)

    descriptor.__set_name__(MyClass, "attr1")

    with pytest.raises(TypeError) as exc_info:
        descriptor.__set_name__(MyClass, "attr2")


def test_thread_local_cached_property_without_set_name():
    class TestClass:
        pass

    test_instance = TestClass()

    prop_without_set_name = thread_local_cached_property(lambda x: x)

    with pytest.raises(TypeError):
        prop_without_set_name.__get__(test_instance)


def test_access_class_property():
    class TestClass:
        @thread_local_cached_property
        def value(self):
            return 1

    assert isinstance(TestClass.value, thread_local_cached_property)
    assert TestClass().value == 1
