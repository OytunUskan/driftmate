"""Driftmate core package.

Contains vendor-agnostic models, interfaces and services. This package
must never import any provider/adapter module (providers/, channels/, build/).
Dependency direction is always inward: adapters know core, core does not know adapters.
"""
