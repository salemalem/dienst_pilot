"""Interfaces for external dependencies (solver, ML models, LLM provider, push, calendar).

Domain code depends on these protocols, never on a vendor SDK. Ports are added as the
components that need them are built.
"""
