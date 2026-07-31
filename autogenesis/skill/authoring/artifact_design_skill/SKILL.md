---
name: artifact_design_skill
description: Design guidance and fundamentals for building polished self-contained HTML/web artifacts (pages, dashboards, tools, docs). Use when generating an HTML page or web UI and you want a deliberate, non-templated visual identity calibrated to the task.
version: 1.0.0
type: worker
license: N/A
category: design
requirements: [cpu]
metadata: {}
---

# Artifact Design Skill

Approach this as the design lead at a small studio known for their versatility, giving every client a visual identity pitched at the treatment the task actually calls for. Make deliberate choices about palette, typography, and layout that are specific to this subject, and avoid templated designs.

> Tools: write the HTML with `write_file_tool`, then render and screenshot it with the `artifact_renderer` environment action (`{type:"env", name:"artifact_renderer", args:{html, validate_csp:true}}`). That renderer runs headless Chrome inside the sandbox under a strict CSP (no external CDNs, fonts, scripts, images, or network) — so **inline all CSS/JS and embed assets as `data:` URIs**.

## Read the request first

Calibrate treatment, not whether to design. A doc deserves the same craft as a landing page — what changes is the treatment that craft is delivered in.

Many requests call for a more utilitarian treatment: a plan, a memo, a demo. Make it polished — real typographic hierarchy, considered spacing, a proper palette — but avoid over-designing. Most pages do not need a flashy, gigantic hero. Keep flourishes tasteful and limited.

Some requests call for an editorial treatment: a landing page, a game, an app or tool they'll keep or share.

When unsure: a well-composed page is never the wrong answer; an over-designed visual identity sometimes is. Fundamentals below apply to everything; the editorial process runs only when the read above says so.

## Fundamentals for every artifact

**Honor what's already there.** Look for an existing design system first — CLAUDE.md, a tokens or theme file, existing component styles. When one exists, apply it; everything below fills gaps and never overrides. Precedence: the user's own words, then the project's existing system, then your choices.

**Ground it in the subject.** Pin one concrete subject, its audience, and the page's single job. The subject's own world — materials, instruments, vernacular — is where distinctive choices come from. Build with real content throughout, never lorem.

**Pair typefaces.** Typography carries the page even when the page isn't about typography. If font CDNs are blocked, inline the face as a `@font-face` data URI rather than risking a silent fallback. Keep running text near 65 characters wide; set a type scale and stay on it; give headings `text-wrap: balance`, body text room to breathe, uppercase labels a touch of letter-spacing.

**Choose neutrals, don't default to them.** A pure mid-grey reads as unconsidered; a grey with a slight hue bias toward the page's accent reads as chosen. Pure white and near-black are fine grounds when they suit the subject — the point is the neutral was picked, not inherited.

**Let layout do the spacing.** Lay out sibling groups with flex or grid and `gap`, not per-element margins that collapse or double. Wide content — tables, code, diagrams — gets `overflow-x: auto` on its own container so the page body never scrolls sideways. Use `font-variant-numeric: tabular-nums` wherever digits line up in columns.

**Avoid AI-generated design.** It currently clusters around a few looks: warm cream (#F4F1EA) with a serif display and terracotta accent; near-black with a lone acid-green or vermilion pop; broadsheet hairline rules with dense columns; a purple-to-blue gradient hero on white; Inter or Space Grotesk as the "safe" face; emoji as section markers; everything centered; `rounded-lg` everywhere; accent rail on rounded cards. Where the user pins a direction, follow it exactly. Where nothing is specified, don't spend that freedom on one of these defaults.

**Build cleanly.** Watch for overlapping elements, cascade collisions, silent font fallbacks; visual bugs hide between source and output. Close every non-void element, double-quote attributes, give keyboard focus a visible state, respect `prefers-reduced-motion`. For generative/decorative graphics, reach for Canvas or WebGL rather than hand-authoring long SVG path data.

**Mind CSS specificity.** It's easy to generate classes that cancel each other out — a type-based selector fighting an element-based one over padding. Structure the cascade so it doesn't silently undo your spacing.

**Copy is design material.** Write from the user's side of the screen — name things by what people recognize, not how the system is built. Active voice; a control says exactly what happens ("Publish" → toast "Published"). Errors explain what went wrong and how to fix it. Specific beats clever.

**Structure is information.** Numbering, eyebrows, dividers, labels should encode something true about the content, not decorate it. Numbered markers (01 / 02 / 03) only fit when the content is genuinely a sequence.

**When it's a UI, not a document.** A dashboard or tool is scanned and operated, not read top-to-bottom — craft shifts from typography to information design. Surface summary before detail; encode state in form as well as number (pill, chip, severity stripe). Semantic color (good / warning / critical) is separate from the accent hue. Give sparklines and charts the same care as type. What's interactive should look interactive.

## Process

Before writing code, sketch a short design plan — a compact token system:
- **Color**: 4–6 named hex values.
- **Type**: typefaces for 2+ roles — a characterful display face used with restraint, a complementary body face, a utility face for captions/data if needed.
- **Layout**: a layout concept in one or two sentences.

Then build, deriving every color and type decision from the plan.

## Render & self-check (required)

After writing the HTML, do not stop at "it should look right" — render it and look:

1. `write_file_tool` the HTML to the work dir.
2. Call the `artifact_renderer` env action with the HTML and `validate_csp:true`.
3. Inspect the returned screenshot. If `csp_violations` is non-empty, the page references blocked external resources (CDN/script/font/image/network) that will silently fail to load — fix each by inlining the asset as a `data:` URI, then re-render.
4. Iterate until the screenshot matches the design plan and there are no CSP violations. Only then finish.

## When the request is editorial

The client has already rejected proposals that felt templated and is paying for a distinctive point of view. Make opinionated calls, take one real aesthetic risk where it serves the work. Review the plan against the subject before building: revise any part that reads like the generic default, and note what you changed and why.

- The hero is a thesis: open with the most characteristic thing in the subject's world.
- Typography carries the personality — pair display and body faces deliberately, set a clear scale with intentional weights and spacing.
- Use motion deliberately; an orchestrated moment lands harder than scattered effects. Sometimes less is more — extra animation reads as AI-generated.
- Match complexity to the vision: maximalist needs elaborate execution; minimal needs precision.
- Spend your boldness in one place; keep everything around it quiet.
