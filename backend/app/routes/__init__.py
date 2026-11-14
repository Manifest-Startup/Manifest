import inspect

from starlette.routing import Router as StarletteRouter


def _patch_router_init_for_fastapi() -> None:
    parameters = inspect.signature(StarletteRouter.__init__).parameters
    if "on_startup" in parameters and "on_shutdown" in parameters:
        return

    original_init = StarletteRouter.__init__

    def _compat_init(
        self,
        routes=None,
        redirect_slashes=True,
        default=None,
        on_startup=None,
        on_shutdown=None,
        lifespan=None,
        *,
        middleware=None,
    ) -> None:
        original_init(
            self,
            routes=routes,
            redirect_slashes=redirect_slashes,
            default=default,
            lifespan=lifespan,
            middleware=middleware,
        )
        self.on_startup = [] if on_startup is None else list(on_startup)
        self.on_shutdown = [] if on_shutdown is None else list(on_shutdown)

    StarletteRouter.__init__ = _compat_init


_patch_router_init_for_fastapi()
