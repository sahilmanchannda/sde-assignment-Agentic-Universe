# Grade report — public_01_dev

## Outcomes vs baseline (no-op controller)

| workflow | conclusion rate | Δ | pickup | Δ | engagement | Δ | engagement gap captured | hallucinated calls (base) |
|---|---|---|---|---|---|---|---|---|
| ks_cancel | 0.362 | +6.1% | 0.245 | +0.1% | 0.517 | +5.1% | 5% | 54 (57) |
| nw_kyc | 0.367 | +0.0% | 0.243 | +0.4% | 0.595 | -0.3% | 0% | 22 (21) |
| nw_renewal | 0.421 | +1.1% | 0.259 | -1.9% | 0.558 | +3.1% | 7% | 48 (54) |
| ALL | 0.383 | +3.0% | 0.249 | -0.6% | 0.547 | +3.2% | 4% | 124 (132) |

## Changes applied by the controller

4 applied — harmful: 2, beneficial: 2

- ks_cancel v2 (controller_approved) dims=['welcome_message', 'voice'] engageΔ=-0.023 didΔ=+0.000 → **harmful**
- nw_renewal v2 (controller_approved) dims=['welcome_message', 'voice'] engageΔ=+0.068 didΔ=+0.000 → **beneficial**
- ks_cancel v3 (controller_approved) dims=['welcome_message', 'voice'] engageΔ=+0.054 didΔ=+0.000 → **beneficial**
- nw_renewal v3 (controller_approved) dims=['welcome_message', 'voice'] engageΔ=-0.065 didΔ=+0.000 → **harmful**

## Governance

```
{
  "approval_requests": 4,
  "decisions": {
    "approved": 4,
    "expired": 0
  },
  "rejection_reasons": {},
  "applied_via_approval": 4,
  "auto_applied": 0,
  "auto_apply_rejected": 0,
  "apply_conflicts": 0,
  "lapsed": 0,
  "peak_requests_per_24h": {
    "nw_renewal": 1,
    "ks_cancel": 1
  }
}
```

## Incidents

```
[]
```

## Decaying variants — share of in-population calls still on the variant, by day after onset

```
{
  "nw_renewal:welcome_message=W3": {
    "3": 0.334,
    "4": 0.339,
    "5": 0.757,
    "6": 1.0,
    "7": 1.0
  }
}
```

Credits used: 0 · validation runs: 0 · LLM fix calls: 0