# ADR-003: Flask over FastAPI for the API layer

**Status:** Accepted

## Context

The platform needs an HTTP API for authenticated users to query events, fetch patient summaries, and trigger admin operations. Two obvious candidates in the modern Python ecosystem: **Flask** (the long-standing default) and **FastAPI** (the newer async-first framework).

## Decision

Use **Flask** with **Flask-RESTful** for resource routing, **flask-pydantic** for request validation, and **gunicorn** as the WSGI server.

## Alternatives considered

**FastAPI**

- Async-first, OpenAPI generation built in, Pydantic-native validation
- Excellent for high-concurrency I/O-bound APIs
- Smaller talent pool in regulated industries - large biotech and pharma estates are still heavily Flask
- Async would require either rewriting the boto3 calls with `aioboto3` or running them in a thread pool, neither of which buys us much for our access patterns

**Django REST Framework**

- Comes with an ORM, admin interface, and authentication system
- Designed for monolithic web apps - overkill for a focused JSON API
- The platform deliberately uses DynamoDB for the hot path, which the Django ORM doesn't speak natively

**Bare Flask**

- Possible but means hand-rolling resource routing, request validation, and serialisation
- Flask-RESTful is a thin enough layer that the conventions help without locking us in

## Consequences

**Positive**

- Synchronous code path is simpler to reason about, especially when downstream calls are short
- Vast pool of operational knowledge in the Python community - every gotcha has a Stack Overflow thread
- Pydantic validation at the boundary gives us the same contract-enforcement benefit as FastAPI without the framework lock-in

**Negative**

- We give up automatic OpenAPI generation - we either write the spec by hand or add `flasgger`/`apispec`
- Concurrency under load relies on gunicorn worker count, not native async - needs benchmarking before any high-RPS workload
- If the API later needs WebSocket or streaming endpoints, we will revisit

## Future revisit triggers

This decision is worth re-examining if any of these become true:

- Per-request latency is dominated by waiting for multiple I/O calls (async wins)
- The team is staffing up with engineers who have only worked in async Python
- A websocket or server-sent-events endpoint becomes a hard requirement
