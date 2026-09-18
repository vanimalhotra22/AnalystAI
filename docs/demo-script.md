# Five-minute demo script

Have both servers running and the browser on the **landing page** (`/`), signed out.

```bash
cd backend && ../.venv/Scripts/python -m uvicorn app.api.main:app --reload
```

```bash
cd frontend && npm run dev
```

---

## 0:00 – 0:25 · Landing and sign-in

> "This is the product surface — what it does, how a run unfolds, and what is under the hood."

Scroll once through the hero (the trace on the right is a real run, replayed), then click
**Use the demo account → Continue with the demo account**.

> "Accounts are real: scrypt-hashed passwords, a signed session in an httpOnly cookie, and
> every analytics route 401s without one. The demo account exists so I never type a password
> on stage."

## 0:25 – 1:00 · The problem

> "This is a dashboard view of a consumer-health business — revenue down 5.5% in July, North
> down, four availability alerts. A dashboard tells me *what* happened. Every question my
> manager actually asks starts with *why*, and answering that is an hour of SQL: regions,
> products, inventory, suppliers, marketing, pricing, customers.
>
> InsightPilot does that investigation. The data is synthetic and generated for this demo."

Point at the *Current position* panel and the availability alerts.

## 1:00 – 1:30 · The architecture, briefly

> "React front end, FastAPI, a LangGraph supervisor, and fourteen typed tools over
> PostgreSQL, pandas, scikit-learn and a small policy knowledge base.
>
> The rule that shapes everything: **the model never produces a number.** SQL and pandas
> compute; the model decides what to compute next and writes the summary. That is what makes
> the output checkable."

## 1:30 – 3:00 · Run the investigation

Click *"Revenue decreased this month. Find out why and recommend what we should do."* →
**Investigate**. Let the feed stream; narrate as steps land.

> "It measures the headline first — and notice it reports both the total change and the
> per-day rate, because July has 31 days and June has 30. That 3% is mechanical, not
> business.
>
> Now it localises: North carries 76% of the decline. It runs an anomaly scan *inside* North
> — robust z-score plus IsolationForest against each product's own twelve-month history —
> and the air purifier comes out at z = -3.5.
>
> Here is the step I care about. It asks the inventory ledger what demand actually was:
> 79 units wanted, 39 served. A 49% fill rate. That single test separates a supply problem
> from a demand problem, and it is why the next step is the supply chain and not marketing.
>
> Seventeen stockout days, then upstream: purchase order PO-000214 from AirTech, promised
> the 2nd, received the 18th — sixteen days late, against a baseline delay of one day.
>
> And then it does the thing analysts skip: it tests the explanations it expects to be
> innocent. Marketing in North is down 36% — that is a real secondary driver. Pricing moved
> 0.07 points and the customer base is flat, so both are ruled out on evidence."

## 3:00 – 4:00 · The conclusion

Move to the right-hand panel.

> "Root cause, with the originating cause named separately. Below it, the traced mechanism —
> six links, each with a number and the table it came from. Click any hypothesis to see its
> evidence.
>
> Confidence is 80%, and it tells you how it got there: strongest hypothesis 0.95, three
> alternatives ruled out, but the quantified impact only covers 35% of the total movement —
> so it does not claim more than it can support. It is capped at 92% by design; one month of
> evidence is never near-certainty."

## 4:00 – 4:30 · The decision

> "Recommendations are costed and cited, not invented. 'Raise safety stock to the Class A
> minimum' comes from the inventory policy retrieved by the RAG step — the agent did not pick
> 15% out of the air. The what-if card is a Monte-Carlo on the product's own demand history
> and the supplier's own lead-time distribution: risk 2.8% → 1.3%, protected revenue against
> holding cost, net benefit per 90 days.
>
> Every item that costs money is flagged *needs approval*. The agent proposes; a human
> disposes."

## 4:30 – 5:00 · Engineering

> "Guardrails: the SQL tool validates single-statement SELECT only, allow-lists the nine
> analytics tables, blocks comment smuggling, caps rows — and then runs on a read-only
> connection, so even a validator bug cannot write. There are tests for the refusals.
>
> Evaluation: 34 business questions, 150 machine checks, including the agent's headline
> figure against an independently written SQL query. All passing.
>
> And it degrades gracefully — with no API key the deterministic investigation policy drives
> the same tools, and the UI says which planner is running."

---

## Follow-ups worth having ready

| ask | do |
|---|---|
| "Ask it something else" | *"Which supplier caused the delays?"* — a three-step run, not fourteen |
| "Can it do scenarios?" | *"What if we increase safety stock by 25% for P103 in North?"* |
| "What if the cause were different?" | *"Was the decline caused by discounting?"* — it tests and rules it out |
| "Show me the guardrail" | `POST /api/sql` with `DELETE FROM sales` → refusal from the validator |
| "Is the app actually secured?" | Sign out, then hit `/app` directly → bounced to sign-in; `curl /api/dashboard` → 401 |
| "Is it hard-coded?" | Change `SEED` in `.env`, regenerate, re-run — the chain is re-derived |
