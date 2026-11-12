"""Helpers that load a contract file against the offline GenVM shim."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHIM_DIR = ROOT / "tools" / "genshim"

CLIENT = "0x" + "a1" * 20
ALICE = "0x" + "c3" * 20       # bidder, cheapest
BOB = "0x" + "d4" * 20         # bidder, mid
CAROL = "0x" + "e5" * 20       # bidder, most expensive
STRANGER = "0x" + "f6" * 20

GEN = 10 ** 18

_load_counter = 0


def load_contract(relative_path: str):
    """Import a contract file with `genlayer` resolving to the local shim.

    Each call gets a fresh shim instance, so mocks, message context and the
    transfer log never leak between tests.
    """
    global _load_counter
    _load_counter += 1
    module_name = f"contract_under_test_{_load_counter}"

    sys.path.insert(0, str(SHIM_DIR))
    try:
        spec = importlib.util.spec_from_file_location(module_name, ROOT / relative_path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(SHIM_DIR))
        sys.modules.pop("genlayer", None)


def deploy_tender():
    module = load_contract("contracts/compliant_tender.py")
    return module, module.CompliantTender()


def transfers(module) -> list[tuple[str, int]]:
    """Every emit_transfer the contract made, in order, as (address, value)."""
    return list(module.gl.evm.sent_log)
