from abc import ABC


class AutowiredException(Exception, ABC):
    """
    Base class for all library exceptions.
    """

    pass


class MissingTypeAnnotation(AutowiredException):
    """
    Raised when a field or property is not annotated with a type hint.
    """

    pass


class IllegalAutoWireType(AutowiredException):
    """
    Raised when an object of a type that is not allowed to be auto-wired is auto-wired.
    """

    pass


class AmbiguousDependencyException(AutowiredException):
    """
    Raised when a dependency cannot be resolved because multiple candidates are found
    and none of them matches the name of the dependency.
    """

    pass


class UnresolvableDependencyException(AutowiredException):
    """
    Raised when a dependency cannot be resolved.
    """

    pass


class InstantiationError(AutowiredException):
    """
    Raised when an object cannot be instantiated.
    """

    pass


class ContextError(AutowiredException, ABC):
    """
    Base class for all context-related errors.
    """

    pass


class IllegalContextClass(ContextError):
    """
    Raised when a class is used as a context class not allowed to be used as such.
    """

    pass


class NotProvidedException(ContextError):
    """
    Raised when a provided field is not initialized.
    """

    pass
