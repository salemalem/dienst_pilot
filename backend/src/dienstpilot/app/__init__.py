"""Application layer: the HTTP API for the screens.

It composes the bounded contexts through their public ``service`` modules only (never their
models), applies roles, department scope and privacy rules, and records audit events.
"""
