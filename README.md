# autowired

A minimalistic dependency injection library for Python.

[![PyPI - License](https://img.shields.io/pypi/l/autowired)](https://github.com/npgrosser/autowired/blob/main/LICENSE)
[![PyPI - Version](https://img.shields.io/pypi/v/autowired?color=blue)](https://pypi.org/project/autowired/)
[![Codecov](https://img.shields.io/codecov/c/github/npgrosser/autowired)](https://codecov.io/gh/npgrosser/autowired)

## Installation

```bash
pip install autowired
```

## Quick Start

With _autowired_, everything is centered around context classes.     
A context can be viewed as a higher-level layer on top of a dependency injection container.
It can also be perceived as the in-code configuration of the application's components (e.g., services, controllers,
repositories, etc.).

Let's create a simple first example application.    
The demo application mimics a notification service that sends messages to users.    
We begin by defining the components of our application.

```python
class MessageService:
    def send_message(self, user: str, message: str):
        print(f"Sending message '{message}' to user '{user}'")


class UserService:
    def get_user(self, user_id: int) -> str:
        return f"User{user_id}"


class NotificationService:
    def __init__(self, message_service: MessageService, user_service: UserService):
        self.message_service = message_service
        self.user_service = user_service

    def send_notification(self, user_id: int, message: str):
        user = self.user_service.get_user(user_id)
        self.message_service.send_message(user, message)

```

Next, we'll define a context class for this application.    
The sole responsibility of this class is to set up the application components.

```python
from autowired import Context, autowired


class ApplicationContext(Context):
    notification_service: NotificationService = autowired()
```

Finally, we can utilize the context to access and use the application components.

```python
ctx = ApplicationContext()
ctx.notification_service.send_notification(1, "Hello, User!")
```

In our application code, we only interact with the `notification_service`, hence it's the only component we explicitly
define in the context class.

Note that the `ApplicationContext` is the only class that depends on the _autowired_ library.
All the components that implement the actual application logic are completely framework-agnostic and
don't require any special annotations or decorators.
This is a fundamental design principle of _autowired_.

Here are some other important things to point out:

1. Lazy instantiation:  
   `autowired` fields are instantiated lazily _by default_. This means they are instantiated the first time they are
   accessed.
   This can help reduce the startup time of your application and allows the use of a context even if some of its
   components cannot be instantiated (for example, due to missing configuration or unavailability of external services).
2. Singletons:  
   _By default_, `autowired` fields and all implicit dependencies are singletons.
   This implies that the same instance is returned every time they are accessed or injected.

In this initial example, _autowired_ did all the work for us.
However, in most real-world applications, you will need more control over the instantiation process.
The following sections will explain all the necessary concepts and advanced features in more detail.

---

## Core Principles

### Dependency Injection without Frameworks

[Dependency Injection](https://en.wikipedia.org/wiki/Dependency_injection) is a simple yet powerful concept designed to
improve the decoupling of components in code. Although
it's often associated with certain frameworks, its implementation doesn’t necessarily require one.

One simple framework-free approach involves defining a central class, which is responsible for instantiating all the
necessary components (e.g., services, repositories, controllers, etc.) of an application.
These components are presented as properties of this class, each tying to the others during instantiation.

Typically, it's preferable for multiple components to share the same instance (often called
a [singleton](https://en.wikipedia.org/wiki/Singleton_pattern)) of a specific
dependency. In such cases, Python’s built-in `cached_property` decorator is an ideal solution. It functions by saving
the result of a property's initial call and then returns this cached value for any subsequent calls.    
This effectively provides all that's needed for a simple but elegant form of Dependency Injection in Python.

Let's look at a simple example:

```python
from dataclasses import dataclass


# define some components

class MessageService:
    def send_message(self, user: str, message: str):
        print(f"Sending message '{message}' to user '{user}'")


class UserService:
    def get_user(self, user_id: int):
        return f"User{user_id}"


@dataclass
class NotificationService:
    message_service: MessageService
    user_service: UserService
    all_caps: bool = False

    def send_notification(self, user_id: int, message: str):
        user = self.user_service.get_user(user_id)

        if self.all_caps:
            message = message.upper()

        self.message_service.send_message(user, message)


@dataclass
class NotificationController:
    notification_service: NotificationService

    def notify(self, user_id: int, message: str):
        print(f"Sending notification to user {user_id}")
        self.notification_service.send_notification(user_id, message)
```

And then we create a central class that ties everything together.
In our case it's life cycle is tied to the application itself, so we call it `ApplicationContext`.
In practice, there might be multiple such classes, each with a different life cycle or scope (e.g., `RequestContext`,
`SessionContext`, etc.).

```python
from functools import cached_property


class ApplicationContext:

    @cached_property
    def message_service(self) -> MessageService:
        return MessageService()

    @cached_property
    def user_service(self) -> UserService:
        return UserService()

    @cached_property
    def notification_service(self) -> NotificationService:
        return NotificationService(
            message_service=self.message_service,
            user_service=self.user_service
        )

    @cached_property
    def notification_controller(self) -> NotificationController:
        return NotificationController(
            notification_service=self.notification_service
        )


ctx = ApplicationContext()
ctx.notification_controller.notify(1, "Hello, User!")
```

In this setup, the `ApplicationContext` is responsible for managing the dependencies between components. Using
the `cached_property` decorator ensures that each component is instantiated only once, even if it's accessed multiple
times.

This approach is sufficient for many simple applications.
However, as the application becomes larger and more complex, the context class can quickly become bloated.
You'll have more components, increasing interdependencies, and you'll need to
carefully manage the differing life cycles or scopes of each component (e.g. request scoped components, session-scoped
ones, etc.).
As the complexity grows, so does the amount of boilerplate code needed, making it harder to maintain and
increasing the risk for errors.
_Autowired_ aims to streamline this process, while building on the exact same simple principles.

### Using autowired

Here's how the previous `ApplicationContext` could be rewritten using _autowired_:

```python
from autowired import Context, autowired


class ApplicationContext(Context):
    notification_controller: NotificationController = autowired()

```

We have simplified the context class to a single line of code.
As the `NotificationController` was the only component
that needed to be exposed as a public property, it is the only one we explicitly define.
_Autowired_ now handles the instantiation of all components and their dependencies for us.
Components can be either dataclasses or traditional classes, provided they are appropriately annotated with type hints
for _autowired_ to automatically resolve their dependencies.

## Configuration

Autowired provides several ways to configure the instantiation of components within a context.
Some of them are more convenient, while others offer more flexibility.

### Leveraging `cached_property` and `property` methods

Using `cached_property` and `property` methods is the most flexible way to configure the instantiation of
components, as it gives you full control over the process.
As mentioned before, _autowired_ builds on the idea of using `cached_property` to implement the singleton pattern.
That's
why `cached_property` is a first-class citizen in _autowired_.
When _autowired_ resolves dependencies, it does not only respect other `autowired` fields but also `cached_property`
as well as `property` methods.

Here is an example of how to make use of this to configure the `NotificationService` from the previous example:

```python
# We define a dataclass to represent our application settings
@dataclass
class ApplicationSettings:
    all_caps_notifications: bool = False


class ApplicationContext(Context):
    notification_controller: NotificationController = autowired()

    # we add a constructor to the context class to allow passing the settings
    def __init__(self, settings: ApplicationSettings = ApplicationSettings()):
        self.settings = settings

    @cached_property
    def _notification_service(self) -> NotificationService:
        # we use `self.autowire()` to resolve the dependencies of the notification service,
        # while passing a subset of the dependencies explicitly as kwargs
        return self.autowire(
            NotificationService,
            all_caps=self.settings.all_caps_notifications
        )


settings = ApplicationSettings(all_caps_notifications=True)
ctx = ApplicationContext(settings=settings)
ctx.notification_controller.notify(1, "Hello, User!")

assert ctx.notification_controller.notification_service.all_caps == True
```

The `autowire` method behaves very similarly to the `autowired` field, but it is meant to be used to
directly instantiate components, rather than to define them as fields.
Explicit dependencies can be passed as kwargs, as shown in the example above, while the remaining ones will be resolved
automatically as before.

### Configuring Autowired Fields with Context Attributes

To configure your autowired fields with attributes of the context-instance,
you can also directly reference these attributes in the field definition.

Here is how you could rewrite the previous example:

```python
class ApplicationContext(Context):
    settings: ApplicationSettings = provided()
    notification_controller: NotificationController = autowired()
    _notification_service: NotificationService = autowired(all_caps=settings.all_caps_notifications)

    def __init__(self, settings: ApplicationSettings = ApplicationSettings()):
        self.settings = settings
```

To make the settings field available in the autowired field definition, we need to define it explicitly.
Note that we use `provided()` instead of `autowired()` because the field is manually set in the constructor.

Which of the two approaches you prefer is a matter of taste or the complexity of evaluating the settings. For simple
settings, the second approach should be preferred.
For more complex rules, the `cached_property` approach might be more suitable. Both approaches can be mixed freely.

### Advanced Configuration with Kwargs Factory Function

For more complex configuration scenarios, you can use a kwargs factory function with autowired fields. This approach
provides a balance between simplicity and flexibility, allowing you to define custom logic for setting up your autowired
fields directly in the field definition.

The factory function receives the context instance as its only argument during the component's instantiation.
This allows you to access any attribute of the context and use it in your configuration logic.
It should return a dictionary of kwargs that will be passed to the component's constructor.
As before, the remaining dependencies will be resolved automatically.

Here's how you can apply it:

```python
class ApplicationContext(Context):
    notification_controller: NotificationController = autowired()
    _notification_service: NotificationService = autowired(
        lambda self: dict(all_caps=self.settings.all_caps_notifications)
    )

    def __init__(self, settings: ApplicationSettings = ApplicationSettings()):
        self.settings = settings
```

As always, you can freely mix and match the approaches within a single context class.

## Recap — The Building Blocks

We already covered the most important building blocks of _autowired_.

- `Context` serves as the base class for all classes that manage dependencies between components.
- `autowired()` defines autowired fields.
- `@cached_property` and `@property` offer more control over the instantiation process.
- `self.autowire()` is a helper method for implementing `@cached_property` and `@property` methods on context classes.

## Advanced Features

### Eager and Lazy Instantiation

`autowired()` fields behave like `cached_property`s and are instantiated lazily, i.e., the first time they are accessed.
If this is not the desired behavior, you can use the `eager` parameter to force eager instantiation of the component.

```python
class ApplicationContext(Context):
    notification_controller: NotificationController = autowired(eager=True)
```

### Transient Components

There may be situations where you need to create a new instance of a component each time it's injected or accessed from
the context.
This is also known as a component with a transient lifetime.
You can accomplish this by setting the 'transient' parameter to 'True' when defining an 'autowired' field.

```python
class ApplicationContext(Context):
    notification_controller: NotificationController = autowired(transient=True)


ctx = ApplicationContext()

# A new instance is created each time the notification controller is accessed
assert id(ctx.notification_controller) != id(ctx.notification_controller)
```

For property methods, use the `property` decorator instead of `cached_property` to achieve the same effect.

### Thread Local Components

Besides singletons and transient components, there is a third type of component lifetime: thread-local.
For autowired fields, you can set the `thread_local` parameter to `True` to make the component thread-local.

```python
class ApplicationContext(Context):
    notification_controller: NotificationController = autowired(thread_local=True)
```

Each thread will now get its own instance of the component when it is injected or accessed from the context.
The same can be achieved for property methods by using the `thread_local_cached_property` decorator.

### Scopes and Derived Contexts

Often a single context is not sufficient to manage all the dependencies of an application. Instead, many applications
will have multiple contexts, often sharing some components. A classic example is a request context, derived from an
application context.

```python
from dataclasses import dataclass
from autowired import Context, autowired, provided


# application scoped component

@dataclass
class AuthService:
    api_keys: list[str]

    def check_api_key(self, key: str) -> bool:
        return key in self.api_keys


# an example request object (e.g., from a web framework)
@dataclass
class Request:
    headers: dict[str, str]


s


# request scoped component

@dataclass
class RequestService:
    auth_service: AuthService
    request: Request

    def is_authorised(self) -> bool:
        api_key = self.request.headers.get("Authorization") or ""
        api_key = api_key.replace("Bearer ", "")
        return self.auth_service.check_api_key(api_key)


# application settings and context

@dataclass
class ApplicationSettings:
    api_keys: list[str]


class ApplicationContext(Context):
    auth_service: AuthService = autowired(
        lambda self: dict(api_keys=self.settings.api_keys)
    )

    def __init__(self, settings: ApplicationSettings):
        self.settings = settings


# request scoped context

class RequestContext(Context):
    request_service: RequestService = autowired()
    # `provided` fields are not resolved automatically, but must be set explicitly in the constructor.
    # As `autowired` fields, `property`s and `cached_property`s, they are respected during dependency resolution.
    # If you forget to set them, _autowired_ will raise an exception on context instantiation.
    request: Request = provided()

    def __init__(self, parent_context: Context, request: Request):
        # We use `self.derive_from` to make the components of the parent context available in the request context.
        self.derive_from(parent_context)
        self.request = request


# example usage

settings = ApplicationSettings(api_keys=["123", "456"])
application_ctx = ApplicationContext(settings)


def create_request_context(request: Request):
    return RequestContext(application_ctx, request)


def request_handler(request: Request):
    ctx = create_request_context(request)
    if ctx.request_service.is_authorised():
        return "Authorised"
    else:
        raise Exception("Not authorised")


# applying the request handler to an example request

dummy_request = Request(headers={
    "Authorization": "Bearer 123"
})
response = request_handler(dummy_request)
print(response)

```

### The Container

Most of the time, using the `Context` class is sufficient for managing dependencies between components.
However, since it requires knowing upfront which components will be needed, it might not be suitable for all use cases.
Therefore, if you need more flexibility, you can use the `Container` class instead.
You can instantiate a container yourself or access a context's container via the `container` property.

```python
from autowired import Container


class MessageService:
    def send_message(self, user: str, message: str):
        print(f"Sending message '{message}' to user '{user}'")


class UserService:
    def get_user(self, user_id: int):
        return f"User{user_id}"


class NotificationService:
    def __init__(self, message_service: MessageService, user_service: UserService):
        self.message_service = message_service
        self.user_service = user_service

    def send_notification(self, user_id: int, message: str):
        user = self.user_service.get_user(user_id)
        self.message_service.send_message(user, message)


container = Container()
notification_service = container.resolve(NotificationService)

assert isinstance(notification_service, NotificationService)
assert notification_service is container.resolve(NotificationService)
assert notification_service.message_service is container.resolve(MessageService)
```

#### Provider

A container can contain a list of providers (instances of the `Provider` class).
A provider is what actually creates the instances of a component.
Most of the time, especially when using the `Context` class, you don't need to worry about providers, as they are
created automatically.
The `Provider` class defines a simple interface that the `Container` class uses to resolve dependencies.

```python
class Provider(Generic[T]):

    def satisfies(self, dependency: Dependency) -> bool:
        # Checks whether the provider can provide an instances that satisfies the given dependency specification.
        ...

    def get_instance(self, dependency: Dependency, container: Container) -> T:
        # Returns an instance that satisfies the given dependency specification.
        ...

    def get_name(self) -> str:
        # Each provider has a name. The container utilises it to resolve ambiguous dependencies.
        ...

```    

Most providers are singleton component providers, i.e., they always return the same instance when `get_instance()` is
called.
In the above container usage example, when we resolved the `NotificationService` for the first time,
a singleton provider was
created automatically and added to the container.
However, you can also add providers manually.   
In most cases you use the `from_supplier` or `from_instance` factory methods to create a provider,
but you can also implement your own `Provider` subclass.
In the following example, we use the `from_supplier` factory method to create a transient provider for a custom
`MessageService` class.

```python
from autowired import Container, Provider

container = Container()


class AllCapsMessageService(MessageService):
    def send_message(self, user: str, message: str):
        super().send_message(user, message.upper())


def create_message_service() -> MessageService:
    return AllCapsMessageService()


# Using `from_supplier` calls the given supplier function each time 
# Note that the return type annotation on the supplier function is mandatory
# unless you specify the type argument explicitly
container.add(Provider.from_supplier(create_message_service))

assert isinstance(container.resolve(MessageService), AllCapsMessageService)
assert container.resolve(MessageService) is not container.resolve(MessageService)

```

---

## Example Application — FastAPI

Although FastAPI already provides a powerful dependency injection mechanism, you might want to reuse your
autowired-based context classes.
The following example shows how to use autowired in a FastAPI application.
It does not aim to replace FastAPI's dependency injection, but rather demonstrates
how to seamlessly combine both approaches.

```python
from dataclasses import dataclass
from autowired import Context, autowired, provided


# Components

@dataclass
class DatabaseService:
    conn_str: str

    def load_allowed_tokens(self):
        return ["123", "456", ""]

    def get_user_name_by_id(self, user_id: int) -> str | None:
        print(f"Loading user {user_id} from database {self.conn_str}")
        d = {1: "John", 2: "Jane"}
        return d.get(user_id)


@dataclass
class UserService:
    db_service: DatabaseService

    def get_user_name_by_id(self, user_id: int) -> str | None:
        if user_id == 0:
            return "admin"
        return self.db_service.get_user_name_by_id(user_id)


@dataclass
class UserController:
    user_service: UserService

    def get_user(self, user_id: int) -> str:
        user_name = self.user_service.get_user_name_by_id(user_id)
        if user_name is None:
            raise HTTPException(status_code=404, detail="User not found")

        return user_name


# Application Settings and Context


@dataclass
class ApplicationSettings:
    database_connection_string: str = "db://localhost"


# Application Context


class ApplicationContext(Context):
    user_controller: UserController = autowired()
    database_service: DatabaseService = autowired(
        lambda self: dict(conn_str=self.settings.database_connection_string)
    )

    def __init__(self, settings: ApplicationSettings = ApplicationSettings()):
        self.settings = settings


from fastapi import FastAPI, Request, Depends, HTTPException


# Request Scoped Service for the FastAPI Application


@dataclass
class RequestAuthService:
    db_service: DatabaseService
    request: Request

    def is_authorised(self):
        token = self.request.headers.get("Authorization") or ""
        token = token.replace("Bearer ", "")
        if token in self.db_service.load_allowed_tokens():
            return True
        return False


# Request Context


class RequestContext(Context):
    request_auth_service: RequestAuthService = autowired()
    request: Request = provided()

    def __init__(self, parent_context: Context, request: Request):
        self.derive_from(parent_context)
        self.request = request


# Setting up the FastAPI Application

app = FastAPI()
application_context = ApplicationContext()


def request_context(request: Request):
    return RequestContext(application_context, request)


# We can seamlessly combine autowired's and FastAPIs dependency injection mechanisms
def request_auth_service(request_context: RequestContext = Depends(request_context)):
    return request_context.request_auth_service


def user_controller():
    return application_context.user_controller


@app.get("/users/{user_id}")
def get_user(
        user_id: int,
        request_auth_service: RequestAuthService = Depends(request_auth_service),
        user_controller=Depends(user_controller),
):
    if request_auth_service.is_authorised():
        return user_controller.get_user(user_id=int(user_id))
    else:
        return {"detail": "Not authorised"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app)

    # http://127.0.0.1:8000/users/0 should now return "admin"
```

