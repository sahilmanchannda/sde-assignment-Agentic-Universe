# Grade report — public_02_incidents

## Outcomes vs baseline (no-op controller)

| workflow | conclusion rate | Δ | pickup | Δ | engagement | Δ | engagement gap captured | hallucinated calls (base) |
|---|---|---|---|---|---|---|---|---|
| ks_cancel | 0.257 | +8.9% | 0.179 | -1.3% | 0.516 | +10.2% | 36% | 107 (348) |
| nw_kyc | 0.371 | -0.8% | 0.239 | +2.0% | 0.595 | -2.1% | 0% | 31 (29) |
| nw_renewal | 0.438 | +1.1% | 0.264 | +0.8% | 0.559 | +0.8% | 13% | 57 (54) |
| ALL | 0.341 | +3.2% | 0.220 | +0.2% | 0.550 | +3.3% | 23% | 195 (431) |

## Changes applied by the controller

7 applied — beneficial: 4, neutral: 1, harmful: 2

- ks_cancel v2 (controller_approved) dims=['welcome_message', 'voice'] engageΔ=+0.025 didΔ=+0.000 → **beneficial**
- nw_renewal v2 (controller_approved) dims=['welcome_message', 'voice'] engageΔ=+0.069 didΔ=+0.000 → **beneficial**
- ks_cancel v4 (controller_approved) dims=['prompt_version'] engageΔ=+0.102 didΔ=+0.000 → **beneficial**
- nw_renewal v4 (controller_approved) dims=['welcome_message', 'voice'] engageΔ=+0.008 didΔ=+0.000 → **neutral**
- ks_cancel v5 (controller_approved) dims=['welcome_message', 'voice'] engageΔ=-0.025 didΔ=+0.000 → **harmful**
- ks_cancel v6 (controller_approved) dims=['prompt_version'] engageΔ=+0.050 didΔ=+0.000 → **beneficial**
- ks_cancel v7 (controller_approved) dims=['prompt_version'] engageΔ=-0.048 didΔ=+0.000 → **harmful**

## Governance

```
{
  "approval_requests": 7,
  "decisions": {
    "approved": 7,
    "expired": 0
  },
  "rejection_reasons": {},
  "applied_via_approval": 7,
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
      "4": 0.499,
      "5": 0.495,
      "6": 0.506,
      "7": 0.503,
      "8": 0.497,
      "9": 0.499
    }
  },
  {
    "type": "supervisor_edit",
    "workflow": "ks_cancel",
    "at": "D3 11:30",
    "mttr_minutes": 1485,
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
    "4": 0.327,
    "5": 0.344,
    "6": 0.07,
    "7": 0.0,
    "8": 0.0,
    "9": 0.0
  }
}
```

Credits used: 15 · validation runs: 4 · LLM fix calls: 1