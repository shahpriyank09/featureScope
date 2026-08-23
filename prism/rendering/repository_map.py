from __future__ import annotations

import base64

from prism.models import RepositoryMap


def render_repository_map_html(repository_map: RepositoryMap, height: int = 820) -> str:
    """Render a purpose-built architecture landscape centered on the PR's impact."""

    payload = base64.b64encode(
        repository_map.model_dump_json().encode("utf-8")
    ).decode("ascii")
    return f"""
<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <style>
      :root {{ color-scheme: light; font-family: Inter, ui-sans-serif, system-ui, sans-serif; }}
      * {{ box-sizing: border-box; }}
      body {{ margin: 0; background: #f8fafc; color: #101828; }}
      .shell {{ height: {height}px; display: grid; grid-template-rows: auto minmax(0, 1fr); gap: 10px; }}
      .toolbar {{ display: flex; flex-wrap: wrap; align-items: center; gap: 8px; padding: 10px;
                  border: 1px solid #e4e7ec; border-radius: 12px; background: white; }}
      button.mode {{ border: 1px solid #d0d5dd; border-radius: 8px; padding: 7px 11px; background: white;
                     color: #344054; cursor: pointer; font-weight: 700; }}
      button.mode.active {{ background: #6941c6; border-color: #6941c6; color: white; }}
      input {{ min-width: 230px; flex: 1; border: 1px solid #d0d5dd; border-radius: 8px;
               padding: 8px 10px; }}
      .legend {{ display: flex; flex-wrap: wrap; gap: 9px; color: #475467; font-size: 12px; }}
      .legend span {{ display: inline-flex; align-items: center; gap: 4px; }}
      .dot {{ width: 10px; height: 10px; border-radius: 3px; display: inline-block; }}
      .content {{ min-height: 0; display: grid; grid-template-columns: minmax(0, 1fr) 350px; gap: 10px; }}
      #landscape {{ position: relative; min-height: 0; overflow: hidden; border: 1px solid #e4e7ec;
                    border-radius: 14px; background:
                    radial-gradient(circle at 50% 45%, rgba(105,65,198,.07), transparent 34%),
                    linear-gradient(180deg, #ffffff 0%, #fafaff 100%); }}
      #landscape::before {{ content: ""; position: absolute; inset: 0; opacity: .35; pointer-events: none;
                            background-image: radial-gradient(#d0d5dd 1px, transparent 1px);
                            background-size: 22px 22px; }}
      #edges, #cards {{ position: absolute; inset: 0; width: 100%; height: 100%; }}
      #edges {{ pointer-events: none; overflow: visible; }}
      .relationship {{ fill: none; stroke: #98a2b3; stroke-width: 2; opacity: .58;
                       transition: opacity .18s, stroke .18s, stroke-width .18s; }}
      .relationship.active {{ stroke: #6941c6; stroke-width: 3; opacity: 1; }}
      .relationship.dim {{ opacity: .09; }}
      .edge-label {{ fill: #667085; font: 650 10px Inter, sans-serif; text-anchor: middle;
                     paint-order: stroke; stroke: white; stroke-width: 5px; stroke-linejoin: round; }}
      .edge-label.dim {{ opacity: .12; }}
      .lane-label {{ position: absolute; top: 14px; transform: translateX(-50%); color: #98a2b3;
                     font-size: 10px; font-weight: 800; letter-spacing: .1em; text-transform: uppercase; }}
      .block-card {{ position: absolute; width: 176px; min-height: 112px; transform: translate(-50%, -50%);
                     border: 2px solid #98a2b3; border-radius: 13px; padding: 11px 12px; text-align: left;
                     background: rgba(255,255,255,.96); color: #101828; cursor: pointer;
                     box-shadow: 0 5px 16px rgba(16,24,40,.08); transition: transform .16s, opacity .16s,
                     box-shadow .16s, border-color .16s; overflow: hidden; }}
      .block-card:hover, .block-card.active {{ transform: translate(-50%, -50%) scale(1.045); z-index: 5;
                                               box-shadow: 0 12px 28px rgba(16,24,40,.16); }}
      .block-card.dim {{ opacity: .22; }}
      .block-card.modified {{ border-color: #f79009; background: #fffaf1; }}
      .block-card.added {{ border-color: #12b76a; background: #f1fbf6; }}
      .block-card.removed {{ border-color: #f04438; background: #fff5f4; }}
      .block-card.renamed {{ border-color: #2e90fa; background: #f4f8ff; }}
      .block-card.impacted {{ border-color: #7f56d9; background: #f8f5ff; }}
      .block-card.search-pulse {{ animation: pulse .8s ease-out 1; }}
      @keyframes pulse {{ 50% {{ box-shadow: 0 0 0 8px rgba(105,65,198,.18); }} }}
      .block-kicker {{ display: flex; align-items: center; justify-content: space-between; gap: 7px;
                       color: #667085; font-size: 10px; font-weight: 800; text-transform: uppercase; }}
      .impact-badge {{ border-radius: 999px; padding: 2px 6px; background: #f79009; color: white; }}
      .connected-badge {{ border-radius: 999px; padding: 2px 6px; background: #7f56d9; color: white; }}
      .block-card h3 {{ margin: 7px 0 4px; font-size: 16px; line-height: 1.1; }}
      .block-meta {{ margin: 0; color: #475467; font-size: 11px; font-weight: 650; }}
      .block-purpose {{ margin: 6px 0 0; color: #667085; font-size: 10px; line-height: 1.3;
                        display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
                        overflow: hidden; }}
      #details {{ border: 1px solid #d6bbfb; border-radius: 14px; background: white; padding: 16px;
                  overflow: auto; box-shadow: 0 5px 18px rgba(105,65,198,.08); }}
      #details h3 {{ margin: 8px 0 5px; font-size: 19px; overflow-wrap: anywhere; }}
      #details h4 {{ margin: 15px 0 7px; font-size: 12px; color: #344054; letter-spacing: .04em; }}
      #details p {{ margin: 5px 0; color: #475467; font-size: 13px; overflow-wrap: anywhere; }}
      .note-pill {{ display: inline-flex; padding: 3px 7px; border-radius: 6px; background: #f4ebff;
                    color: #6941c6; font: 700 11px ui-monospace, monospace; }}
      .status {{ text-transform: capitalize; font-weight: 750; }}
      .file-list {{ display: grid; gap: 6px; }}
      .file-row {{ border: 1px solid #eaecf0; border-radius: 7px; padding: 7px 8px; font-size: 12px;
                   overflow-wrap: anywhere; background: #fcfcfd; }}
      .file-row a {{ color: #344054; text-decoration: none; font-weight: 620; }}
      .file-row a:hover {{ color: #6941c6; text-decoration: underline; }}
      .file-meta {{ display: block; color: #667085; margin-top: 3px; }}
      .badge {{ display: inline-block; margin-left: 5px; border-radius: 999px; padding: 1px 5px;
                color: white; font-size: 10px; text-transform: uppercase; }}
      details {{ margin-top: 14px; font-size: 12px; color: #475467; }}
      pre {{ white-space: pre-wrap; overflow-wrap: anywhere; font-size: 11px; background: #f9fafb;
             border: 1px solid #eaecf0; padding: 9px; border-radius: 7px; }}
      .hint {{ color: #667085; font-size: 12px; }}
      @media (max-width: 900px) {{
        .shell {{ height: {height}px; }}
        .content {{ grid-template-columns: 1fr; grid-template-rows: 510px minmax(0, 1fr); }}
        #details {{ padding: 13px; }}
      }}
    </style>
  </head>
  <body>
    <div class="shell">
      <div class="toolbar">
        <button id="impact" class="mode active">Change impact</button>
        <button id="all" class="mode">Full architecture</button>
        <input id="search" type="search" placeholder="Find a block, file, or symbol…" />
        <div class="legend">
          <span><i class="dot" style="background:#f79009"></i>Changed</span>
          <span><i class="dot" style="background:#12b76a"></i>Added</span>
          <span><i class="dot" style="background:#f04438"></i>Removed</span>
          <span><i class="dot" style="background:#7f56d9"></i>Connected</span>
          <span><i class="dot" style="background:#98a2b3"></i>Unchanged</span>
        </div>
      </div>
      <div class="content">
        <section id="landscape" aria-label="Repository architecture impact map">
          <svg id="edges" aria-hidden="true"></svg>
          <div id="cards"></div>
        </section>
        <aside id="details">
          <span id="note-path" class="note-pill">Blocks/README.md</span>
          <h3>Architecture block README</h3>
          <p id="detail-status" class="status">Hover over a block</p>
          <p id="detail-description">Its Obsidian note, contained files, and PR changes appear here.</p>
          <h4 id="changed-title">CHANGED IN THIS PR</h4>
          <div id="changed-files" class="file-list"></div>
          <h4>FILES IN THIS BLOCK</h4>
          <div id="all-files" class="file-list"></div>
          <details>
            <summary>View Obsidian Markdown</summary>
            <pre id="markdown-note"></pre>
          </details>
        </aside>
      </div>
    </div>
    <script>
      const encoded = "{payload}";
      const bytes = Uint8Array.from(atob(encoded), character => character.charCodeAt(0));
      const graph = JSON.parse(new TextDecoder().decode(bytes));
      const changedStatuses = new Set(["modified", "added", "removed", "renamed"]);
      const badgeColors = {{
        unchanged: "#98a2b3", impacted: "#7f56d9", modified: "#f79009",
        added: "#12b76a", removed: "#f04438", renamed: "#2e90fa"
      }};
      const blockById = new Map(graph.blocks.map(block => [block.id, block]));
      const landscape = document.getElementById("landscape");
      const cardsLayer = document.getElementById("cards");
      const edgeSvg = document.getElementById("edges");
      let mode = "impact";
      let activeBlockId = null;

      function visibleBlocks() {{
        if (mode === "all") return graph.blocks;
        const focused = graph.blocks.filter(block => block.focused || changedStatuses.has(block.status));
        return focused.length ? focused : graph.blocks;
      }}

      function distribute(items, x, height, top = 92, bottom = 76) {{
        const usable = Math.max(1, height - top - bottom);
        return new Map(items.map((item, index) => [
          item.id,
          {{ x, y: top + usable * ((index + 1) / (items.length + 1)) }}
        ]));
      }}

      function positionsFor(blocks, width, height) {{
        if (mode === "all") {{
          const columns = width < 560 ? 2 : 3;
          const rows = Math.ceil(blocks.length / columns);
          const positions = new Map();
          blocks.forEach((block, index) => {{
            const column = index % columns;
            const row = Math.floor(index / columns);
            positions.set(block.id, {{
              x: width * ((column + .5) / columns),
              y: 82 + (height - 142) * ((row + .5) / Math.max(rows, 1))
            }});
          }});
          return positions;
        }}

        const changedBlocks = blocks.filter(block => changedStatuses.has(block.status));
        const contextBlocks = blocks.filter(block => !changedStatuses.has(block.status));
        const left = contextBlocks.filter((_, index) => index % 2 === 0);
        const right = contextBlocks.filter((_, index) => index % 2 === 1);
        const positions = distribute(changedBlocks, width * .5, height, 98, 72);
        for (const [id, point] of distribute(left, width * .17, height, 108, 72)) positions.set(id, point);
        for (const [id, point] of distribute(right, width * .83, height, 108, 72)) positions.set(id, point);
        return positions;
      }}

      function cardFor(block, position) {{
        const card = document.createElement("button");
        card.type = "button";
        card.className = `block-card ${{block.status}}`;
        card.dataset.blockId = block.id;
        card.style.left = `${{position.x}}px`;
        card.style.top = `${{position.y}}px`;

        const kicker = document.createElement("div");
        kicker.className = "block-kicker";
        const status = document.createElement("span");
        status.textContent = block.path;
        kicker.appendChild(status);
        const changedFiles = block.files.filter(file => changedStatuses.has(file.status));
        if (changedFiles.length) {{
          const badge = document.createElement("span");
          badge.className = "impact-badge";
          badge.textContent = `${{changedFiles.length}} changed`;
          kicker.appendChild(badge);
        }} else if (block.status === "impacted") {{
          const badge = document.createElement("span");
          badge.className = "connected-badge";
          badge.textContent = "connected";
          kicker.appendChild(badge);
        }}
        card.appendChild(kicker);

        const heading = document.createElement("h3");
        heading.textContent = block.label;
        card.appendChild(heading);
        const metadata = document.createElement("p");
        metadata.className = "block-meta";
        metadata.textContent = `${{block.files.length}} file${{block.files.length === 1 ? "" : "s"}}`;
        card.appendChild(metadata);
        const purpose = document.createElement("p");
        purpose.className = "block-purpose";
        purpose.textContent = block.description;
        card.appendChild(purpose);

        card.addEventListener("mouseenter", () => {{ showDetails(block); highlight(block.id); }});
        card.addEventListener("mouseleave", clearHighlight);
        card.addEventListener("focus", () => {{ showDetails(block); highlight(block.id); }});
        card.addEventListener("blur", clearHighlight);
        card.addEventListener("click", () => {{ activeBlockId = block.id; showDetails(block); highlight(block.id); }});
        return card;
      }}

      function drawEdges(visibleIds, positions, width, height) {{
        edgeSvg.replaceChildren();
        edgeSvg.setAttribute("viewBox", `0 0 ${{width}} ${{height}}`);
        graph.block_edges.forEach((edge, index) => {{
          if (!visibleIds.has(edge.source) || !visibleIds.has(edge.target)) return;
          const from = positions.get(edge.source);
          const to = positions.get(edge.target);
          if (!from || !to) return;
          const bend = Math.max(45, Math.abs(to.x - from.x) * .42);
          const direction = to.x >= from.x ? 1 : -1;
          const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
          path.id = `relationship-${{index}}`;
          path.dataset.source = edge.source;
          path.dataset.target = edge.target;
          path.classList.add("relationship");
          path.setAttribute(
            "d",
            `M ${{from.x}} ${{from.y}} C ${{from.x + bend * direction}} ${{from.y}}, ` +
            `${{to.x - bend * direction}} ${{to.y}}, ${{to.x}} ${{to.y}}`
          );
          edgeSvg.appendChild(path);
          const label = document.createElementNS("http://www.w3.org/2000/svg", "text");
          label.dataset.source = edge.source;
          label.dataset.target = edge.target;
          label.classList.add("edge-label");
          label.setAttribute("x", String((from.x + to.x) / 2));
          label.setAttribute("y", String((from.y + to.y) / 2 - 7));
          label.textContent = `${{edge.relationship_count}} import${{edge.relationship_count === 1 ? "" : "s"}}`;
          edgeSvg.appendChild(label);
        }});
      }}

      function laneLabel(text, left) {{
        const label = document.createElement("span");
        label.className = "lane-label";
        label.style.left = left;
        label.textContent = text;
        cardsLayer.appendChild(label);
      }}

      function render() {{
        cardsLayer.replaceChildren();
        const blocks = visibleBlocks();
        const width = landscape.clientWidth;
        const height = landscape.clientHeight;
        const positions = positionsFor(blocks, width, height);
        const visibleIds = new Set(blocks.map(block => block.id));
        if (mode === "impact") {{
          laneLabel("Connected context", "17%");
          laneLabel("Changed in this PR", "50%");
          if (blocks.filter(block => !changedStatuses.has(block.status)).length > 1) {{
            laneLabel("Connected context", "83%");
          }}
        }} else {{
          laneLabel("Repository architecture", "50%");
        }}
        blocks.forEach(block => cardsLayer.appendChild(cardFor(block, positions.get(block.id))));
        drawEdges(visibleIds, positions, width, height);
        const initial = blocks.find(block => block.id === activeBlockId)
          || blocks.find(block => changedStatuses.has(block.status))
          || blocks[0];
        if (initial) showDetails(initial);
      }}

      function highlight(blockId) {{
        const neighbors = new Set([blockId]);
        graph.block_edges.forEach(edge => {{
          if (edge.source === blockId) neighbors.add(edge.target);
          if (edge.target === blockId) neighbors.add(edge.source);
        }});
        document.querySelectorAll(".block-card").forEach(card => {{
          card.classList.toggle("active", card.dataset.blockId === blockId);
          card.classList.toggle("dim", !neighbors.has(card.dataset.blockId));
        }});
        document.querySelectorAll(".relationship, .edge-label").forEach(item => {{
          const active = item.dataset.source === blockId || item.dataset.target === blockId;
          item.classList.toggle("active", active);
          item.classList.toggle("dim", !active);
        }});
      }}

      function clearHighlight() {{
        if (activeBlockId) {{ highlight(activeBlockId); return; }}
        document.querySelectorAll(".block-card, .relationship, .edge-label").forEach(item =>
          item.classList.remove("active", "dim")
        );
      }}

      function fileRow(file) {{
        const row = document.createElement("div");
        row.className = "file-row";
        const fileName = file.url ? document.createElement("a") : document.createElement("span");
        fileName.textContent = file.path;
        if (file.url) {{ fileName.href = file.url; fileName.target = "_blank"; fileName.rel = "noopener noreferrer"; }}
        row.appendChild(fileName);
        if (file.status !== "unchanged") {{
          const badge = document.createElement("span");
          badge.className = "badge";
          badge.textContent = file.status;
          badge.style.background = badgeColors[file.status] || "#98a2b3";
          row.appendChild(badge);
        }}
        const metadata = document.createElement("span");
        metadata.className = "file-meta";
        metadata.textContent = [file.language, ...(file.symbols || []).slice(0, 5)].filter(Boolean).join(" · ")
          || "No top-level symbols detected";
        row.appendChild(metadata);
        return row;
      }}

      function showDetails(block) {{
        if (!block) return;
        document.getElementById("note-path").textContent = block.note_path;
        document.querySelector("#details h3").textContent = block.label;
        document.getElementById("detail-status").textContent = `${{block.status}} architecture block`;
        document.getElementById("detail-description").textContent = block.description;
        document.getElementById("markdown-note").textContent = block.note;
        const changedFiles = block.files.filter(file => changedStatuses.has(file.status));
        const changedContainer = document.getElementById("changed-files");
        changedContainer.replaceChildren();
        document.getElementById("changed-title").textContent = changedFiles.length
          ? `CHANGED IN THIS PR (${{changedFiles.length}})` : "CHANGE IN THIS PR";
        if (changedFiles.length) {{
          changedFiles.forEach(file => changedContainer.appendChild(fileRow(file)));
        }} else {{
          const message = document.createElement("p");
          message.className = "hint";
          message.textContent = block.status === "impacted"
            ? "No direct edits; linked to a changed block." : "No files changed directly.";
          changedContainer.appendChild(message);
        }}
        const allFiles = document.getElementById("all-files");
        allFiles.replaceChildren();
        block.files.forEach(file => allFiles.appendChild(fileRow(file)));
      }}

      function setMode(nextMode) {{
        mode = nextMode;
        activeBlockId = null;
        document.getElementById("impact").classList.toggle("active", mode === "impact");
        document.getElementById("all").classList.toggle("active", mode === "all");
        render();
      }}
      document.getElementById("impact").addEventListener("click", () => setMode("impact"));
      document.getElementById("all").addEventListener("click", () => setMode("all"));
      document.getElementById("search").addEventListener("input", event => {{
        const query = event.target.value.trim().toLowerCase();
        if (!query) return;
        const match = graph.blocks.find(block =>
          block.label.toLowerCase().includes(query) || block.path.toLowerCase().includes(query)
          || block.description.toLowerCase().includes(query)
          || block.files.some(file => file.path.toLowerCase().includes(query)
            || (file.symbols || []).some(symbol => symbol.toLowerCase().includes(query)))
        );
        if (!match) return;
        if (!visibleBlocks().some(block => block.id === match.id)) setMode("all");
        activeBlockId = match.id;
        showDetails(match);
        highlight(match.id);
        const card = document.querySelector(`[data-block-id="${{CSS.escape(match.id)}}"]`);
        if (card) {{ card.classList.add("search-pulse"); card.focus(); }}
      }});
      new ResizeObserver(render).observe(landscape);
      render();
    </script>
  </body>
</html>
"""
