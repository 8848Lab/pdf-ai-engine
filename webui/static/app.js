let mutationCount = 0;
let hasDocument = false;
let selectedProvider = "anthropic";

function showError(message) {
  document.getElementById("error").textContent = message || "";
}

function setHasDocument(value) {
  hasDocument = value;
  document.getElementById("download-button").disabled = !value;
  document.getElementById("ai-instruct-button").disabled = !value;
}

function render(state) {
  showError("");
  mutationCount += 1;
  setHasDocument(state.pages.length > 0);
  const pagesDiv = document.getElementById("pages");
  pagesDiv.innerHTML = "";

  for (const page of state.pages) {
    const pageDiv = document.createElement("div");
    pageDiv.className = "page";

    const img = document.createElement("img");
    img.src = `/api/page/${page.index}.png?v=${mutationCount}`;
    pageDiv.appendChild(img);

    const blocksForPage = state.blocks.filter((b) => b.page_index === page.index);
    for (const block of blocksForPage) {
      const blockDiv = document.createElement("div");
      blockDiv.className = "block-controls";

      const textSpan = document.createElement("span");
      textSpan.className = "block-text";
      textSpan.textContent = block.text;
      blockDiv.appendChild(textSpan);

      const redactButton = document.createElement("button");
      redactButton.textContent = "Redact";
      blockDiv.appendChild(redactButton);

      const replaceInput = document.createElement("input");
      replaceInput.type = "text";
      replaceInput.placeholder = "replacement text";
      blockDiv.appendChild(replaceInput);

      const replaceButton = document.createElement("button");
      replaceButton.textContent = "Replace";
      blockDiv.appendChild(replaceButton);

      // Defence in depth against a double-click firing two requests for the
      // same block: the second one would target an id the first already
      // consumed. The backend now rejects that stale id outright, so this is
      // a UX nicety on top of the real fix, not the fix itself.
      const buttonsForBlock = [redactButton, replaceButton];
      redactButton.onclick = () =>
        actGuarded(buttonsForBlock, "/api/redact", { block_id: block.id });
      replaceButton.onclick = () =>
        actGuarded(buttonsForBlock, "/api/replace", {
          block_id: block.id,
          new_text: replaceInput.value,
        });

      pageDiv.appendChild(blockDiv);
    }

    pagesDiv.appendChild(pageDiv);
  }
}

async function actGuarded(buttons, url, body) {
  for (const button of buttons) {
    button.disabled = true;
  }
  try {
    await act(url, body);
  } finally {
    // These buttons belong to the pre-request DOM; a successful act() has
    // already replaced them with a freshly rendered set, so re-enabling them
    // only matters on the failure path -- but it is unconditional so no
    // control flow can leave a live button stuck disabled.
    for (const button of buttons) {
      button.disabled = false;
    }
  }
}

async function act(url, body) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await response.json();
  if (!response.ok) {
    // Re-sync BEFORE showing the error: an engine operation can mutate the
    // document and then fail (replace_text erases the old content before it
    // discovers the new text does not fit), so what is on screen may be
    // stale. Order matters -- render() clears the error message.
    await refreshState();
    showError(data.error || "request failed");
    return;
  }
  render(data);
}

async function refreshState() {
  const response = await fetch("/api/state");
  if (response.ok) {
    render(await response.json());
  }
  // If /api/state itself fails (e.g. no document loaded at all), there's
  // nothing to re-render -- leave whatever's currently shown alone.
}

async function uploadFile(file) {
  const formData = new FormData();
  formData.append("file", file);
  const response = await fetch("/api/upload", { method: "POST", body: formData });
  const data = await response.json();
  if (!response.ok) {
    // A rejected upload leaves any previously-loaded document untouched, so
    // re-sync rather than assuming the session is now empty.
    await refreshState();
    showError(data.error || "upload failed");
    return;
  }
  render(data);
}

document.getElementById("file-input").onchange = () => {
  const fileInput = document.getElementById("file-input");
  if (fileInput.files.length) {
    uploadFile(fileInput.files[0]);
  }
};

document.getElementById("sample-button").onclick = async () => {
  // The bundled sample is a static asset, not a special endpoint -- fetch it
  // as a blob and feed it through the exact same upload path a real file
  // pick would use, so there is only one upload code path to keep correct.
  const response = await fetch("/static/sample-document.pdf");
  const blob = await response.blob();
  await uploadFile(new File([blob], "sample-document.pdf", { type: "application/pdf" }));
};

const dropzone = document.getElementById("upload-dropzone");
["dragenter", "dragover"].forEach((eventName) => {
  dropzone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropzone.dataset.dragover = "true";
  });
});
["dragleave", "drop"].forEach((eventName) => {
  dropzone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropzone.dataset.dragover = "false";
  });
});
dropzone.addEventListener("drop", (event) => {
  const file = event.dataTransfer.files[0];
  if (file) {
    uploadFile(file);
  }
});

document.getElementById("reset-button").onclick = async () => {
  await fetch("/api/reset", { method: "POST" });
  document.getElementById("pages").innerHTML = "";
  setHasDocument(false);
  showError("");
};

document.getElementById("download-button").onclick = () => {
  if (!hasDocument) {
    return;
  }
  window.location.href = "/api/export";
};

document.getElementById("manual-toggle").onclick = () => {
  const showing = document.body.dataset.manualControls === "true";
  document.body.dataset.manualControls = showing ? "false" : "true";
  document.getElementById("manual-toggle").textContent = showing
    ? "Show manual editing controls"
    : "Hide manual editing controls";
};

const PROVIDER_DEFAULTS = {
  anthropic: { baseUrlPlaceholder: "Custom base URL (optional)", modelPlaceholder: "Model (default: claude-opus-5)", apiKeyPlaceholder: "Anthropic API key (or leave blank to use the server's ANTHROPIC_API_KEY)" },
  openai_compatible: { baseUrlPlaceholder: "Base URL (required)", modelPlaceholder: "Model (required)", apiKeyPlaceholder: "API key (optional for servers with no auth)" },
  ollama: { baseUrlPlaceholder: "Base URL (default: http://localhost:11434)", modelPlaceholder: "Model (required -- must already be pulled locally)", apiKeyPlaceholder: "Not used by Ollama" },
};

function applyProviderDefaults() {
  const defaults = PROVIDER_DEFAULTS[selectedProvider];
  document.getElementById("base-url-input").placeholder = defaults.baseUrlPlaceholder;
  document.getElementById("model-input").placeholder = defaults.modelPlaceholder;
  document.getElementById("api-key-input").placeholder = defaults.apiKeyPlaceholder;
}

for (const option of document.querySelectorAll(".provider-option")) {
  option.onclick = () => {
    selectedProvider = option.dataset.provider;
    for (const other of document.querySelectorAll(".provider-option")) {
      other.setAttribute("aria-pressed", other === option ? "true" : "false");
    }
    applyProviderDefaults();
  };
}
applyProviderDefaults();

function showTerminal() {
  const card = document.getElementById("terminal-card");
  card.hidden = false;
  document.getElementById("terminal-title").textContent = "running";
  const body = document.getElementById("terminal-body");
  body.innerHTML = "";

  const line = document.createElement("div");
  line.className = "terminal-line";
  const promptSpan = document.createElement("span");
  promptSpan.className = "prompt";
  promptSpan.textContent = "$";
  const textSpan = document.createElement("span");
  textSpan.textContent = document.getElementById("instruction-input").value;
  const cursor = document.createElement("span");
  cursor.className = "cursor";
  line.append(promptSpan, textSpan, cursor);
  body.appendChild(line);
}

function showTerminalResult(status, text) {
  document.getElementById("terminal-title").textContent = status === "error" ? "failed" : "done";
  const body = document.getElementById("terminal-body");
  const cursor = body.querySelector(".cursor");
  if (cursor) {
    cursor.remove();
  }

  const result = document.createElement("div");
  result.className = "terminal-result";
  result.dataset.status = status;
  const icon = document.createElement("span");
  icon.className = "terminal-result-icon";
  icon.textContent = status === "error" ? "!" : "✓";
  const textDiv = document.createElement("div");
  textDiv.className = "terminal-result-text";
  textDiv.textContent = text;
  result.append(icon, textDiv);
  body.appendChild(result);
}

document.getElementById("ai-instruct-button").onclick = async () => {
  const button = document.getElementById("ai-instruct-button");
  const instruction = document.getElementById("instruction-input").value;
  const apiKey = document.getElementById("api-key-input").value;
  const baseUrl = document.getElementById("base-url-input").value;
  const model = document.getElementById("model-input").value;

  const body = { instruction, provider: selectedProvider };
  if (apiKey) body.api_key = apiKey;
  if (baseUrl) body.base_url = baseUrl;
  if (model) body.model = model;

  button.disabled = true;
  showTerminal();
  try {
    const response = await fetch("/api/ai-instruct", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await response.json();
    if (!response.ok) {
      await refreshState();
      showTerminalResult("error", data.error || "AI instruction failed");
      return;
    }
    showTerminalResult("ok", data.summary);
    render(data);
  } catch (err) {
    // A non-JSON error body (e.g. a bare 500) makes `await response.json()`
    // above throw -- without this catch that failure was completely silent,
    // the button just re-enabled with no indication anything went wrong.
    showTerminalResult("error", err.message || "AI instruction failed");
  } finally {
    button.disabled = false;
  }
};
