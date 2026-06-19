Evaluating a tender proposal requires a bit more structure than just dumping the raw text into a single chat window. If you paste a massive RFP (Request for Proposal) and your 50-page draft into a standard agent context window all at once, the LLM will often suffer from **"lost in the middle" syndrome**—it will miss subtle compliance gaps, hallucinate that a requirement was met, or give you generic advice like *"Make the tone more professional."*

To get an audit that actually protects you from being disqualified, you want to set up an agentic workflow that treats the evaluation like a multi-stage corporate compliance review.

The most reliable approach breaks down into three distinct steps:

---

## 1. The Pre-Processing Step (The Matrix)

Before you look at your draft, you need an agent to extract a **Compliance Matrix** from the buyer's tender documents.

Instead of asking the agent to evaluate the whole document, you give it the RFP and ask it to output a clean, structured list of absolute constraints.

> **Prompt for Agent 1 (The Auditor):**
> *"Scan this RFP and extract every mandatory requirement, evaluation criteria, page limit, formatting rule, and technical specification. Output this as a structured markdown table with three columns: [Requirement ID, Description, Scoring Weight/Pass-Fail Status]."*

## 2. The Fragmented Evaluation Step (Section by Section)

Once you have your matrix, you feed the evaluation agent **one section of your proposal at a time**, alongside the specific requirements mapped to that section.

Evaluating piece-by-piece ensures the LLM reads every sentence critically rather than skimming.

```
                  ┌──────────────────────┐
                  │   Compliance Matrix  │
                  └──────────┬───────────┘
                             │ (Matches Section 3.2)
                             ▼
┌───────────────────┐    ┌──────────┐    ┌────────────────────┐
│ Your Draft Sec 3.2├───►│Evaluator │◄───┤ Scoring Rubric &  │
│   (Technical)     │    │  Agent   │    │ Evaluation Criteria│
└───────────────────┘    └────┬─────┘    └────────────────────┘
                              │
                              ▼
                 ┌─────────────────────────┐
                 │  - Gap Analysis Report  │
                 │  - Estimated Score      │
                 │  - Redline Suggestions  │
                 └─────────────────────────┘

```

## 3. The 3-Persona Agentic Workflow (Advanced Self-Hosting)

If you use a tool like **CrewAI** or **Flowise**, you can automate this by setting up three distinct agents that pass the document between themselves. This mirrors how a real bid review board works:

| Agent Persona | Responsibility | What it looks for |
| --- | --- | --- |
| **Agent 1: The Black-Hat Evaluator** | Acts as a strict, cynical buyer looking for any excuse to disqualify your bid or dock points. | Missing case studies, passive voice, unproven claims, unmapped requirements. |
| **Agent 2: The Domain Expert** | Reviews the technical and commercial substance of the answers. | Technical accuracy, alignment with industry standards, clear methodology. |
| **Agent 3: The Editor / Closer** | Synthesizes the feedback from the first two agents into an actionable "redline" checklist. | Specific instructions on *how* to rewrite the failing sections to maximize points. |

---

### A Proven Prompt Template for Evaluation

If you *are* using a single-agent interface like AnythingLLM or a custom web UI for speed, do not just say *"Evaluate this."* Use a structured prompt that forces deep critical analysis:

```markdown
You are a Lead Tender Evaluator for [Industry/Sector]. Your job is to rigorously score the attached PROPOSAL DRAFT against the provided RFP REQUIREMENTS.

For your evaluation, you must ignore politeness and focus purely on score optimization. Analyze the text and provide feedback in the following format:

1. COMPLIANCE SCORECARD: Rate each mandatory requirement as [MET], [PARTIALLY MET], or [NOT MET].
2. CAP ANALYSIS: For any requirement marked partially or not met, explicitly state what information is missing.
3. PROOF GAP: Identify where the draft makes a claim (e.g., "We are experts in X") but fails to back it up with a metric, case study, or CV reference.
4. ACTIONABLE REDLINES: Provide specific rewrite examples for the weakest sections to increase our score according to the evaluation criteria.

```

By isolating the criteria first and forcing the agent to act as a critical reviewer rather than a collaborative writer, you will get feedback that actually catches errors before the real evaluators see them.
