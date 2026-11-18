---
name: manifest-investing
description: "Track investments in Manifest ideas: cash and sweat-equity investments, contributions, status, cap tables and the person's portfolio. Use when a person asks what they've invested, who owns what, or wants to record an investment or hours worked."
---

# Investments and cap tables

These are records the founders keep in Manifest, not payments: nothing moves money. They are still hard to undo, so the writes need `confirm: true`.

- `my_portfolio`: everything the person has invested in, with totals.
- `idea_investments` and `idea_cap_table`: who holds what in one idea.
- `calculate_sweat_equity`: value and percentage for hours at an hourly rate and valuation (read-only; good for "what if").
- `create_investment` (input: ideaId, cashAmount, sweatEquityHours, hourlyRate, equityPercentage, investmentType, role, notes): read the numbers back to the person before confirming.
- `add_investment_contribution`: log more cash or hours against an existing investment.
- `update_investment_status`: change an investment's status.

Cap tables and valuations are working records, not legal or financial advice.
