const previewToggle = document.querySelector("#preview-toggle");

if (previewToggle) {
  const storageKey = "forge-gamesheets-show-previews";
  const storedPreference = window.localStorage.getItem(storageKey);
  let showPreviews = storedPreference !== "false";

  const applyPreviewPreference = () => {
    document.body.classList.toggle("previews-hidden", !showPreviews);
    previewToggle.textContent = showPreviews ? "Hide previews" : "Show previews";
    previewToggle.setAttribute("aria-pressed", String(showPreviews));
  };

  previewToggle.addEventListener("click", () => {
    showPreviews = !showPreviews;
    window.localStorage.setItem(storageKey, String(showPreviews));
    applyPreviewPreference();
  });

  applyPreviewPreference();
}

for (const preview of document.querySelectorAll(".resource-preview img")) {
  preview.addEventListener("error", () => {
    preview.hidden = true;
    const row = preview.closest(".resource-row");
    const status = row?.querySelector(".preview-status");
    if (status) {
      status.hidden = false;
    }
  });
}

for (const form of document.querySelectorAll("form[data-confirm]")) {
  form.addEventListener("submit", (event) => {
    if (!window.confirm(form.dataset.confirm)) {
      event.preventDefault();
    }
  });
}
