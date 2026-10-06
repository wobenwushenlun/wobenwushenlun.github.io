(() => {
  const header = document.querySelector("[data-header]");
  const menu = document.querySelector("[data-menu]");
  const toggle = document.querySelector("[data-menu-toggle]");

  const updateHeader = () => {
    if (header) header.classList.toggle("is-scrolled", window.scrollY > 12);
  };

  updateHeader();
  window.addEventListener("scroll", updateHeader, { passive: true });

  if (toggle && menu) {
    toggle.addEventListener("click", () => {
      const isOpen = toggle.getAttribute("aria-expanded") === "true";
      toggle.setAttribute("aria-expanded", String(!isOpen));
      menu.classList.toggle("is-open", !isOpen);
    });

    menu.querySelectorAll("a").forEach((link) => {
      link.addEventListener("click", () => {
        toggle.setAttribute("aria-expanded", "false");
        menu.classList.remove("is-open");
      });
    });
  }

  document.querySelectorAll(".prose table").forEach((table) => {
    const scroll = document.createElement("div");
    scroll.className = "table-scroll";
    scroll.tabIndex = 0;
    scroll.setAttribute("role", "region");
    const headings = Array.from(document.querySelectorAll(".prose h2, .prose h3"));
    const heading = headings.filter((item) =>
      item.compareDocumentPosition(table) & Node.DOCUMENT_POSITION_FOLLOWING
    ).pop();
    scroll.setAttribute("aria-label", `${heading?.textContent || "文章"}：数据表`);
    table.before(scroll);
    scroll.append(table);
  });

  const directory = document.querySelector("[data-reading-directory]");
  if (directory) {
    const summary = directory.querySelector("summary");
    const chapterMenu = directory.querySelector(".reading-menu");
    const fitChapterMenu = () => {
      if (!directory.open) return;
      if (window.innerHeight - chapterMenu.getBoundingClientRect().top < 160) {
        directory.scrollIntoView({ block: "start", behavior: "instant" });
      }
      const room = Math.max(120, window.innerHeight - chapterMenu.getBoundingClientRect().top - 16);
      chapterMenu.style.setProperty("--reading-menu-room", `${room}px`);
    };
    directory.addEventListener("toggle", () => {
      if (!directory.open) return;
      fitChapterMenu();
      const current = chapterMenu.querySelector('[aria-current="page"]');
      if (current) {
        chapterMenu.scrollTop += current.getBoundingClientRect().top
          - chapterMenu.getBoundingClientRect().top - chapterMenu.clientHeight / 2
          + current.clientHeight / 2;
      }
    });
    document.addEventListener("pointerdown", (event) => {
      if (!directory.contains(event.target)) directory.open = false;
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && directory.open) {
        event.preventDefault();
        directory.open = false;
        summary.focus({ preventScroll: true });
      }
    });
    directory.addEventListener("focusout", (event) => {
      if (event.relatedTarget && !directory.contains(event.relatedTarget)) directory.open = false;
    });
    window.addEventListener("resize", fitChapterMenu);
  }

  const animated = document.querySelectorAll(".note-row, .latest-card, .topic-pill, .work-card");
  if (!("IntersectionObserver" in window)) {
    animated.forEach((item) => item.classList.add("is-visible"));
    return;
  }

  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (!entry.isIntersecting) return;
      entry.target.classList.add("is-visible");
      observer.unobserve(entry.target);
    });
  }, { threshold: 0.12, rootMargin: "0px 0px -30px" });

  animated.forEach((item, index) => {
    item.style.transitionDelay = `${Math.min(index * 45, 180)}ms`;
    observer.observe(item);
  });
})();
