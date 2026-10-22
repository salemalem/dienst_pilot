"""The LLM port, its adapters (live Anthropic, replay of recorded fixtures), cost and budget.

Domain code and the backend talk to ``LlmClient`` and never import the vendor SDK; only
``anthropic_client`` does. Every paid call is written to an append-only ledger and checked against
the phase budget before it is sent (ADR-020).
"""
