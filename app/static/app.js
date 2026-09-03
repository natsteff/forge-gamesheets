const previewToggle = document.querySelector("#preview-toggle");

const siteHeader = document.querySelector(".site-header");
const menuToggle = document.querySelector("#menu-toggle");
const primaryNavigation = document.querySelector("#primary-navigation");

if (siteHeader && menuToggle && primaryNavigation) {
  const mobileNavigation = window.matchMedia("(max-width: 850px)");
  siteHeader.classList.add("nav-enhanced");
  menuToggle.hidden = false;

  const closeMenu = () => {
    siteHeader.classList.remove("menu-open");
    menuToggle.setAttribute("aria-expanded", "false");
  };

  menuToggle.addEventListener("click", () => {
    const menuIsOpen = siteHeader.classList.toggle("menu-open");
    menuToggle.setAttribute("aria-expanded", String(menuIsOpen));
  });

  primaryNavigation.addEventListener("click", (event) => {
    if (event.target.closest("a")) {
      closeMenu();
    }
  });

  document.addEventListener("click", (event) => {
    if (siteHeader.classList.contains("menu-open") && !siteHeader.contains(event.target)) {
      closeMenu();
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && siteHeader.classList.contains("menu-open")) {
      closeMenu();
      menuToggle.focus();
    }
  });

  mobileNavigation.addEventListener("change", (event) => {
    if (!event.matches) {
      closeMenu();
    }
  });
}

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
