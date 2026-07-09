"""Autonomous carrier-rerouting agent package.

A LangGraph multi-agent workflow that ingests a logistics telemetry alert,
evaluates alternative carriers via a (SIMULATED) carrier API, and autonomously
executes a reroute against an explicit policy -- with a retry + human-escalation
fallback path. Every run emits a structured trajectory log for evaluation.
"""
