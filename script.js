(function () {
  const list = document.getElementById("games-list");
  const search = document.getElementById("search");
  const genresBox = document.getElementById("genres");
  const freeOnly = document.getElementById("free-only");
  const count = document.getElementById("games-count");
  const empty = document.getElementById("games-empty");
  const randomButton = document.getElementById("random-game");

  const ALL_GENRES = "Все";
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  let activeGenre = ALL_GENRES;
  let lastPicked = null;

  // Буквы на обложке: "Team Fortress 2" -> "TF", "Counter-Strike 2" -> "CS"
  function initials(title) {
    return title
      .trim()
      .split(/[\s-]+/)
      .slice(0, 2)
      .map((word) => word[0])
      .join("")
      .toUpperCase();
  }

  function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text) node.textContent = text;
    return node;
  }

  function createCard(game) {
    const card = element("li", "game-card");
    card.style.setProperty("--card-color", game.color);

    const cover = element("div", "game-cover", initials(game.title));
    cover.setAttribute("aria-hidden", "true");

    const body = element("div", "game-body");
    const meta = element("p", "game-meta", game.genre + " · " + game.platforms.join(", "));

    const title = element("h3", "game-title");
    const link = element("a", "", game.title);
    link.href = game.url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    title.append(link);

    const description = element("p", "game-desc", game.description);

    const footer = element("div", "game-footer");
    const price = element(
      "span",
      game.free ? "badge badge-free" : "badge",
      game.free ? "Бесплатно" : "Платная"
    );
    const go = element("span", "game-go", "Играть →");
    go.setAttribute("aria-hidden", "true");
    footer.append(price, go);

    body.append(meta, title, description, footer);
    card.append(cover, body);
    return card;
  }

  const cards = GAMES.map((game) => ({ game, node: createCard(game) }));
  list.append(...cards.map((card) => card.node));

  function matches(game, query) {
    const genreOk = activeGenre === ALL_GENRES || game.genre === activeGenre;
    const priceOk = !freeOnly.checked || game.free;
    const text = (game.title + " " + game.genre + " " + game.description).toLowerCase();
    return genreOk && priceOk && text.includes(query);
  }

  function render() {
    const query = search.value.trim().toLowerCase();
    let shown = 0;
    cards.forEach(({ game, node }) => {
      const visible = matches(game, query);
      node.hidden = !visible;
      if (visible) shown++;
    });
    empty.hidden = shown > 0;
    count.textContent = "Показано: " + shown + " из " + cards.length;
  }

  function setGenre(genre) {
    activeGenre = genre;
    genresBox.querySelectorAll(".chip").forEach((chip) => {
      chip.setAttribute("aria-pressed", String(chip.textContent === genre));
    });
    render();
  }

  const genres = [ALL_GENRES, ...new Set(GAMES.map((game) => game.genre))];
  genres.forEach((genre) => {
    const chip = element("button", "chip", genre);
    chip.type = "button";
    chip.setAttribute("aria-pressed", String(genre === activeGenre));
    chip.addEventListener("click", () => setGenre(genre));
    genresBox.append(chip);
  });

  function resetFilters() {
    search.value = "";
    freeOnly.checked = false;
    setGenre(ALL_GENRES);
  }

  // Выбирает случайную игру среди показанных (или среди всех, если фильтры ничего не нашли)
  function pickRandom() {
    let pool = cards.filter((card) => !card.node.hidden);
    if (pool.length === 0) {
      resetFilters();
      pool = cards;
    }
    if (pool.length > 1) pool = pool.filter((card) => card !== lastPicked);

    const picked = pool[Math.floor(Math.random() * pool.length)];
    lastPicked = picked;

    cards.forEach((card) => card.node.classList.remove("is-picked"));
    // Перезапуск анимации, если снова выпала та же карточка
    void picked.node.offsetWidth;
    picked.node.classList.add("is-picked");
    picked.node.scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth", block: "center" });
    picked.node.querySelector("a").focus({ preventScroll: true });
  }

  search.addEventListener("input", render);
  freeOnly.addEventListener("change", render);
  randomButton.addEventListener("click", pickRandom);

  document.getElementById("year").textContent = new Date().getFullYear();
  render();
})();
