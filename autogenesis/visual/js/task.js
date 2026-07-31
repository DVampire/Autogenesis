// Task document view — renders the Markdown authored inside each semantic
// section tag (<objective>, <requirements>, …) to HTML, client-side. This is
// the task analogue of how prompt.js renders Markdown inside the prompt tags,
// so opening a task .html file directly shows nicely formatted lists / tables /
// code without any build step. No dependencies.
(function () {
  "use strict";

  function esc(s) {
    return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  function inline(s) {
    s = esc(s);
    s = s.replace(/`([^`]+)`/g, "<code>$1</code>");
    s = s.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    s = s.replace(/\*([^*]+)\*/g, "<em>$1</em>");
    s = s.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2">$1</a>');
    return s;
  }

  function dedent(md) {
    var lines = md.replace(/\r\n?/g, "\n").split("\n");
    var indents = lines
      .filter(function (l) { return l.trim(); })
      .map(function (l) { return l.match(/^\s*/)[0].length; });
    var min = indents.length ? Math.min.apply(null, indents) : 0;
    return lines.map(function (l) { return l.slice(min); }).join("\n");
  }

  function isTableSep(l) {
    return l.indexOf("|") >= 0 && /^[\s:|-]*-[\s:|-]*$/.test(l.trim());
  }

  function cells(l) {
    return l.trim().replace(/^\|/, "").replace(/\|$/, "")
      .split("|").map(function (c) { return c.trim(); });
  }

  function renderMarkdown(md) {
    var lines = dedent(md).split("\n");
    var out = [], i = 0;
    while (i < lines.length) {
      var line = lines[i];

      if (/^\s*```/.test(line)) {                       // fenced code block
        var buf = []; i++;
        while (i < lines.length && !/^\s*```/.test(lines[i])) { buf.push(lines[i]); i++; }
        i++;
        out.push("<pre><code>" + esc(buf.join("\n")) + "</code></pre>");
        continue;
      }

      if (line.indexOf("|") >= 0 && i + 1 < lines.length && isTableSep(lines[i + 1])) {  // table
        var header = line; i += 2;
        var body = [];
        while (i < lines.length && lines[i].indexOf("|") >= 0 && lines[i].trim()) { body.push(lines[i]); i++; }
        var h = "<table><thead><tr>" +
          cells(header).map(function (c) { return "<th>" + inline(c) + "</th>"; }).join("") +
          "</tr></thead><tbody>";
        body.forEach(function (r) {
          h += "<tr>" + cells(r).map(function (c) { return "<td>" + inline(c) + "</td>"; }).join("") + "</tr>";
        });
        out.push(h + "</tbody></table>");
        continue;
      }

      if (/^\s*[-*]\s+/.test(line)) {                   // unordered list
        var items = [];
        while (i < lines.length && /^\s*[-*]\s+/.test(lines[i])) { items.push(lines[i].replace(/^\s*[-*]\s+/, "")); i++; }
        out.push("<ul>" + items.map(function (t) { return "<li>" + inline(t) + "</li>"; }).join("") + "</ul>");
        continue;
      }

      if (/^\s*\d+\.\s+/.test(line)) {                  // ordered list
        var oitems = [];
        while (i < lines.length && /^\s*\d+\.\s+/.test(lines[i])) { oitems.push(lines[i].replace(/^\s*\d+\.\s+/, "")); i++; }
        out.push("<ol>" + oitems.map(function (t) { return "<li>" + inline(t) + "</li>"; }).join("") + "</ol>");
        continue;
      }

      if (line.trim() === "") { i++; continue; }        // blank

      var para = [];                                     // paragraph
      while (i < lines.length && lines[i].trim() &&
             !/^\s*```/.test(lines[i]) &&
             !/^\s*[-*]\s+/.test(lines[i]) &&
             !/^\s*\d+\.\s+/.test(lines[i]) &&
             !(lines[i].indexOf("|") >= 0 && i + 1 < lines.length && isTableSep(lines[i + 1]))) {
        para.push(lines[i]); i++;
      }
      out.push("<p>" + inline(para.join(" ")) + "</p>");
    }
    return out.join("\n");
  }

  function init() {
    document.querySelectorAll("div.task > *").forEach(function (sec) {
      sec.innerHTML = renderMarkdown(sec.textContent);
      sec.addEventListener("click", function () {
        if (window.getSelection && String(window.getSelection())) return;
        sec.classList.toggle("collapsed");
      });
    });
  }

  if (typeof document !== "undefined") {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", init);
    } else {
      init();
    }
  }
  if (typeof module !== "undefined" && module.exports) {
    module.exports = { renderMarkdown: renderMarkdown };  // for node tests
  }
})();
