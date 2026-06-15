// Translate the panels on the active tab via the local backend.
//
// Flow: tag + collect the big <img>s on the page, fetch each image's bytes
// (the extension's host_permissions let it read cross-origin images without the
// page's CORS getting in the way), POST to the backend's /translate-image, then
// swap the panel's src for the returned translated image.

const goBtn = document.getElementById("go");
const statusEl = document.getElementById("status");

goBtn.addEventListener("click", run);

async function run() {
  const backend = (document.getElementById("backend").value || "http://localhost:8000").replace(/\/$/, "");
  goBtn.disabled = true;
  statusEl.textContent = "Scanning page...";

  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });

  // 1. find + tag panel images in the page.
  const [{ result: panels }] = await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    func: collectPanels,
  });

  if (!panels || !panels.length) {
    statusEl.textContent = "No panel images found on this page.";
    goBtn.disabled = false;
    return;
  }

  let done = 0, ok = 0;
  for (const p of panels) {
    statusEl.textContent = `Translating ${done + 1}/${panels.length}...`;
    try {
      const imgResp = await fetch(p.src);
      const blob = await imgResp.blob();

      const fd = new FormData();
      fd.append("file", blob, "panel.jpg");
      const tr = await fetch(backend + "/translate-image", { method: "POST", body: fd });
      const data = await tr.json();

      if (data.rendered_image) {
        await chrome.scripting.executeScript({
          target: { tabId: tab.id },
          func: replacePanel,
          args: [p.id, data.rendered_image],
        });
        ok++;
      }
    } catch (e) {
      console.error("panel failed:", p.src, e);
    }
    done++;
  }

  statusEl.textContent = `Done: ${ok}/${panels.length} panels translated.`;
  goBtn.disabled = false;
}

// --- injected into the page (must be self-contained) ---

function collectPanels() {
  const out = [];
  let i = 0;
  for (const img of document.images) {
    if (img.naturalWidth >= 400 && img.naturalHeight >= 400) {
      const id = "mt-" + i++;
      img.setAttribute("data-mt-id", id);
      out.push({ id, src: img.currentSrc || img.src });
    }
  }
  return out;
}

function replacePanel(id, dataUrl) {
  const img = document.querySelector('[data-mt-id="' + id + '"]');
  if (img) {
    img.removeAttribute("srcset");
    img.src = dataUrl;
  }
}
