"""The four durable workflows and what drives them (ADR-017).

The engine itself (instances, timers, firing) lives in ``dienstpilot.shared.workflows``. This
package holds what needs several contexts at once: the timer handlers, the consumers of domain
events, and the arming of recurring timers.
"""
