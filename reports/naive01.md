# Grade report — public_01_dev

## Outcomes vs baseline (no-op controller)

| workflow | conclusion rate | Δ | pickup | Δ | engagement | Δ | engagement gap captured | hallucinated calls (base) |
|---|---|---|---|---|---|---|---|---|
| ks_cancel | 0.339 | -0.6% | 0.244 | -0.4% | 0.491 | -0.2% | 0% | 57 (57) |
| nw_kyc | 0.391 | +6.7% | 0.246 | +1.8% | 0.621 | +4.0% | 15% | 23 (21) |
| nw_renewal | 0.418 | +0.4% | 0.264 | -0.0% | 0.544 | +0.4% | 0% | 56 (54) |
| ALL | 0.377 | +1.3% | 0.251 | +0.2% | 0.535 | +1.0% | 3% | 136 (132) |

## Changes applied by the controller

4 applied — neutral: 2, beneficial: 2

- nw_renewal v2 (controller_approved) dims=['voice'] engageΔ=+0.002 didΔ=+0.000 → **neutral**
- nw_kyc v2 (controller_approved) dims=['voice'] engageΔ=+0.035 didΔ=+0.000 → **beneficial**
- nw_renewal v3 (controller_approved) dims=['voice'] engageΔ=-0.001 didΔ=+0.000 → **neutral**
- nw_kyc v3 (controller_approved) dims=['voice'] engageΔ=+0.033 didΔ=+0.000 → **beneficial**

## Governance

```
{
  "approval_requests": 14,
  "decisions": {
    "rejected": 2,
    "approved": 4,
    "expired": 7
  },
  "rejection_reasons": {
    "approver declined (judgement call)": 2
  },
  "applied_via_approval": 4,
  "auto_applied": 0,
  "auto_apply_rejected": 0,
  "apply_conflicts": 0,
  "lapsed": 0,
  "peak_requests_per_24h": {
    "nw_renewal": 1,
    "nw_kyc": 1,
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
{}
```

Credits used: 0 · validation runs: 0 · LLM fix calls: 0