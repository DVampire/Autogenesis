/* Dynamic Workflow HTML preview renderer — visual schema version 1.1.0. */
(() => {
  "use strict";

  const STEP_TAGS = new Set([
    // Capabilities
    "agent", "tool", "skill", "connector", "environment", "workflow",
    // Data pipeline
    "datasource", "process", "data", "knowledge", "benchmark",
    // Control flow
    "parallel", "map", "reduce", "branch", "loop", "verify", "checkpoint",
  ]);

  const escapeHTML = (value = "") => String(value)
    .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;").replaceAll("'", "&#039;");

  const directChildren = (element, tags = STEP_TAGS) =>
    [...element.children].filter((child) => tags.has(child.tagName.toLowerCase()));

  function detailsFor(step) {
    const keys = [
      "name", "agent", "action", "items", "as", "concurrency", "min-votes",
      "max-rounds", "until", "while", "timeout", "retries", "retry-delay", "retry-backoff",
    ];
    return keys
      .filter((key) => step.hasAttribute(key))
      .map((key) => `<span class="wf-detail">${escapeHTML(key)}=${escapeHTML(step.getAttribute(key))}</span>`)
      .join("");
  }

  function renderStep(step) {
    const kind = step.tagName.toLowerCase();
    const id = step.getAttribute("id") || kind;
    let children = directChildren(step);
    if (kind === "branch") {
      children = [...step.querySelectorAll(":scope > then > *, :scope > else > *")]
        .filter((child) => STEP_TAGS.has(child.tagName.toLowerCase()));
    }
    const taskNode = [...step.children].find((child) => child.tagName.toLowerCase() === "task");
    const task = step.getAttribute("task") || taskNode?.textContent?.trim() || "";
    return `
      <article class="wf-step" data-kind="${escapeHTML(kind)}">
        <div class="wf-step-header">
          <h3 class="wf-step-title">${escapeHTML(id)}</h3>
          <span class="wf-kind">${escapeHTML(kind)}</span>
        </div>
        ${task ? `<p class="wf-task">${escapeHTML(task)}</p>` : ""}
        <div class="wf-details">${detailsFor(step)}</div>
        ${children.length ? `<div class="wf-children">${children.map(renderStep).join("")}</div>` : ""}
      </article>`;
  }

  function render() {
    const source = document.querySelector("workflow");
    const mount = document.querySelector("[data-workflow-preview]");
    if (!source || !mount) return;

    const inputs = [...source.querySelectorAll(":scope > inputs > input")];
    const tags = [...source.querySelectorAll(":scope > applicability > tag")];
    const flow = source.querySelector(":scope > flow");
    const steps = flow ? directChildren(flow) : [];
    const badges = [
      `workflow ${source.getAttribute("version") || "1.0.0"}`,
      `schema ${source.getAttribute("schema-version") || "1.0.0"}`,
      `max agents ${source.getAttribute("max-agents") || "1000"}`,
      `concurrency ${source.getAttribute("max-concurrency") || "16"}`,
    ];

    mount.innerHTML = `
      <header class="wf-hero">
        <div class="wf-eyebrow">Autogenesis · Dynamic Workflow</div>
        <h1 class="wf-title">${escapeHTML(source.getAttribute("name") || "Unnamed workflow")}</h1>
        <p class="wf-description">${escapeHTML(source.getAttribute("description") || "No description")}</p>
        <div class="wf-badges">${badges.map((item) => `<span class="wf-badge">${escapeHTML(item)}</span>`).join("")}</div>
        <div class="wf-tags">${tags.map((tag) => `<span class="wf-tag">${escapeHTML(tag.textContent.trim())}</span>`).join("")}</div>
      </header>
      <div class="wf-grid">
        <section class="wf-section">
          <h2>Inputs</h2>
          ${inputs.length ? inputs.map((input) => `
            <div class="wf-input">
              <strong>${escapeHTML(input.getAttribute("name"))}</strong>
              <span>${escapeHTML(input.getAttribute("type") || "string")}${input.hasAttribute("required") ? " · required" : ""}</span>
            </div>`).join("") : '<p class="wf-empty">No inputs</p>'}
        </section>
        <section class="wf-section">
          <h2>Execution program</h2>
          <div class="wf-flow">${steps.map(renderStep).join("")}</div>
        </section>
      </div>`;
  }

  document.readyState === "loading" ? document.addEventListener("DOMContentLoaded", render) : render();
})();
