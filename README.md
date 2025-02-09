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

Define some plain Python classes that represent your components:

```python
class GreetingService:
    def greet(self, name: str):
        print(f"Hello, {name}!")


class FarewellService:
    def farewell(self, name: str):
        print(f"Goodbye, {name}!")


class WorldService:
    def __init__(self, greeting_service: GreetingService, farewell_service: FarewellService):
        self.greeting_service = greeting_service
        self.farewell_service = farewell_service

    def run(self):
        self.greeting_service.greet("World")
        self.farewell_service.farewell("World")

```

A Context is a declarative dependency container and responsible for wiring up the components.

```python
from autowired import Context, autowired


class ApplicationContext(Context):
    world_service: WorldService = autowired()  # dependencies are resolved automatically
```

Use the context to initialize and run your application:

```python
ctx = ApplicationContext()
ctx.world_service.run()
```

In most real-world applications, you will need more control over the instantiation process.
The following sections will explain the necessary concepts and features in more detail.

---

## Configuration

Autowired provides several ways to configure the instantiation of components within a context.
Some of them are more convenient, while others offer more flexibility.

### Leveraging `cached_property` and `property` methods

Using `cached_property` and `property` methods is the most flexible way to configure the instantiation of
components, as it gives you full control over the process.

```python
from dataclasses import dataclass
from autowired import Context, cached_property


# Application components (services)
class MessageService:
    """
    A simple service that mimics sending messages to users.
    """

    def send_message(self, user_id: str, message: str):
        print(f"Sending message '{message}' to user '{user_id}'")


@dataclass
class NotificationService:
    """
    Simple notification service that relies on a message service to send notifications to users.
    """
    message_service: MessageService
    all_caps: bool = False

    def send_notification(self, user_id: str, message: str):
        if self.all_caps:
            message = message.upper()

        self.message_service.send_message(user_id, message)


# We define a dataclass to represent our application settings
@dataclass
class ApplicationSettings:
    all_caps_notifications: bool = False


class ApplicationContext(Context):

    # Settings can be passed to the context constructor
    def __init__(self, settings: ApplicationSettings = ApplicationSettings()):
        self.settings = settings

    @cached_property
    def _notification_service(self) -> NotificationService:
        # Instead of fully autowiring the notification service, we can explicitly pass specific dependencies.
        # All remaining dependencies will be resolved automatically as usual.
        return self.autowire(
            NotificationService,
            all_caps=self.settings.all_caps_notifications
        )
```

```python
settings = ApplicationSettings(all_caps_notifications=True)
ctx = ApplicationContext(settings=settings)
ctx.notification_controller.notify("user1", "Hello, User 1!")
```

The `autowire` method behaves very similarly to the way `autowired` fields are resolved, with the extra benefit of
allowing to explicitly define dependencies via kwargs instead of relying on autowiring.
Additional dependencies will still be resolved automatically.

### Configuring Autowired Fields with Context Attributes

Using `cached_property` and `property` allows us to define our own factory functions for components.
However, for simple use cases, it is enough to configure autowired fields directly in the field definition.
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

### Advanced Configuration with Kwargs Factory Function

For more complex configuration scenarios, you can use a kwargs factory function with autowired fields. This approach
provides a balance between simplicity and flexibility, allowing you to define custom logic for setting up your autowired
fields directly in the field definition.

Following is equivalent to the previous example, but using a factory function to configure the `_notification_service`

```python
class ApplicationContext(Context):
    notification_controller: NotificationController = autowired()
    _notification_service: NotificationService = autowired(
        lambda self: dict(all_caps=self.settings.all_caps_notifications)
    )

    def __init__(self, settings: ApplicationSettings = ApplicationSettings()):
        self.settings = settings
```

## Advanced Features

### Component Lifetime

By default, components function as singletons, meaning the same instance is returned each time they're accessed or
injected from a context.
_Autowired_ offers three specific lifetimes within a context: singleton, transient, and thread-local. These can be
applied to both autowired fields and properties, as shown in the table below:

| Lifetime  | Description                                             | Autowired Syntax               | Decorator                       |
|-----------|---------------------------------------------------------|--------------------------------|---------------------------------|
| Singleton | Single shared instance across the context               | `autowired()`                  | `@cached_property`              |
| Transient | A new instance is created whenever accessed or injected | `autowired(transient=True)`    | `@property`                     |
| Thread    | Unique instance per thread                              | `autowired(thread_local=True)` | `@thread_local_cached_property` |

### Scopes and Derived Contexts

In many applications, component instances should be bound to a specific scope.
A common example is a web application,
where some components are request-scoped, while others are session-scoped or application-scoped.
Often, these scopes follow a hierarchy; for example, a request scope is part of a session scope, which is part of the
application scope.

While it's possible to manage all these components within a single context, it can sometimes be beneficial to
break them up into multiple hierarchical contexts.
Each context can then handle its own component instances, while drawing from the parent context if necessary.

The next example demonstrates how this hierarchical structure can be implemented using _autowired_.

```python
from autowired import Context, autowired, provided
import json
from dataclasses import dataclass


# application scoped components

class DatabaseService:

    def __init__(self, connection_string: str):
        self.connection_string = connection_string

    def get_api_keys(self):
        print(f"Fetching API keys from the database...")
        return ["123", "456", ""]

    def get_user_data(self, user_id: str):
        print(f"Fetching data for user {user_id} from the database...")
        return {"name": "John Doe", "email": "john.doe@example.com"}


@dataclass
class ApplicationSettings:
    db_connection_string: str = "db://localhost"


class ApplicationContext(Context):
    settings: ApplicationSettings = provided()
    database_service: DatabaseService = autowired(connection_string=settings.db_connection_string)

    def __init__(self, settings: ApplicationSettings):
        self.settings = settings


# request scoped components

@dataclass
class HttpRequest:
    headers: dict[str, str]
    parameters: dict[str, str]


class HttpRequestHandler:

    # because the RequestContext derives from the ApplicationContext (derive_from(parent_context)),
    # it has access to all components defined in the parent context. E.g., the DatabaseService.
    def __init__(self, database_service: DatabaseService, http_request: HttpRequest):
        self.database_service = database_service
        self.http_request = http_request

    def handle_request(self) -> str:
        api_key = self.http_request.headers.get("Authorization") or ""
        if api_key in self.database_service.get_api_keys():
            print("User is authorised")
            user_id = self.http_request.parameters.get("user_id")
            user_data = self.database_service.get_user_data(user_id)
            return json.dumps(user_data)
        else:
            raise Exception("Not authorised")


class RequestContext(Context):
    http_request: HttpRequest = provided()
    http_request_handler: HttpRequestHandler = autowired()

    def __init__(self, parent_context: Context, http_request: HttpRequest):
        self.derive_from(parent_context)  # inherit all components from the parent context
        self.http_request = http_request


# example usage

settings = ApplicationSettings(db_connection_string="db://localhost")
app_context = ApplicationContext(settings)

# Create a dummy HTTP request
http_request = HttpRequest(headers={"Authorization": "123"}, parameters={"user_id": "1"})

# Create a request context for the dummy request
request_context = RequestContext(app_context, http_request)

# Use the HttpRequestHandler to handle the request
response = request_context.http_request_handler.handle_request()

print(response)

```

### Eager and Lazy Instantiation

By default, `autowired()` fields behave like `cached_property`s and are instantiated lazily,
i.e., the first time they are accessed.
If this is not the desired behavior, you can use the `eager` parameter to force eager instantiation of the component.
Eager means the component is instantiated as soon as the context is created.

```python
class ApplicationContext(Context):
    notification_controller: NotificationController = autowired(eager=True)
```


### List Injection

Sometimes, you might want to inject a list of all components that implement a specific interface.
This is especially useful when you want to implement a plugin system.

```python
from autowired import Context, autowired
from abc import ABC, abstractmethod


class Plugin(ABC):
    @abstractmethod
    def run(self):
        ...


class PluginA(Plugin):
    def run(self):
        print("Plugin A")


class PluginB(Plugin):
    def run(self):
        print("Plugin B")


class PluginManager:
    def __init__(self, plugins: list[Plugin]):
        self.plugins = plugins

    def run_all(self):
        for plugin in self.plugins:
            plugin.run()


class ApplicationContext(Context):
    plugin_manager: PluginManager = autowired()


# usage

ctx = ApplicationContext()

ctx.container.add(PluginA())
ctx.container.add(PluginB())

ctx.plugin_manager.run_all()

```

### Component Scan

In many applications, you might want to automatically discover all components in a specific package.

You can use the `@component` decorator to mark a class as a component.
When you call `component_scan()` on a container, it will automatically discover all decorated components in the given package
and add them to the dependency container.

```python
# my_module/services/__init__.py

from autowired import component


@component
class SomeService:
    def run(self):
        print("Running Service 1")


@component
class SomeOtherService:
    def run(self):
        print("Starting Service 2")


# my_module/main.py

from autowired import Context, autowired
from my_module import services



class ApplicationContext(Context):
    # ...

    def __init__(self):
        # register all components from the services package
        self.container.component_scan(services)


```

---

### The Container

*Lower level API*

Instead of using the declarative `Context` abstraction, you can also use the `Container` class directly.
The `Container` class gives you generally more control than using the `Context` class.

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

For more information, refer to the `Container` code documentation.

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