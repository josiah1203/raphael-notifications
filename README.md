# raphael-notifications

In-app inbox, preferences, email/push routing via external providers

## API

- Prefix: `/v1/notifications`
- Port: `8090`
- Health: `GET /health`

## Events

_Published and consumed events documented in `openapi.yaml` and raphael-contracts._

## Development

```bash
uv sync
uv run uvicorn raphael_notifications.app:app --reload --port 8090
```

Part of the [Raphael Platform](https://github.com/hummingbird-labs) by HummingBird Labs.
