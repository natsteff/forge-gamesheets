const previewToggle = document.querySelector("#preview-toggle");
const bulkForm = document.querySelector("#bulk-categories");
if (bulkForm) {
  const boxes = [...bulkForm.querySelectorAll('input[name="game_ids"]')];
  const select = document.querySelector("#select-games");
  const updateCount = () => {
    document.querySelector("#selected-count").textContent = `${boxes.filter(box => box.checked).length} selected`;
    select.textContent = boxes.length && boxes.every(box => box.checked) ? "Deselect all shown" : "Select all shown";
  };
  select.hidden = false;
  select.addEventListener("click", () => {
    const checked = !boxes.every(box => box.checked);
    boxes.forEach(box => { box.checked = checked; });
    updateCount();
  });
  bulkForm.addEventListener("change", updateCount);
  updateCount();
}

const siteHeader = document.querySelector(".site-header");
const menuToggle = document.querySelector("#menu-toggle");
const primaryNavigation = document.querySelector("#primary-navigation");

if (siteHeader && menuToggle && primaryNavigation) {
  const mobileNavigation = window.matchMedia("(max-width: 850px)");
  siteHeader.classList.add("nav-enhanced");
  menuToggle.hidden = false;
  const groups = [...primaryNavigation.querySelectorAll(".nav-group")];
  const closeGroups = () => groups.forEach((group) => {
    group.classList.remove("group-open");
    group.querySelector("button").setAttribute("aria-expanded", "false");
  });
  groups.forEach((group) => {
    const button = group.querySelector("button");
    button.hidden = false;
    button.addEventListener("click", () => {
      const open = !group.classList.contains("group-open");
      closeGroups();
      group.classList.toggle("group-open", open);
      button.setAttribute("aria-expanded", String(open));
    });
    group.addEventListener("focusout", (event) => {
      if (!group.contains(event.relatedTarget)) {
        group.classList.remove("group-open");
        button.setAttribute("aria-expanded", "false");
      }
    });
  });
  document.addEventListener("click", (event) => {
    if (!primaryNavigation.contains(event.target)) closeGroups();
  });
  primaryNavigation.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !mobileNavigation.matches) {
      const open = primaryNavigation.querySelector(".group-open button");
      closeGroups();
      if (open) { open.focus(); event.stopPropagation(); }
    }
  });

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
    closeGroups();
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
