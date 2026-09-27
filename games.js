// Список игр на сайте.
//
// Чтобы добавить игру, скопируй любой блок { ... } целиком и поменяй поля:
//   title       — название игры
//   genre       — жанр (из жанров автоматически собираются кнопки-фильтры)
//   platforms   — где можно поиграть
//   free        — true, если игра бесплатная, иначе false
//   description — пара слов об игре
//   url         — ссылка на официальный сайт игры
//   color       — цвет обложки (любой цвет CSS, например "#ff0000")
//
// Не забудь запятую между блоками!
const GAMES = [
  {
    title: "Dota 2",
    genre: "MOBA",
    platforms: ["ПК"],
    free: true,
    description: "Командные бои 5 на 5: выбери героя из сотни и снеси вражеский трон.",
    url: "https://www.dota2.com/",
    color: "#b3321f",
  },
  {
    title: "Counter-Strike 2",
    genre: "Шутер",
    platforms: ["ПК"],
    free: true,
    description: "Легендарный командный шутер: террористы против спецназа.",
    url: "https://www.counter-strike.net/",
    color: "#c7812a",
  },
  {
    title: "Team Fortress 2",
    genre: "Шутер",
    platforms: ["ПК"],
    free: true,
    description: "Весёлый мультяшный шутер с девятью классами — от снайпера до шпиона.",
    url: "https://www.teamfortress.com/",
    color: "#9d3a2a",
  },
  {
    title: "Warframe",
    genre: "Шутер",
    platforms: ["ПК", "Консоли", "Телефон"],
    free: true,
    description: "Космические ниндзя, паркур и кооперативные миссии с друзьями.",
    url: "https://www.warframe.com/",
    color: "#3d5a80",
  },
  {
    title: "Minecraft",
    genre: "Песочница",
    platforms: ["ПК", "Консоли", "Телефон"],
    free: false,
    description: "Строй, копай и выживай в бесконечном мире из кубиков.",
    url: "https://www.minecraft.net/",
    color: "#4f7a28",
  },
  {
    title: "Terraria",
    genre: "Песочница",
    platforms: ["ПК", "Консоли", "Телефон"],
    free: false,
    description: "2D-приключение: копай вглубь, крафти оружие и побеждай боссов.",
    url: "https://terraria.org/",
    color: "#2f7d6d",
  },
  {
    title: "Genshin Impact",
    genre: "RPG",
    platforms: ["ПК", "Консоли", "Телефон"],
    free: true,
    description: "Огромный открытый мир, стихийная магия и отряд из любимых героев.",
    url: "https://genshin.hoyoverse.com/",
    color: "#4a6fa5",
  },
  {
    title: "Stardew Valley",
    genre: "Симулятор",
    platforms: ["ПК", "Консоли", "Телефон"],
    free: false,
    description: "Уютная ферма: выращивай урожай, рыбачь и заводи друзей в деревне.",
    url: "https://www.stardewvalley.net/",
    color: "#5f8f3a",
  },
  {
    title: "Among Us",
    genre: "Для компании",
    platforms: ["ПК", "Консоли", "Телефон"],
    free: false,
    description: "Найди предателя среди экипажа, пока он не нашёл тебя. На телефоне бесплатно.",
    url: "https://www.innersloth.com/games/among-us/",
    color: "#b5313a",
  },
  {
    title: "Hollow Knight",
    genre: "Платформер",
    platforms: ["ПК", "Консоли"],
    free: false,
    description: "Мрачное и красивое королевство насекомых с крутыми боссами.",
    url: "https://www.hollowknight.com/",
    color: "#3b4466",
  },
  {
    title: "Geometry Dash",
    genre: "Платформер",
    platforms: ["ПК", "Телефон"],
    free: false,
    description: "Прыгай в ритм музыки и проходи уровни, от которых горит.",
    url: "https://store.steampowered.com/app/322170/Geometry_Dash/",
    color: "#2a7ab8",
  },
  {
    title: "Brawl Stars",
    genre: "Экшен",
    platforms: ["Телефон"],
    free: true,
    description: "Быстрые бои 3 на 3 и королевская битва прямо на телефоне.",
    url: "https://supercell.com/en/games/brawlstars/",
    color: "#c9a227",
  },
];
