let mutationCount = 0;

function showError(message) {
  document.getElementById("error").textContent = message || "";
}

function render(state) {
  showError("");
  mutationCount += 1;
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
      blockDiv.className = "block";

      const textSpan = document.createElement("span");
      textSpan.className = "block-text";
      textSpan.textContent = block.text;
      blockDiv.appendChild(textSpan);

      const redactButton = document.createElement("button");
      redactButton.textContent = "Redact";
      redactButton.onclick = () => act("/api/redact", { block_id: block.id });
      blockDiv.appendChild(redactButton);

      const replaceInput = document.createElement("input");
      replaceInput.type = "text";
      replaceInput.placeholder = "replacement text";
      blockDiv.appendChild(replaceInput);

      const replaceButton = document.createElement("button");
      replaceButton.textContent = "Replace";
      replaceButton.onclick = () =>
        act("/api/replace", { block_id: block.id, new_text: replaceInput.value });
      blockDiv.appendChild(replaceButton);

      pageDiv.appendChild(blockDiv);
    }

    pagesDiv.appendChild(pageDiv);
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

document.getElementById("upload-button").onclick = async () => {
  const fileInput = document.getElementById("file-input");
  if (!fileInput.files.length) {
    showError("choose a PDF file first");
    return;
  }
  const formData = new FormData();
  formData.append("file", fileInput.files[0]);
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
};

document.getElementById("reset-button").onclick = async () => {
  await fetch("/api/reset", { method: "POST" });
  document.getElementById("pages").innerHTML = "";
  showError("");
};
