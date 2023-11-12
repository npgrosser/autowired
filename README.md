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

The heart of _autowired_ is the `Context` class.    
You can think of it as a declarative dependency injection container.

Let's look at an example.    
We start by defining some components in plain Python:

```python
class ComponentA:
    def hello(self, name: str):
        print(f"Hello, {name}!")


class ComponentB:
    def goodbye(self, name: str):
        print(f"Goodbye, {name}!")


class MainComponent:
    def __init__(self, component_a: ComponentA, component_b: ComponentB):
        self.component_a = component_a
        self.component_b = component_b

    def run(self):
        self.component_a.hello("World")
        self.component_b.goodbye("World")

```

Next, we'll define the `Context` class.    
In our application code, we only need to interact with the `MainComponent`, hence it's the only component we explicitly
define.

```python
from autowired import Context, autowired


class ApplicationContext(Context):
    main_component: MainComponent = autowired()
```

Finally, we can utilize it in our application code:

```python
ctx = ApplicationContext()
ctx.main_component.run()
```

In this example, _autowired_ was able to resolve all dependencies automatically.
However, in most real-world applications, you will need more control over the instantiation process.
The following sections will explain all the necessary concepts and advanced features in more detail.

---

## Core Principles

### Dependency Injection

Reusability, maintainability, and testability are important aspects of code quality.
One technique commonly used for achieving this is Dependency Injection (DI).

In essence, DI is about decoupling the creation of objects from their usage.
It encourages a system where dependencies are not built internally,
but provided (or 'injected') externally.
This approach offers the flexibility to replace dependencies without altering the classes using them.

While some might associate DI with complex frameworks, it's primarily a simple but effective design pattern.

A simple example:

1. Without DI:

```python
class TextWriter:
    def write(self, text: str):
        print(text)


class Poet:
    def __init__(self):
        self.writer = TextWriter()

    def write_poem(self):
        self.writer.write("Roses are red, violets are blue...")
```

Here, the `Poet` class is tightly coupled to the `TextWriter` class.
If we wanted to use a different writer, we would have to change the `Poet` class.

2. With DI:

```python
class TextWriter:
    def write(self, text: str):
        print(text)


class Poet:
    def __init__(self, writer: TextWriter):
        self.writer = writer

    def write_poem(self):
        self.writer.write("Roses are red, violets are blue...")
```

Here, the `Poet` class is decoupled from the `TextWriter` class. It can now interact with any class that implements
the `TextWriter` interface without necessitating changes to the `Poet` class itself. This elevates the flexibility and
reusability of the `Poet` class. Moreover, it simplifies testing, as the `Poet` can now be easily tested in isolation
from the `TextWriter`.

Since Dependency Injection relieves the class from creating its own dependencies, these now need to be provided
from the outside.
This naturally leads to the question: Who takes up this responsibility?

In a simple application, this could be the main function. It could be responsible for reading the configuration and
instantiating all the necessary components with the correct dependencies.
This is sufficient for small applications, but it quickly becomes unwieldy as the application grows.
This is especially true if you have multiple entry points and need to reuse the same instantiation logic in different
places such as in a CLI, a web app, or a test suite.

To resolve this, one clean approach is to create a central class that takes over this responsibility and allows access
to all the necessary components. These components could be presented as properties of this class, each tied to the
others during instantiation.

Typically, it's preferable for multiple components to share the same instance (often called
a [singleton](https://en.wikipedia.org/wiki/Singleton_pattern)) of a specific
dependency. In such cases, Python’s built-in `cached_property` decorator is an ideal solution. It functions by saving
the result of a property's initial call and then returns this cached value for any subsequent calls.    
This effectively provides all that's needed for a simple but elegant and reusable form of Dependency Injection in
Python.

Let's look at a more concrete example:

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

And now we create a central class that ties everything together.

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

This approach is already sufficient for many simple applications.
However, as the application becomes larger and more complex, the context class can quickly become bloated.
You'll have more components, increasing interdependencies, and you'll need to
carefully manage the differing life cycles or scopes of each component (e.g. request scoped components, session-scoped
ones, etc.).
As the complexity grows, so does the amount of boilerplate code needed, making it harder to maintain and
increasing the risk for errors.
_Autowired_ aims to streamline this process, while building on the same simple principles.

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

    # we add a constructor to the context class to allow passing in the settings
    def __init__(self, settings: ApplicationSettings = ApplicationSettings()):
        self.settings = settings

    @cached_property
    def _notification_service(self) -> NotificationService:
        return self.autowire(
            NotificationService,
            all_caps=self.settings.all_caps_notifications
        )
```

Now, we can use the context class as before, with the added benefit of being able to configure the notification service
via the `ApplicationSettings`.

```python
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

Using `cached_property` and `property` allows us to define our own factory functions for components.
However, for simple use cases, this is unnecessarily verbose.
To configure your autowired fields with attributes of the
context-instance, you can also directly reference these attributes in the field definition.

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

### Component Lifetime

By default, components function as singletons, meaning the same instance is returned each time they're accessed or
injected from a context. However, situations may arise where a different lifetime for a component is required.
_Autowired_ offers three specific lifetimes within a context: singleton, transient, and thread-local. These can be
applied to both autowired fields and properties, as shown in the table below:

| Lifetime  | Description                                             | Autowired Syntax               | Decorator                       |
|-----------|---------------------------------------------------------|--------------------------------|---------------------------------|
| Singleton | Single shared instance across the context               | `autowired()`                  | `@cached_property`              |
| Transient | A new instance is created whenever accessed or injected | `autowired(transient=True)`    | `@property`                     |
| Thread    | Unique instance per thread                              | `autowired(thread_local=True)` | `@thread_local_cached_property` |

While component lifetimes dictate the policy for instantiation of components within a particular context, determining
whether new instances are created or existing ones are reused, another essential dimension in component lifetime
management exists: the lifetime of the context itself.
The next sections will describe that in more detail.

### Scopes and Derived Contexts

In many applications, components can be bound to a specific scope.
A common example is a web application,
where some components are request-scoped, while others are session-scoped or application-scoped.
Often, these scopes follow a hierarchy; for example, a request scope is part of a session scope, which is part of the
application scope.

While it's certainly possible to manage all these components within a single context, it can sometimes be beneficial to
break them up into multiple contexts.
Each context can then handle its own component instances, while drawing from the parent context if necessary.

The next example demonstrates how this hierarchical structure can be implemented using _autowired_.

```python
from autowired import Context, autowired, provided
import json
from dataclasses import dataclass


# application scope

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


# request scope

@dataclass
class HttpRequest:
    headers: dict[str, str]
    parameters: dict[str, str]


class HttpRequestHandler:

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
        self.derive_from(parent_context)
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

```python
class ApplicationContext(Context):
    notification_controller: NotificationController = autowired(eager=True)
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

For more information on how to use the `Container` class, refer to its code documentation.

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
It does not aim to fully replace FastAPI's dependency injection, but rather demonstrates
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

