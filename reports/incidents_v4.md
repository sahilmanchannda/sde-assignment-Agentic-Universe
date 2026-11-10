# Grade report — public_02_incidents

## Outcomes vs baseline (no-op controller)

| workflow | conclusion rate | Δ | pickup | Δ | engagement | Δ | engagement gap captured | hallucinated calls (base) |
|---|---|---|---|---|---|---|---|---|
| ks_cancel | 0.261 | +10.7% | 0.182 | +0.5% | 0.513 | +9.7% | 35% | 64 (348) |
| nw_kyc | 0.375 | +0.2% | 0.238 | +1.6% | 0.603 | -0.9% | 0% | 29 (29) |
| nw_renewal | 0.436 | +0.7% | 0.264 | +0.8% | 0.557 | +0.4% | 13% | 61 (54) |
| ALL | 0.343 | +3.8% | 0.221 | +0.8% | 0.550 | +3.2% | 23% | 154 (431) |

## Changes applied by the controller

5 applied — beneficial: 3, neutral: 1, harmful: 1

- ks_cancel v2 (controller_approved) dims=['welcome_message', 'voice'] engageΔ=+0.025 didΔ=+0.000 → **beneficial**
- nw_renewal v2 (controller_approved) dims=['welcome_message', 'voice'] engageΔ=+0.069 didΔ=+0.000 → **beneficial**
- ks_cancel v4 (controller_approved) dims=['prompt_version'] engageΔ=+0.102 didΔ=+0.000 → **beneficial**
- nw_renewal v4 (controller_approved) dims=['welcome_message', 'voice'] engageΔ=+0.007 didΔ=+0.000 → **neutral**
- ks_cancel v5 (controller_approved) dims=['welcome_message', 'voice'] engageΔ=-0.025 didΔ=+0.000 → **harmful**

## Governance

```
{
  "approval_requests": 5,
  "decisions": {
    "approved": 5,
    "expired": 0
  },
  "rejection_reasons": {},
  "applied_via_approval": 5,
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
[
  {
    "type": "did_flagged",
    "workflow": "ks_cancel",
    "at": "D2 10:00",
    "flagged_did_share_by_day": {
      "2": 0.501,
      "3": 0.497,
      "4": 0.497,
      "5": 0.505,
      "6": 0.497,
      "7": 0.504,
      "8": 0.49,
      "9": 0.501
    }
  },
  {
    "type": "supervisor_edit",
    "workflow": "ks_cancel",
    "at": "D3 11:30",
    "mttr_minutes": 465,
    "fixed_by": "controller_approved"
  },
  {
    "type": "supervisor_edit",
    "workflow": "nw_renewal",
    "at": "D5 15:00"
  }
]
```

## Decaying variants — share of in-population calls still on the variant, by day after onset

```
{
  "nw_renewal:welcome_message=W3": {
    "2": 0.338,
    "3": 0.325,
    "4": 0.342,
    "5": 0.341,
    "6": 0.07,
    "7": 0.0,
    "8": 0.0,
    "9": 0.0
  }
}
```

Credits used: 3 · validation runs: 1 · LLM fix calls: 0