# autowired

_autowired_ is a lightweight dependency injection library for Python, which utilizes type hints to resolve
dependencies.     
It promotes a simple context-based singleton pattern to manage dependencies between components and
provides some tools to make the implementation of this pattern more convenient.

## Installation

```bash
pip install autowired
```

## Basic Example

```python
from autowired import Context, autowired, cached_property
from dataclasses import dataclass


# Defining some classes (e.g. services, controllers, repositories, etc.)
# We will refer to this type of classes as "components" throughout this documentation

class UserService:
    pass


class AuthService:
    pass


# Defining a component with dependencies
class UserAuthService:
    def __init__(self, user_service: UserService, auth_service: AuthService):
        self.user_service = user_service
        self.auth_service = auth_service

    def __repr__(self):
        return f"UserAuthService(user_service={self.user_service}, auth_service={self.auth_service})"


# dataclasses are supported as well
@dataclass
class LoginController:
    user_auth_service: UserAuthService

    def login(self, username: str):
        print(f"Logging in user {username} via {self.user_auth_service}")


# Creating a context class to manage the components.
# The context class is a regular class, which inherits from Context
class ApplicationContext(Context):
    login_controller: LoginController = autowired()


if __name__ == "__main__":
    ctx = ApplicationContext()
    ctx.login_controller.login("admin")

```

A context's `autowired` fields and their dependencies are resolved automatically on first access.

Note that all the components (services, controllers, etc.) are neither aware of the context nor the
existence of the _autowired_ library. They are regular classes, and don't care about how they are instantiated.
That is a fundamental design principle of _autowired_.
Wiring things together is the sole responsibility of the context and its dependency container.

In the above example, the complete control of creating the actual component instances is delegated to the library.
However, you can also instantiate components by hand, using a `cached_property` method on the context class.

The `cached_property` decorator is a first-class citizen in _autowired_.
The decorated methods will be registered in the context's dependency container, just like fields defined
with `autowired()`.
You can make use of this if you need more control over the instantiation of a component.

In the following example, we use a `cached_property` to explicitly instantiate the `UserService` as
a `CustomUserService`.

```python
# ... same components as in the previous example

class CustomUserService(UserService):
    pass


class ApplicationContext(Context):
    login_controller: LoginController = autowired()

    @cached_property
    def user_service(self) -> UserService:
        return CustomUserService()


if __name__ == '__main__':
    ctx = ApplicationContext()

    # The user_auth_service should use the custom user_service now
    assert isinstance(ctx.login_controller.user_auth_service.user_service, CustomUserService)

    # The instance should be the same throughout the context
    assert id(ctx.user_service) == id(ctx.login_controller.user_auth_service.user_service)
```

## Example with Settings

In most cases, you will want to be able to make the behavior of your application configurable via settings.
As noted above, the context is responsible for wiring things together.
This makes it the perfect place to evaluate the settings and to pass them to the components as required.
_autowired_ provides some tools to make this straightforward.

```python
from autowired import Context, autowired, cached_property
from dataclasses import dataclass


class UserService:
    pass


@dataclass
class AuthService:
    secret_key: str
    user_service: UserService


@dataclass
class LoginController:
    auth_service: AuthService

    def login(self, username: str):
        print(f"Logging in user {username} via {self.auth_service}")


# Create a dataclass to represent your settings
@dataclass
class ApplicationSettings:
    auth_secret_key: str


# Create a context to manage the components
class ApplicationContext(Context):
    login_controller: LoginController = autowired()

    def __init__(self, settings: ApplicationSettings):
        self.settings = settings

    # using cached_property and self.autowire()
    @cached_property
    def auth_service(self) -> AuthService:
        # Similar to autowired(), self.autowire() resolves the dependencies of the component automatically.
        # Besides that, it allows you to pass a subset of the component's dependencies as kwargs.
        # Here we pass the secret key from our ApplicationSettings to the AuthService and
        # let the dependency container resolve the remaining dependencies (i.e. the UserService).
        return self.autowire(AuthService, secret_key=self.settings.auth_secret_key)


if __name__ == "__main__":
    # load the settings as desired (e.g. using pydantic-settings)
    # For the sake of this example, we just hardcode the settings here
    settings = ApplicationSettings(auth_secret_key="secret")
    ctx = ApplicationContext(settings=settings)
    ctx.login_controller.login("admin")
```

The following `ApplicationContext` is equivalent to the previous example.

```python
class ApplicationContext(Context):
    login_controller: LoginController = autowired()

    # Here we pass a kwargs factory function to autowired.
    # The factory function will be called with the context instance as its only argument.
    # This allows us to access the settings via self.settings
    auth_service: AuthService = autowired(
        lambda self: dict(secret_key=self.settings.auth_secret_key)
    )

    def __init__(self, settings: ApplicationSettings):
        self.settings = settings
```

Which of the two approaches you prefer is a matter of taste or the complexity of evaluating the settings.
For simple settings, the _kwargs factory_ function is probably the most convenient way.
For more complex rules, the _cached\_property_ approach might be more suitable.
Both approaches can be mixed freely.

## Scopes / Derived Contexts

Often a single context is not enough to manage all the dependencies of an application.
Instead, many applications will have multiple contexts, that are derived from each other.
A classic example is a request context, that is derived from the application context.

```python

# ... same application context and components as in the previous example

@dataclass
class RequestService:
    auth_service: AuthService


class RequestContext(Context):
    request_service: RequestService = autowired()

    def __init__(self, parent_context: Context):
        # setting the parent context makes the parent context's components available
        self.parent_context = parent_context


if __name__ == "__main__":
    root_ctx = ApplicationContext(ApplicationSettings(auth_secret_key="secret"))
    request_ctx = RequestContext(root_ctx)

    # Both contexts should have the same AuthService instance
    assert id(root_ctx.auth_service) == id(request_ctx.request_service.auth_service)

```

## Advanced Example - FastAPI Application

```python
from dataclasses import dataclass
from autowired import Context, autowired, cached_property


# Components


class DatabaseService:
    def __init__(self, conn_str: str):
        self.conn_str = conn_str

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

    def __init__(self, settings: ApplicationSettings = ApplicationSettings()):
        self.settings = settings

    @cached_property
    def database_service(self) -> DatabaseService:
        return DatabaseService(conn_str=self.settings.database_connection_string)


from fastapi import FastAPI, Request, Depends, HTTPException


# Request Scoped Service for the FastAPI Application


class RequestAuthService:
    def __init__(self, db_service: DatabaseService, request: Request):
        self.db_service = db_service
        self.request = request

    def is_authorised(self):
        token = self.request.headers.get("Authorization") or ""
        token = token.replace("Bearer ", "")
        if token in self.db_service.load_allowed_tokens():
            return True
        return False


# Request Context


class RequestContext(Context):
    request_auth_service: RequestAuthService = autowired()

    def __init__(self, parent_context: Context):
        self.parent_context = parent_context


# Setting up the FastAPI Application

app = FastAPI()
application_context = ApplicationContext()


def request_context(r: Request):
    # We manually register the Request object for the request context
    # so that it can be injected into dependent services (e.g. RequestAuthService)
    request_context = RequestContext(parent_context=application_context)
    request_context.container.register(r)
    return request_context


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

