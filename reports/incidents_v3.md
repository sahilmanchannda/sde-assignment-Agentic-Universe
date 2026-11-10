# Grade report — public_02_incidents

## Outcomes vs baseline (no-op controller)

| workflow | conclusion rate | Δ | pickup | Δ | engagement | Δ | engagement gap captured | hallucinated calls (base) |
|---|---|---|---|---|---|---|---|---|
| ks_cancel | 0.255 | +8.2% | 0.180 | -0.8% | 0.510 | +8.9% | 33% | 80 (348) |
| nw_kyc | 0.373 | -0.3% | 0.238 | +1.6% | 0.601 | -1.3% | 0% | 32 (29) |
| nw_renewal | 0.435 | +0.5% | 0.262 | -0.0% | 0.560 | +1.0% | 13% | 54 (54) |
| ALL | 0.340 | +2.8% | 0.220 | +0.0% | 0.549 | +3.2% | 22% | 166 (431) |

## Changes applied by the controller

5 applied — beneficial: 3, neutral: 1, harmful: 1

- ks_cancel v2 (controller_approved) dims=['welcome_message', 'voice'] engageΔ=+0.025 didΔ=+0.000 → **beneficial**
- nw_renewal v2 (controller_approved) dims=['welcome_message', 'voice'] engageΔ=+0.069 didΔ=+0.000 → **beneficial**
- ks_cancel v4 (controller_approved) dims=['prompt_version'] engageΔ=+0.102 didΔ=+0.000 → **beneficial**
- nw_renewal v4 (controller_approved) dims=['welcome_message', 'voice'] engageΔ=+0.008 didΔ=+0.000 → **neutral**
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
      "4": 0.499,
      "5": 0.495,
      "6": 0.506,
      "7": 0.502,
      "8": 0.509,
      "9": 0.5
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

Credits used: 3 · validation runs: 1 · LLM fix calls: 0