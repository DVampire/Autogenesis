---
name: deep_research_skill
description: Deep research harness — fan-out web searches, fetch sources, adversarially verify claims, then synthesize a cited report. Use when the user wants a deep, multi-source, fact-checked research report. If the question is underspecified, ask 2-3 clarifying questions to narrow scope first.
version: 1.0.0
type: worker
license: N/A
category: research
requirements: [cpu]
metadata: {}
---

# Deep Research Skill

A research procedure that searches multiple angles, extracts falsifiable claims,
kills weak ones through adversarial self-verification, and synthesizes a cited
report. Before invoking, check the question is specific enough; if underspecified
(e.g. "what car to buy" without budget/use-case/region), ask 2–3 clarifying
questions and weave the answers into the research question.

## How to run (read first)

This is a **single-agent procedure** — you do every phase yourself, not by
spawning other agents. Your engine is `web_searcher_tool` (already a deep,
multi-engine search that fetches and synthesizes) plus `web_fetcher_tool` for
reading a specific source. The five phases below are the *method you follow
solo*: run several `web_searcher_tool` queries (one per angle), extract
falsifiable claims, then critically re-check each claim yourself before keeping
it. Finish with `done_tool` (`result` = the cited report).

The five phases — treat "Verify" and "Synthesize" as steps you do after the full
claim pool is gathered.

## Phase 1 — Scope

Decompose the research question into **5 search angles** that approach it from
different directions (don't just rephrase). Each angle becomes one search agent.

## Phase 2 — Search (one web_searcher_tool query per angle)

For each angle, call `web_searcher_tool`. Aim for:

> Search the web for the angle's query. Rank results by relevance to the
> ORIGINAL question, not just the search query. Skip obvious SEO spam / content
> farms. Include a short snippet capturing why each result is relevant.
> Structured output only.

Then URL-dedup across angles and cap the number of sources fetched (≈top 15 by
relevance), so duplicate and low-relevance URLs don't burn the fetch budget.

## Phase 3 — Fetch + extract (per source)

For each novel source, read it with `web_fetcher_tool` and extract claims using
this rubric:

> **## Source Extractor**
> Research question: "<QUESTION>"
> Fetch and extract key claims from this source (URL, title, found-via angle).
> 1. Retrieve the page content.
> 2. Assess source quality: primary research/institution? secondary reporting?
>    blog/opinion? forum? unreliable?
> 3. Extract 2–5 FALSIFIABLE claims that bear on the question. Each must be a
>    concrete, checkable statement; include a direct supporting quote; and be
>    rated central/supporting/tangential.
> 4. Note publish date if available.
> If the fetch fails or the page is irrelevant/paywalled, return claims: [] and
> sourceQuality: "unreliable". Structured output only.

Collect all claims. Rank by importance (central > supporting > tangential), then
by source quality (primary > secondary > blog > forum > unreliable), and keep the
top N for verification.

## Phase 4 — Verify (adversarial self-check)

For each ranked claim, deliberately try to REFUTE it yourself (use
`web_searcher_tool` to look for contradicting evidence). Apply this checklist
with a skeptical default — if it doesn't hold up, drop the claim:

> **## Adversarial Claim Verifier**
> Be SKEPTICAL. Try to REFUTE this claim.
> Given the research question, the claim, its source + quality, and the
> supporting quote, check:
> 1. Is the claim actually supported by the quote, or an overreach/misread?
> 2. Web-search for contradicting evidence — does any credible source dispute it?
> 3. Is the source quality sufficient for the claim's strength? (extraordinary
>    claims need primary sources)
> 4. Is the claim outdated? (old claims about fast-moving fields are suspect)
> 5. Is this marketing / press release / cherry-picked benchmark / forum
>    speculation?
> **refuted=true** if: unsupported by quote / contradicted / low-quality source
> for a strong claim / outdated / marketing fluff.
> **refuted=false** ONLY if: well-supported, current, and source quality matches
> claim strength. **Default to refuted=true if uncertain.** Evidence must be
> specific. Structured output only.

A claim survives only if it was actually adjudicated: a quorum of valid votes AND
fewer than the required refutations. Too many abstentions = unverified, which must
NOT pass into the report. If every claim is refuted, report the research as
inconclusive (sources may be low-quality or claims overstated).

## Phase 5 — Synthesize

From the surviving claims (with their sources, quotes, and the evidence that
held up under your verification), synthesize the report:

> **## Synthesis: research report**
> Given the confirmed claims (and, for transparency, the refuted ones):
> 1. Identify claims that say the same thing — merge them, combine their sources.
> 2. Group related claims into coherent findings, each directly addressing the
>    research question.
> 3. Assign confidence per finding: high (multiple primary sources, unanimous
>    votes), medium (secondary sources or split votes), low (single source or
>    blog-quality).
> 4. Write a 3–5 sentence executive summary answering the question.
> 5. Note caveats: what's uncertain, weak sources, time-sensitivity.
> 6. List 2–4 open questions that emerged but weren't answered.

## Output

Return the report: the executive summary, grouped findings with per-finding
confidence and citations, a transparency list of refuted claims with vote
tallies, the source list with quality ratings, and run stats (angles, sources
fetched, claims extracted/verified/confirmed/killed).
