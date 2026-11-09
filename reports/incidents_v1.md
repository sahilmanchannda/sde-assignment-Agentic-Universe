# Grade report — public_02_incidents

## Outcomes vs baseline (no-op controller)

| workflow | conclusion rate | Δ | pickup | Δ | engagement | Δ | engagement gap captured | hallucinated calls (base) |
|---|---|---|---|---|---|---|---|---|
| ks_cancel | 0.262 | +11.4% | 0.187 | +3.1% | 0.497 | +6.3% | 34% | 104 (348) |
| nw_kyc | 0.372 | -0.4% | 0.241 | +2.8% | 0.590 | -3.0% | 0% | 27 (29) |
| nw_renewal | 0.432 | -0.2% | 0.266 | +1.4% | 0.547 | -1.4% | -2% | 48 (54) |
| ALL | 0.342 | +3.5% | 0.225 | +2.4% | 0.537 | +0.8% | 17% | 179 (431) |

## Changes applied by the controller

9 applied — beneficial: 5, neutral: 3, harmful: 1

- ks_cancel v2 (controller_approved) dims=['welcome_message', 'voice'] engageΔ=+0.025 didΔ=+0.000 → **beneficial**
- nw_renewal v2 (controller_approved) dims=['welcome_message', 'voice'] engageΔ=+0.069 didΔ=+0.000 → **beneficial**
- ks_cancel v3 (controller_approved) dims=['cohorts', 'schedule'] engageΔ=+0.000 didΔ=+0.000 → **neutral**
- nw_kyc v2 (controller_approved) dims=['cohorts', 'schedule'] engageΔ=+0.000 didΔ=+0.000 → **neutral**
- nw_renewal v3 (controller_approved) dims=['cohorts', 'schedule'] engageΔ=+0.000 didΔ=+0.000 → **neutral**
- nw_renewal v4 (controller_approved) dims=['welcome_message', 'voice'] engageΔ=+0.080 didΔ=+0.000 → **beneficial**
- ks_cancel v5 (controller_approved) dims=['prompt_version'] engageΔ=+0.102 didΔ=+0.000 → **beneficial**
- ks_cancel v6 (controller_approved) dims=['welcome_message', 'voice'] engageΔ=-0.025 didΔ=+0.000 → **harmful**
- nw_renewal v6 (controller_approved) dims=['welcome_message', 'voice'] engageΔ=+0.070 didΔ=+0.000 → **beneficial**

## Governance

```
{
  "approval_requests": 11,
  "decisions": {
    "approved": 9,
    "rejected": 2,
    "expired": 0
  },
  "rejection_reasons": {
    "approver declined (judgement call)": 2
  },
  "applied_via_approval": 9,
  "auto_applied": 0,
  "auto_apply_rejected": 0,
  "apply_conflicts": 0,
  "lapsed": 0,
  "peak_requests_per_24h": {
    "nw_renewal": 2,
    "ks_cancel": 2,
    "nw_kyc": 1
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
      "2": 0.495,
      "3": 0.493,
      "4": 0.507,
      "5": 0.497,
      "6": 0.502,
      "7": 0.501,
      "8": 0.49,
      "9": 0.5
    }
  },
  {
    "type": "supervisor_edit",
    "workflow": "ks_cancel",
    "at": "D3 11:30",
    "mttr_minutes": 1410,
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
    "2": 0.777,
    "3": 0.896,
    "4": 0.899,
    "5": 0.892,
    "6": 0.911,
    "7": 0.396,
    "8": 0.0,
    "9": 0.0
  }
}
```

Credits used: 3 · validation runs: 1 · LLM fix calls: 0