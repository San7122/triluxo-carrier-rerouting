"""Mock 'carrier API' tools.

============================  IMPORTANT  ============================
EVERYTHING IN THIS FILE IS SIMULATED. There is no real carrier network,
no real booking system, and no external HTTP call. Each tool reads its
response from the scenario's `simulation` block so that runs are
deterministic and reproducible across models.

In production these two functions would be replaced by real integrations:
  - get_alternative_carriers -> a rate-shopping / TMS carrier API
    (e.g. project44, FourKites, or a 4PL's booking gateway)
  - execute_reroute          -> a booking/EDI transaction against the
    selected carrier, returning a real booking reference.
The *interface* (name, args, shape of the return value) is designed to
match what those real calls would look like, so swapping the mock for a
live client is a localized change.
====================================================================
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any


class ToolError(RuntimeError):
    """Raised when a (simulated) tool call fails, so the graph can retry."""


@dataclass
class SimulatedCarrierNetwork:
    """Per-scenario, in-memory stand-in for a real carrier/booking API.

    `sim` is the scenario's `simulation` block. It controls what the mock
    tools return and lets us deterministically inject failures/empty results.
    Call-counters make 'fail once then succeed' behaviour possible without
    any real randomness.
    """

    sim: dict[str, Any]
    _calls: dict[str, int] = field(default_factory=dict)

    def _bump(self, key: str) -> int:
        self._calls[key] = self._calls.get(key, 0) + 1
        return self._calls[key]

    # ---- Tool 1: list alternative carriers/routes -------------------------
    def get_alternative_carriers(self, shipment_id: str) -> dict[str, Any]:
        """SIMULATED. Return alternative carriers/routes for a shipment.

        Behaviour is driven by scenario `simulation.get_alternative_carriers.mode`:
          - "return"           : return the configured list of carriers
          - "empty"            : return an empty list (no options exist)
          - "error_then_return": raise ToolError on the 1st call, return on 2nd
          - "always_error"     : always raise ToolError
        """
        cfg = self.sim.get("get_alternative_carriers", {"mode": "return"})
        mode = cfg.get("mode", "return")
        n = self._bump("get_alternative_carriers")

        if mode == "always_error":
            raise ToolError("carrier_api_unavailable: upstream 503")
        if mode == "error_then_return" and n == 1:
            raise ToolError("carrier_api_timeout: no response within 5s")
        if mode == "empty":
            return {"shipment_id": shipment_id, "carriers": []}

        return {"shipment_id": shipment_id, "carriers": cfg.get("carriers", [])}

    # ---- Tool 2: execute the reroute booking ------------------------------
    def execute_reroute(self, shipment_id: str, carrier_id: str) -> dict[str, Any]:
        """SIMULATED. Book the reroute with the chosen carrier.

        Behaviour is driven by scenario `simulation.execute_reroute.mode`:
          - "succeed"          : always confirm the booking
          - "fail_then_succeed": raise ToolError on the 1st call, confirm on 2nd
          - "always_fail"      : always raise ToolError
        The confirmed ETA is looked up from the carrier list so the return
        value is internally consistent with what evaluation saw.
        """
        cfg = self.sim.get("execute_reroute", {"mode": "succeed"})
        mode = cfg.get("mode", "succeed")
        n = self._bump("execute_reroute")

        if mode == "always_fail":
            raise ToolError("booking_gateway_rejected: carrier capacity full")
        if mode == "fail_then_succeed" and n == 1:
            raise ToolError("booking_gateway_timeout: EDI ack not received")

        carriers = self.sim.get("get_alternative_carriers", {}).get("carriers", [])
        match = next((c for c in carriers if c.get("carrier_id") == carrier_id), None)
        new_eta = match.get("eta_hours") if match else None
        booking_ref = "BK-" + "".join(random.choices("0123456789ABCDEF", k=8))
        return {
            "status": "confirmed",
            "shipment_id": shipment_id,
            "carrier_id": carrier_id,
            "new_eta_hours": new_eta,
            "booking_ref": booking_ref,
        }


# ----------------------------------------------------------------------------
# Tool schemas advertised to the LLM (provider-agnostic JSON Schema).
# The llm.py adapters translate these into Anthropic / OpenAI tool formats.
# ----------------------------------------------------------------------------
TOOL_SCHEMAS = [
    {
        "name": "get_alternative_carriers",
        "description": (
            "Look up alternative carriers/routes that can still serve a delayed "
            "shipment. Returns a list of options, each with carrier_id, name, mode, "
            "cost_usd, eta_hours (total hours to destination if switched now), and "
            "reliability (0-1). Call this before deciding on a reroute."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "shipment_id": {"type": "string", "description": "The disrupted shipment's id."}
            },
            "required": ["shipment_id"],
        },
    },
    {
        "name": "execute_reroute",
        "description": (
            "Book the reroute by committing the shipment to a chosen carrier. Only "
            "call this once, with a carrier_id returned by get_alternative_carriers, "
            "after confirming it satisfies the policy. Returns a booking confirmation."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "shipment_id": {"type": "string"},
                "carrier_id": {
                    "type": "string",
                    "description": "carrier_id of the selected option.",
                },
            },
            "required": ["shipment_id", "carrier_id"],
        },
    },
]
