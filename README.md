# autowired


A minimalistic dependency injection library for Python.

[![PyPI version](https://badge.fury.io/py/autowired.svg)](https://badge.fury.io/py/autowired)

## Installation

```bash
pip install autowired
```

## Dependency Injection Without a Framework

Dependency Injection is a simple but powerful pattern that aids in decoupling components. However, it doesn't
necessarily require a
framework for implementation. Python already provides some tools that are a perfect fit for implementing dependency
injection. A simple pattern that often works well is using a central context class to manage the dependencies between
components, exposing components as properties of the context class. For defining singletons, the `cached_property`
decorator, part of the Python standard library, can be used. This decorator caches the result of property methods,
making it ideal for implementing the singleton pattern.

Here's a simple example:

```python
from dataclasses import dataclass
from functools import cached_property


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


# define a context class to manage the dependencies between components

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

In this setup, a single context class is responsible for managing the dependencies between components.
This approach is sufficient for many applications. However, as the application grows, the context class will become
increasingly bloated. You will have more components, and their interdependencies will become more complex. You will also
have to deal with different scopes, e.g., request scoped components. This complexity can lead to a lot of boilerplate
code unrelated to the application logic and create opportunities for bugs. _autowired_ aims to provide tools to make
this process easier, while building on the same simple principles.

## Using autowired

Here's how we can rewrite the previous `ApplicationContext` using _autowired_.

```python
from autowired import Context, autowired


class ApplicationContext(Context):
    notification_controller: NotificationController = autowired()

```

We have simplified the context class to a single line of code.
As the `NotificationController` was the only component
that needed to be exposed as a public property, it is the only one we explicitly define.
_autowired_ now handles the instantiation of all components and their dependencies for us.
Components can be either dataclasses or traditional classes.
The only requirement is that they are properly annotated with type hints to allow _autowired_ to resolve their
dependencies automatically.

Note that the component classes remain unaware of the context and the _autowired_ library.
They don't require any special base class or decorators. This is a fundamental design principle of _autowired_.

## Leveraging cached_property with autowired

Sometimes, you need more control over the instantiation process. For instance, the NotificationService has a
boolean parameter `all_caps`. We might want a configuration file that enables or disables this feature. Here's how we
can do this using _autowired_:

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

As mentioned before, _autowired_ builds on the idea of using `cached_property` to implement the singleton pattern.
That's
why `cached_property` is a first-class citizen in _autowired_, and you can use it if you want to have more control over
the instantiation process. When _autowired_ resolves
dependencies, it respects not only other `autowired` fields but also `cached_property` and classic `property` methods.

The `Context` class provides a convenience method `self.autowire()` that you can use to resolve dependencies
within `cached_property` and `property` methods.
Explicit dependencies can be passed as kwargs, as shown in the example above, and the remaining ones will be resolved
automatically as before.

## Using kwargs factory for autowired fields

The previous example is equivalent to the following:

```python
class ApplicationContext(Context):
    notification_controller: NotificationController = autowired()
    _notification_service: NotificationService = autowired(
        lambda self: dict(all_caps=self.settings.all_caps_notifications)
    )

    def __init__(self, settings: ApplicationSettings = ApplicationSettings()):
        self.settings = settings
```

Here we pass a kwargs factory function to `autowired` as the first argument. The factory function is called with the
context instance as its only argument when the component is instantiated. This allows us to access the settings
via `self.settings`.

Which of the two approaches you prefer is a matter of taste or the complexity of evaluating the settings. For simple
settings, the kwargs factory function is probably the most convenient way. For more complex rules, the `cached_property`
approach might be more suitable. Both approaches can be mixed freely.

## Recap - The Building Blocks

Now, you already know the most important building blocks of _autowired_.

- `Context` serves as the base class for all classes that manage dependencies between components.
- `autowired` defines autowired fields.
- `cached_property` and `property` offer more control over the instantiation process.
- `self.autowire()` is a helper method for implementing `cached_property` and `property` methods on context classes.

## Eager and Lazy Instantiation

`autowired()` fields behave like `cached_property`s and are instantiated lazily, i.e., the first time they are accessed.
If this is not the desired behavior, you can use the `eager` parameter to force eager instantiation of the component.

```python
class ApplicationContext(Context):
    notification_controller: NotificationController = autowired(eager=True)
```

## Transient Components

There may be situations where you need to create a new instance of a component each time it's injected or accessed from the context. 
This is also known as a component with transient lifetime. 
You can accomplish this by setting the `transient` parameter to `True` when defining an `autowired` field.

```python
class ApplicationContext(Context):
    notification_controller: NotificationController = autowired(transient=True)


ctx = ApplicationContext()

# A new instance is created each time the notification controller is accessed
assert id(ctx.notification_controller) != id(ctx.notification_controller)
```

For property methods, simply use the `property` decorator instead of `cached_property` to achieve the same effect.

## Scopes and Derived Contexts

Often a single context is not sufficient to manage all the dependencies of an application. Instead, many applications
will have multiple contexts, often sharing some components. A classic example is a request context, derived from an
application context.

```python
from dataclasses import dataclass
from autowired import Context, autowired, provided


# application scoped components

@dataclass
class AuthService:
    allowed_tokens: list[str]

    def check_token(self, token: str) -> bool:
        return token in self.allowed_tokens


# request scoped components

@dataclass
class Request:
    token: str


@dataclass
class RequestService:
    auth_service: AuthService
    request: Request

    def is_authorised(self):
        return self.auth_service.check_token(self.request.token)


# application scoped context

@dataclass
class ApplicationSettings:
    allowed_tokens: list[str]


class ApplicationContext(Context):
    auth_service: AuthService = autowired(
        lambda self: dict(allowed_tokens=self.settings.allowed_tokens)
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


# usage

settings = ApplicationSettings(allowed_tokens=["123", "456"])
application_ctx = ApplicationContext(settings)

demo_request = Request(token="123")
request_ctx = RequestContext(application_ctx, demo_request)

# Both contexts should have the same AuthService instance
assert id(application_ctx.auth_service) == id(request_ctx.request_service.auth_service)

if request_ctx.request_service.is_authorised():
    print("Authorised")
else:
    print("Not authorised")

```

## Advanced Example - FastAPI Application

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

