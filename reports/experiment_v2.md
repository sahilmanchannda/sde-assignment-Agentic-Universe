# Grade report — public_01_dev

## Outcomes vs baseline (no-op controller)

| workflow | conclusion rate | Δ | pickup | Δ | engagement | Δ | engagement gap captured | hallucinated calls (base) |
|---|---|---|---|---|---|---|---|---|
| ks_cancel | 0.358 | +4.9% | 0.244 | -0.1% | 0.513 | +4.3% | 8% | 50 (57) |
| nw_kyc | 0.353 | -3.7% | 0.237 | -2.0% | 0.590 | -1.3% | 0% | 18 (21) |
| nw_renewal | 0.412 | -1.1% | 0.258 | -2.2% | 0.549 | +1.3% | 10% | 38 (54) |
| ALL | 0.375 | +0.8% | 0.248 | -1.2% | 0.540 | +2.0% | 7% | 106 (132) |

## Changes applied by the controller

4 applied — harmful: 1, beneficial: 3

- ks_cancel v2 (controller_approved) dims=['welcome_message', 'voice'] engageΔ=-0.023 didΔ=+0.000 → **harmful**
- nw_renewal v2 (controller_approved) dims=['welcome_message', 'voice'] engageΔ=+0.068 didΔ=+0.000 → **beneficial**
- ks_cancel v3 (controller_approved) dims=['welcome_message', 'voice'] engageΔ=+0.052 didΔ=+0.000 → **beneficial**
- nw_renewal v3 (controller_approved) dims=['welcome_message', 'voice'] engageΔ=+0.061 didΔ=+0.000 → **beneficial**

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
    "3": 0.91,
    "4": 0.894,
    "5": 0.896,
    "6": 0.899,
    "7": 0.896
  }
}
```

Credits used: 0 · validation runs: 0 · LLM fix calls: 0