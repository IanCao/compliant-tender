"""Offline tests for CompliantTender - the model filters, the contract chooses.

The invariant under test is not "does the AI pick a good bid". It is narrower and
checkable: whatever the reviewers say, the contract pays the cheapest bid they
marked compliant, and nothing else. Most of the cases below are attempts to break
that sentence.
"""

from __future__ import annotations

import json

import pytest

from helpers import ALICE, BOB, CAROL, CLIENT, GEN, STRANGER, deploy_tender, transfers

REQUIREMENTS = (
    "A landing page for the Adjudicate project: one hero section, a working "
    "contact form, and delivery within 3 days. Must include the source repo."
)
REVIEWER = "You are the compliance reviewer of an on-chain tender"

BUDGET = GEN // 10          # 0.1 GEN
CHEAP = GEN // 50           # 0.02
MID = GEN // 40             # 0.025
RICH = GEN // 20            # 0.05
WINDOW = 600


def _verdicts(*flags, reasons=None):
    payload = []
    for index, flag in enumerate(flags):
        reason = (reasons or [])[index] if reasons else ("meets the requirements" if flag else "missing the contact form")
        payload.append({"index": index, "compliant": flag, "reason": reason})
    return json.dumps(payload)


def _mock(mod, body="A landing page with hero, form and repo. Delivery in 3 days."):
    mod.gl.nondet.web.mock(r"example\.com/", body)


def _open(mod, contract, budget=BUDGET, window=WINDOW):
    mod.gl.set_context(sender=CLIENT, value=budget)
    return contract.open_tender(REQUIREMENTS, mod.u256(window))


def _bid(mod, contract, tender_id, bidder, price, url="https://example.com/p"):
    mod.gl.set_context(sender=bidder)
    return contract.submit_bid(tender_id, mod.u256(price), url)


def _travel(mod, seconds):
    base = mod._now_ts()
    mod._now_ts = lambda: base + seconds


def _award(mod, contract, tender_id, verdicts):
    mod.gl.llm.clear()
    mod.gl.llm.mock(REVIEWER, verdicts)
    mod.gl.set_context(sender=STRANGER)
    return contract.award(tender_id)


# --- opening a tender --------------------------------------------------------


def test_tender_stores_the_budget_and_the_terms():
    mod, contract = deploy_tender()
    tender_id = _open(mod, contract)
    tender = contract.get_tender(tender_id)
    assert str(tender.client) == CLIENT
    assert tender.requirements == REQUIREMENTS.strip()
    assert int(tender.budget) == BUDGET
    assert tender.status == "OPEN"
    assert contract.is_bidding_open(tender_id) is True


def test_budget_below_the_minimum_is_rejected():
    mod, contract = deploy_tender()
    mod.gl.set_context(sender=CLIENT, value=1)
    with pytest.raises(mod.gl.vm.UserError, match="below the minimum"):
        contract.open_tender(REQUIREMENTS, mod.u256(WINDOW))


def test_requirements_must_be_written_down():
    mod, contract = deploy_tender()
    mod.gl.set_context(sender=CLIENT, value=BUDGET)
    with pytest.raises(mod.gl.vm.UserError, match="at least"):
        contract.open_tender("make a site", mod.u256(WINDOW))


def test_window_bounds_are_enforced():
    mod, contract = deploy_tender()
    mod.gl.set_context(sender=CLIENT, value=BUDGET)
    with pytest.raises(mod.gl.vm.UserError, match="below the minimum"):
        contract.open_tender(REQUIREMENTS, mod.u256(1))
    with pytest.raises(mod.gl.vm.UserError, match="above the maximum"):
        contract.open_tender(REQUIREMENTS, mod.u256(31 * 24 * 3600))


# --- bidding -----------------------------------------------------------------


def test_bid_is_linked_to_the_tender():
    mod, contract = deploy_tender()
    tender_id = _open(mod, contract)
    bid_id = _bid(mod, contract, tender_id, ALICE, CHEAP)

    assert int(contract.bid_count(tender_id)) == 1
    bid = contract.get_bid(bid_id)
    assert str(bid.bidder) == ALICE
    assert int(bid.price) == CHEAP
    assert bid.compliant is False
    assert bid.reason == "not reviewed yet"


def test_bid_after_the_window_is_rejected():
    mod, contract = deploy_tender()
    tender_id = _open(mod, contract, window=120)
    _travel(mod, 121)
    with pytest.raises(mod.gl.vm.UserError, match="bidding window closed"):
        _bid(mod, contract, tender_id, ALICE, CHEAP)


def test_bid_above_the_client_budget_is_rejected():
    mod, contract = deploy_tender()
    tender_id = _open(mod, contract)
    with pytest.raises(mod.gl.vm.UserError, match="exceeds the client budget"):
        _bid(mod, contract, tender_id, ALICE, BUDGET + 1)


def test_zero_price_is_rejected():
    mod, contract = deploy_tender()
    tender_id = _open(mod, contract)
    with pytest.raises(mod.gl.vm.UserError, match="price must be > 0"):
        _bid(mod, contract, tender_id, ALICE, 0)


def test_bid_count_is_capped():
    mod, contract = deploy_tender()
    tender_id = _open(mod, contract)
    for _ in range(8):
        _bid(mod, contract, tender_id, ALICE, CHEAP)
    with pytest.raises(mod.gl.vm.UserError, match="maximum of 8 bids"):
        _bid(mod, contract, tender_id, BOB, CHEAP)


# --- awarding ----------------------------------------------------------------


def test_award_before_the_window_closes_is_rejected():
    mod, contract = deploy_tender()
    tender_id = _open(mod, contract)
    _bid(mod, contract, tender_id, ALICE, CHEAP)
    with pytest.raises(mod.gl.vm.UserError, match="still open"):
        _award(mod, contract, tender_id, _verdicts(True))


def test_award_with_no_bids_refunds_the_client():
    mod, contract = deploy_tender()
    tender_id = _open(mod, contract)
    _travel(mod, WINDOW)

    assert _award(mod, contract, tender_id, _verdicts()) == ""
    assert contract.get_tender(tender_id).status == "NO_AWARD"
    assert transfers(mod) == [(CLIENT, BUDGET)]


def test_cheapest_compliant_bid_wins_even_when_it_is_not_the_cheapest_bid():
    mod, contract = deploy_tender()
    tender_id = _open(mod, contract)
    _bid(mod, contract, tender_id, ALICE, CHEAP)     # 0.02, non-compliant
    _bid(mod, contract, tender_id, BOB, MID)         # 0.025, compliant
    _bid(mod, contract, tender_id, CAROL, RICH)      # 0.05, compliant
    _travel(mod, WINDOW)

    winner = _award(mod, contract, tender_id, _verdicts(False, True, True))

    tender = contract.get_tender(tender_id)
    assert winner == "1"
    assert str(tender.winner) == BOB
    assert int(tender.paid) == MID
    assert tender.status == "AWARDED"


def test_the_cheapest_compliant_bid_wins_over_a_more_expensive_one():
    mod, contract = deploy_tender()
    tender_id = _open(mod, contract)
    _bid(mod, contract, tender_id, ALICE, CHEAP)
    _bid(mod, contract, tender_id, BOB, RICH)
    _travel(mod, WINDOW)

    winner = _award(mod, contract, tender_id, _verdicts(True, True))

    assert winner == "0"
    assert str(contract.get_tender(tender_id).winner) == ALICE


def test_the_client_gets_the_unspent_budget_back():
    mod, contract = deploy_tender()
    tender_id = _open(mod, contract)
    _bid(mod, contract, tender_id, ALICE, CHEAP)
    _travel(mod, WINDOW)

    _award(mod, contract, tender_id, _verdicts(True))

    assert transfers(mod) == [(ALICE, CHEAP), (CLIENT, BUDGET - CHEAP)]


def test_a_tie_goes_to_the_earlier_bid():
    mod, contract = deploy_tender()
    tender_id = _open(mod, contract)
    _bid(mod, contract, tender_id, BOB, CHEAP)
    _bid(mod, contract, tender_id, ALICE, CHEAP)
    _travel(mod, WINDOW)

    _award(mod, contract, tender_id, _verdicts(True, True))

    assert str(contract.get_tender(tender_id).winner) == BOB


def test_no_compliant_bid_returns_the_whole_budget():
    mod, contract = deploy_tender()
    tender_id = _open(mod, contract)
    _bid(mod, contract, tender_id, ALICE, CHEAP)
    _bid(mod, contract, tender_id, BOB, MID)
    _travel(mod, WINDOW)

    assert _award(mod, contract, tender_id, _verdicts(False, False)) == ""
    tender = contract.get_tender(tender_id)
    assert tender.status == "NO_AWARD"
    assert str(tender.winner) == "0x" + "0" * 40
    assert transfers(mod) == [(CLIENT, BUDGET)]


def test_rejections_are_recorded_with_their_reason():
    mod, contract = deploy_tender()
    tender_id = _open(mod, contract)
    bid_id = _bid(mod, contract, tender_id, ALICE, CHEAP)
    _travel(mod, WINDOW)

    _award(mod, contract, tender_id, _verdicts(False, reasons=["no contact form in the page"]))

    bid = contract.get_bid(bid_id)
    assert bid.compliant is False
    assert "contact form" in bid.reason


def test_award_twice_is_refused():
    mod, contract = deploy_tender()
    tender_id = _open(mod, contract)
    _bid(mod, contract, tender_id, ALICE, CHEAP)
    _travel(mod, WINDOW)
    _award(mod, contract, tender_id, _verdicts(True))
    with pytest.raises(mod.gl.vm.UserError, match="awarded"):
        _award(mod, contract, tender_id, _verdicts(True))


# --- failure modes that must not move money ----------------------------------


def test_a_short_verdict_list_reverts_and_pays_nobody():
    mod, contract = deploy_tender()
    tender_id = _open(mod, contract)
    _bid(mod, contract, tender_id, ALICE, CHEAP)
    _bid(mod, contract, tender_id, BOB, MID)
    _travel(mod, WINDOW)

    with pytest.raises(Exception):
        _award(mod, contract, tender_id, _verdicts(True))  # one verdict, two bids

    assert transfers(mod) == []
    assert contract.get_tender(tender_id).status == "OPEN"


def test_disagreement_on_the_vector_reverts():
    mod, contract = deploy_tender()
    tender_id = _open(mod, contract)
    _bid(mod, contract, tender_id, ALICE, CHEAP)
    _bid(mod, contract, tender_id, BOB, MID)
    _travel(mod, WINDOW)

    mod.gl.llm.clear()
    mod.gl.llm.queue(REVIEWER, [_verdicts(True, False), _verdicts(False, True)])
    mod.gl.set_context(sender=STRANGER)
    with pytest.raises(mod.gl.vm.UserError, match="no consensus"):
        contract.award(tender_id)

    assert transfers(mod) == []


def test_agreeing_on_the_vector_survives_different_reasons():
    """The reason text is not compared - only the compliance vector is."""
    mod, contract = deploy_tender()
    tender_id = _open(mod, contract)
    _bid(mod, contract, tender_id, ALICE, CHEAP)
    _travel(mod, WINDOW)

    leader = _verdicts(True, reasons=["meets every requirement"])
    validator = _verdicts(True, reasons=["hero, form, repo, 3 days - all present"])
    mod.gl.llm.clear()
    mod.gl.llm.queue(REVIEWER, [leader, validator])
    mod.gl.set_context(sender=STRANGER)
    contract.award(tender_id)

    assert str(contract.get_tender(tender_id).winner) == ALICE


def test_prose_instead_of_json_reverts():
    mod, contract = deploy_tender()
    tender_id = _open(mod, contract)
    _bid(mod, contract, tender_id, ALICE, CHEAP)
    _travel(mod, WINDOW)

    mod.gl.llm.clear()
    mod.gl.llm.mock(REVIEWER, "looks good to me")
    mod.gl.set_context(sender=STRANGER)
    with pytest.raises(Exception):
        contract.award(tender_id)
    assert transfers(mod) == []


# --- cancel ------------------------------------------------------------------


def test_cancel_refunds_the_client_when_there_are_no_bids():
    mod, contract = deploy_tender()
    tender_id = _open(mod, contract)
    mod.gl.set_context(sender=CLIENT)
    contract.cancel(tender_id)
    assert transfers(mod) == [(CLIENT, BUDGET)]
    assert contract.get_tender(tender_id).status == "CANCELLED"


def test_cancel_is_refused_once_a_bid_exists():
    mod, contract = deploy_tender()
    tender_id = _open(mod, contract)
    _bid(mod, contract, tender_id, ALICE, CHEAP)
    mod.gl.set_context(sender=CLIENT)
    with pytest.raises(mod.gl.vm.UserError, match="once bids exist"):
        contract.cancel(tender_id)


def test_only_the_client_may_cancel():
    mod, contract = deploy_tender()
    tender_id = _open(mod, contract)
    mod.gl.set_context(sender=STRANGER)
    with pytest.raises(mod.gl.vm.UserError, match="only the client"):
        contract.cancel(tender_id)


# --- the prompt --------------------------------------------------------------


def test_prompt_lists_every_bid_with_its_price_and_separates_the_roles():
    mod, contract = deploy_tender()
    tender_id = _open(mod, contract)
    _bid(mod, contract, tender_id, ALICE, CHEAP, url="https://example.com/alice")
    _bid(mod, contract, tender_id, BOB, MID, url="https://example.com/bob")
    _travel(mod, WINDOW)
    _award(mod, contract, tender_id, _verdicts(True, True))

    prompt = mod.gl.llm.calls[-1]
    assert "<<<REQUIREMENTS>>>" in prompt and REQUIREMENTS[:40] in prompt
    assert "BID 0 price=" + str(CHEAP) in prompt
    assert "BID 1 price=" + str(MID) in prompt
    assert "example.com/alice" in prompt and "example.com/bob" in prompt
    assert "You do not choose a winner" in prompt
