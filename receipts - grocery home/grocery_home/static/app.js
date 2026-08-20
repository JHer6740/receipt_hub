(() => {
  "use strict";

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

  function formatBytes(bytes) {
    if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  function initDismissButtons() {
    $$("[data-dismiss]").forEach((button) => {
      button.addEventListener("click", () => {
        const parent = button.closest(".flash");
        if (parent) parent.remove();
      });
    });
  }

  function initUpload() {
    const form = $("#receipt-upload-form");
    if (!form) return;
    const input = $("#receipt-files", form);
    const output = $("#selected-files", form);
    const submit = $("#upload-submit", form);
    const dropzone = $(".receipt-dropzone", form);

    const renderFiles = () => {
      output.replaceChildren();
      const files = Array.from(input.files || []);
      files.forEach((file) => {
        const row = document.createElement("div");
        row.className = "selected-file";
        row.setAttribute("role", "listitem");
        const icon = document.createElementNS("http://www.w3.org/2000/svg", "svg");
        icon.setAttribute("viewBox", "0 0 24 24");
        icon.setAttribute("aria-hidden", "true");
        icon.innerHTML = '<path d="M6 3h8l4 4v14H6z"/><path d="M14 3v5h5"/>';
        const name = document.createElement("span");
        name.textContent = file.name;
        const size = document.createElement("small");
        size.textContent = formatBytes(file.size);
        row.append(icon, name, size);
        output.append(row);
      });
      submit.disabled = files.length === 0;
      submit.textContent = files.length > 1 ? `Read ${files.length} receipt pages` : "Start reading receipt";
    };

    input.addEventListener("change", renderFiles);
    ["dragenter", "dragover"].forEach((eventName) => {
      dropzone.addEventListener(eventName, (event) => {
        event.preventDefault();
        dropzone.classList.add("is-dragging");
      });
    });
    dropzone.addEventListener("dragleave", () => dropzone.classList.remove("is-dragging"));
    dropzone.addEventListener("drop", (event) => {
      event.preventDefault();
      dropzone.classList.remove("is-dragging");
      if (!event.dataTransfer?.files?.length) return;
      try {
        input.files = event.dataTransfer.files;
        input.dispatchEvent(new Event("change", { bubbles: true }));
      } catch (_error) {
        input.click();
      }
    });
    form.addEventListener("submit", () => {
      form.setAttribute("aria-busy", "true");
      submit.disabled = true;
      submit.textContent = "Sending to Grocery Home…";
    });
  }

  function initJobPolling() {
    const page = $("[data-job-id]");
    if (!page) return;
    const endpoint = page.dataset.jobUrl;
    const heading = $("[data-job-heading]", page);
    const message = $("[data-job-message]", page);
    const bar = $("[data-job-progress]", page);
    const progress = $(".job-progress", page);
    const destination = $("[data-job-destination]", page);
    let stopped = false;

    const descriptions = {
      queued: ["In the reading queue.", "Grocery Home will start this receipt shortly."],
      extracting: ["Reading your receipt.", "Finding the shop, totals and line items on this computer."],
      needs_review: ["Ready for a quick check.", "Review the fields before they join household totals."],
      complete: ["Filed in the ledger.", "The receipt and household trends are up to date."],
      duplicate: ["Already in the ledger.", "This upload is kept for the audit trail but is not counted twice."],
      failed: ["This one needs help.", "Grocery Home could not read the receipt. Open it to enter the details manually."],
    };

    async function poll() {
      if (stopped) return;
      try {
        const response = await fetch(endpoint, { headers: { Accept: "application/json" } });
        if (!response.ok) throw new Error("status unavailable");
        const data = await response.json();
        const copy = descriptions[data.status] || descriptions.extracting;
        heading.textContent = data.heading || copy[0];
        message.textContent = data.message || copy[1];
        const value = Number.isFinite(data.progress) ? data.progress : 0;
        const clampedValue = Math.min(100, Math.max(0, value));
        bar.style.width = `${clampedValue}%`;
        progress.setAttribute("aria-valuenow", String(clampedValue));

        if (["needs_review", "complete", "duplicate", "failed"].includes(data.status)) {
          stopped = true;
          page.setAttribute("aria-busy", "false");
          if (data.destination) {
            destination.href = data.destination;
            destination.textContent = data.status === "complete" ? "View receipt" : "Open receipt";
            destination.classList.remove("is-hidden");
          }
          return;
        }
      } catch (_error) {
        message.textContent = "The status check paused. Grocery Home is still working; this page will try again.";
      }
      window.setTimeout(poll, 1400);
    }
    window.setTimeout(poll, 600);
  }

  function parseMoney(value) {
    const parsed = Number.parseFloat(String(value || "").replace(/[$,\s]/g, ""));
    return Number.isFinite(parsed) ? parsed : 0;
  }

  function initReview() {
    const form = $("[data-review-form]");
    if (!form) return;
    const container = $("[data-review-items]", form);
    const template = $("#review-item-template");
    const addButton = $("[data-add-item]", form);
    const balance = $("[data-item-balance]", form);
    const totalInput = $("[data-receipt-total]", form);
    const emptyState = $("[data-items-empty]", form);

    const renumber = () => {
      const items = $$("[data-review-item]", container);
      items.forEach((item, index) => {
        $(".item-number", item).textContent = String(index + 1).padStart(2, "0");
        const description = $('input[name="item_description"]', item);
        const remove = $("[data-remove-item]", item);
        remove.setAttribute("aria-label", `Remove ${description.value || `item ${index + 1}`}`);
      });
      if (emptyState) emptyState.hidden = items.length > 0;
    };

    const updateBalance = () => {
      const itemTotal = $$("[data-item-total]", container)
        .reduce((sum, input) => sum + parseMoney(input.value), 0);
      const receiptTotal = parseMoney(totalInput.value);
      $("strong", balance).textContent = new Intl.NumberFormat("en-AU", {
        style: "currency", currency: "AUD",
      }).format(itemTotal);
      const difference = Math.abs(itemTotal - receiptTotal);
      const note = $("small", balance);
      if (difference > 0.05) {
        balance.classList.add("is-mismatched");
        const direction = itemTotal < receiptTotal ? "under" : "over";
        note.textContent = `$${difference.toFixed(2)} ${direction} receipt total`;
      } else {
        balance.classList.remove("is-mismatched");
        note.textContent = "Balances with receipt total";
      }
    };

    const bindItem = (item) => {
      $("[data-remove-item]", item).addEventListener("click", () => {
        const items = $$("[data-review-item]", container);
        const index = items.indexOf(item);
        item.remove();
        renumber();
        updateBalance();
        const remaining = $$("[data-review-item]", container);
        const focusTarget = remaining[Math.min(index, remaining.length - 1)];
        if (focusTarget) $('input[name="item_description"]', focusTarget)?.focus();
        else addButton.focus();
      });
      $$("input", item).forEach((input) => input.addEventListener("input", () => {
        if (input.name === "item_description") renumber();
        if (input.matches("[data-item-total]")) updateBalance();
      }));
    };

    $$("[data-review-item]", container).forEach(bindItem);
    addButton.addEventListener("click", () => {
      const item = template.content.firstElementChild.cloneNode(true);
      container.append(item);
      bindItem(item);
      renumber();
      updateBalance();
      $('input[name="item_description"]', item).focus();
    });
    totalInput.addEventListener("input", updateBalance);
    renumber();
    updateBalance();
  }

  function safePoints(element) {
    try {
      const value = JSON.parse(element.dataset.points || "[]");
      return Array.isArray(value) ? value : [];
    } catch (_error) {
      return [];
    }
  }

  function drawSpendChart(container) {
    if (!window.d3) return;
    const points = safePoints(container);
    const svg = window.d3.select($("svg", container));
    svg.selectAll("*").remove();
    if (!points.length) return;

    const width = Math.max(280, container.clientWidth);
    const height = container.clientHeight || 280;
    const margin = { top: 16, right: 10, bottom: 28, left: 44 };
    const innerWidth = width - margin.left - margin.right;
    const innerHeight = height - margin.top - margin.bottom;
    const parsed = points.map((point) => ({
      ...point,
      dateValue: new Date(`${point.date}T00:00:00`),
      amountValue: Number(point.amount) || 0,
    }));

    svg.attr("viewBox", `0 0 ${width} ${height}`);
    const root = svg.append("g").attr("transform", `translate(${margin.left},${margin.top})`);
    const x = window.d3.scaleTime()
      .domain(window.d3.extent(parsed, (d) => d.dateValue))
      .range([0, innerWidth]);
    const yMax = window.d3.max(parsed, (d) => d.amountValue) || 1;
    const y = window.d3.scaleLinear().domain([0, yMax * 1.12]).nice().range([innerHeight, 0]);

    const yTicks = y.ticks(4);
    root.selectAll(".chart-rule").data(yTicks).join("line")
      .attr("class", "chart-rule")
      .attr("x1", 0).attr("x2", innerWidth)
      .attr("y1", (d) => y(d)).attr("y2", (d) => y(d));

    const area = window.d3.area()
      .x((d) => x(d.dateValue))
      .y0(innerHeight)
      .y1((d) => y(d.amountValue))
      .curve(window.d3.curveMonotoneX);
    const line = window.d3.line()
      .x((d) => x(d.dateValue))
      .y((d) => y(d.amountValue))
      .curve(window.d3.curveMonotoneX);
    root.append("path").datum(parsed).attr("class", "spend-area").attr("d", area);
    root.append("path").datum(parsed).attr("class", "spend-line").attr("d", line);
    root.selectAll(".spend-dot").data(parsed).join("circle")
      .attr("class", "spend-dot")
      .attr("cx", (d) => x(d.dateValue)).attr("cy", (d) => y(d.amountValue)).attr("r", 3.2)
      .append("title").text((d) => `${d.label}: ${d.amount_label}`);

    const xAxis = window.d3.axisBottom(x)
      .ticks(Math.min(5, parsed.length))
      .tickSize(0)
      .tickPadding(10)
      .tickFormat(window.d3.timeFormat("%b"));
    const yAxis = window.d3.axisLeft(y)
      .ticks(4)
      .tickSize(0)
      .tickPadding(8)
      .tickFormat((value) => `$${window.d3.format(".2~s")(value)}`);
    root.append("g").attr("class", "chart-axis")
      .attr("transform", `translate(0,${innerHeight})`).call(xAxis).call((g) => g.select(".domain").remove());
    root.append("g").attr("class", "chart-axis").call(yAxis).call((g) => g.select(".domain").remove());
  }

  function drawCategoryChart(container) {
    if (!window.d3) return;
    const points = safePoints(container).slice(0, 7);
    const svg = window.d3.select($("svg", container));
    svg.selectAll("*").remove();
    if (!points.length) return;
    const width = Math.max(260, container.clientWidth);
    const height = container.clientHeight || 280;
    const margin = { top: 8, right: 54, bottom: 8, left: 112 };
    const innerWidth = width - margin.left - margin.right;
    const innerHeight = height - margin.top - margin.bottom;
    const values = points.map((point) => ({ ...point, amountValue: Number(point.amount) || 0 }));
    svg.attr("viewBox", `0 0 ${width} ${height}`);
    const root = svg.append("g").attr("transform", `translate(${margin.left},${margin.top})`);
    const y = window.d3.scaleBand().domain(values.map((d) => d.name)).range([0, innerHeight]).padding(0.52);
    const x = window.d3.scaleLinear()
      .domain([0, window.d3.max(values, (d) => d.amountValue) || 1])
      .range([0, innerWidth]);
    root.selectAll(".category-bar").data(values).join("rect")
      .attr("class", "category-bar")
      .attr("x", 0).attr("y", (d) => y(d.name))
      .attr("height", y.bandwidth()).attr("width", (d) => x(d.amountValue)).attr("rx", 2)
      .append("title").text((d) => `${d.name}: ${d.amount_label}`);
    root.selectAll(".category-label").data(values).join("text")
      .attr("class", "category-label")
      .attr("x", -10).attr("y", (d) => y(d.name) + y.bandwidth() / 2 + 4)
      .attr("text-anchor", "end")
      .text((d) => d.name.length > 16 ? `${d.name.slice(0, 15)}…` : d.name);
    root.selectAll(".category-value").data(values).join("text")
      .attr("class", "category-value")
      .attr("x", (d) => Math.min(innerWidth + 8, x(d.amountValue) + 8))
      .attr("y", (d) => y(d.name) + y.bandwidth() / 2 + 4)
      .text((d) => d.amount_label);
  }

  function initCharts() {
    const spend = $("[data-spend-chart]");
    const categories = $("[data-category-chart]");
    if (!spend && !categories) return;
    const render = () => {
      if (spend) drawSpendChart(spend);
      if (categories) drawCategoryChart(categories);
    };
    render();
    if ("ResizeObserver" in window) {
      const observer = new ResizeObserver(() => window.requestAnimationFrame(render));
      if (spend) observer.observe(spend);
      if (categories) observer.observe(categories);
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    initDismissButtons();
    initUpload();
    initJobPolling();
    initReview();
    initCharts();
  });
})();
