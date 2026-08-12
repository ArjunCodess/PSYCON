"""PSYCON Week 4 backend service."""


def create_app(*args, **kwargs):
    """Import the infrastructure dependencies only when the server is created."""

    from .app import create_app as application_factory

    return application_factory(*args, **kwargs)


__all__ = ["create_app"]
