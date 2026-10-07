from starlette.responses import JSONResponse

from terraforma.json_input import strict_json


class RequestSizeLimitMiddleware:
    def __init__(self, app, max_bytes: int = 64 * 1024, path_limits: dict[str, int] | None = None):
        self.app = app
        self.max_bytes = max_bytes
        self.path_limits = path_limits or {}

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] in {"GET", "HEAD"}:
            await self.app(scope, receive, send)
            return
        messages = []
        size = 0
        limit = self.path_limits.get(scope["path"], self.max_bytes)
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            size += len(message.get("body", b""))
            if size > limit:
                response = JSONResponse(
                    {"detail": f"Request exceeds the {limit // 1024} KiB local API limit."},
                    status_code=413,
                )
                await response(scope, receive, send)
                return
            messages.append(message)
            if not message.get("more_body", False):
                break
        content_type = (
            next(
                (
                    value.decode("latin-1")
                    for name, value in scope["headers"]
                    if name == b"content-type"
                ),
                "",
            )
            .split(";", 1)[0]
            .strip()
            .lower()
        )
        if (
            not content_type
            or content_type == "application/json"
            or (content_type.startswith("application/") and content_type.endswith("+json"))
        ):
            try:
                strict_json(
                    b"".join(message.get("body", b"") for message in messages), allow_bom=False
                )
            except (ValueError, TypeError, RecursionError):
                response = JSONResponse(
                    {
                        "detail": "Request must contain unambiguous UTF-8 JSON with finite numbers, unique object keys and at most 64 nesting levels. Input values are omitted."
                    },
                    status_code=422,
                )
                await response(scope, receive, send)
                return
        iterator = iter(messages)

        async def bounded_receive():
            try:
                return next(iterator)
            except StopIteration:
                return await receive()

        await self.app(scope, bounded_receive, send)
