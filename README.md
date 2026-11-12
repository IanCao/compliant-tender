# CompliantTender

A tender where the model decides *compliance* and the contract decides *the
winner*.

```
open_tender(requirements, window)      client locks a budget, publishes the terms
submit_bid(tender_id, price, url)      anyone, inside the window
award(tender_id)                       reviewers mark each bid compliant
                                       contract pays the cheapest compliant one
cancel(tender_id)                      client, only before any bid exists
```

## Why the model does not choose

Letting a model pick "the best bid" fails for a reason that has nothing to do
with model quality: **the choice is unverifiable**. Two reviewers can both be
reasonable and disagree, the client cannot show a losing bidder why it lost, and
the losing bidder cannot show that it should have won. "Best" is not a fact, so
no consensus rule can settle it — you end up paying for an argument.

Meeting a written requirement is closer to a fact: either the proposal describes
a three-day turnaround or it does not.

So the model is asked only that, once per bid, and the contract does the rest:

| Question | Answered by | Why |
|---|---|---|
| Does this proposal meet the written requirements? | validators | needs reading a document |
| Which compliant bid wins? | the contract | cheapest price; deterministic and replayable |
| How much is paid? | the contract | the bid's stored price |

A reviewer cannot pick a winner, change a price, or introduce a bid. Replacing it
with a coin flip would give worse answers but an equally well-defined outcome —
and being well-defined is what makes an award auditable.

## What the contract guarantees

- **Cheapest compliant wins.** Ties go to the earlier bid: a rule the chain can
  prove, unlike "better value".
- **The client's budget is locked until `award()`.** If no bid complies, the
  whole budget returns and the tender ends `NO_AWARD` — the client cannot be
  forced to pay for a field it considers non-compliant, and nobody is paid for a
  proposal that was not accepted.
- **`award()` is permissionless.** The client cannot withhold payment by
  refusing to call it; a second call reverts.
- **Rejections carry their reason.** A bidder reads the exact ground for
  rejection from `get_bid()`.
- **Unspent budget returns automatically.** The winner gets its price; the
  remainder goes back to the client in the same transaction.

## Consensus

Every validator re-fetches every proposal and re-derives a compliance verdict.
What is compared is the compliance *vector* — the string `"101"` for three bids —
not the reasoning text. Two reviewers that agree a proposal fails, but cite
different missing requirements, are in agreement about the thing the award
depends on.

A verdict list of the wrong length, a non-array response, or prose instead of
JSON all revert the whole transaction: no payment, tender still `OPEN`.

## Prompt-injection handling

Proposals are fetched from the open web and fenced as data:

```
<<<REQUIREMENTS>>>   the client's written terms
<<<BID 0 price=... url=...>>>   one untrusted proposal
```

A proposal that asks to be marked compliant, to ignore the rules, or to reveal
the prompt is non-compliant on that ground alone. Silence about a requirement is
not compliance, and an unreachable document is not compliance — the fallbacks all
point away from paying.

## Tests

26 offline tests, no network, no Docker:

```bash
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/Scripts/python -m pytest tests -q
```

They cover the constructor bounds, bidding windows and the eight-bid cap, the
cheapest-compliant rule with a cheaper non-compliant bid in the field, the
tie-break, the no-award refund, unspent-budget return, rejection reasons, a
second award, and four ways the review can fail without moving money.

## Deploy

Studio → Studionet → paste `contracts/compliant_tender.py`. No constructor
arguments.

```
open_tender(
  requirements="Landing page: hero, working contact form, source repo, "
               "delivery within 3 days.",
  window=604800            # 7 days
)  with value = 0.1 GEN
```

## Limits worth stating

- **Bids are public.** The price is on-chain the moment it is submitted, so this
  is a posted-price tender, not a cryptographic sealed-bid auction. A commit-
  reveal phase would be the next step and is deliberately out of scope.
- **Eight bids maximum**, so the whole field fits in one review prompt. A larger
  tender needs batching and a different consensus shape.
- **Compliance is judged from the proposal document alone.** A bidder who writes
  a proposal that satisfies every requirement and then delivers nothing still
  wins; pair this with a delivery escrow if the work must be verified too.
- **Non-compliance is not punished.** Nothing is slashed, so a spam bid costs
  only the transaction fee and a slot out of eight. A per-bid deposit is the
  obvious upgrade and is not implemented.
