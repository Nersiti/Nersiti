import { tgUser } from "./tg";

const ru = {
  "app.title": "Битва за Мир",
  "app.loading": "Загрузка…",
  "app.error": "Не удалось загрузить игру",
  "app.retry": "Повторить",
  "app.openInTelegram": "Открой игру через Telegram-бота",
  "hello": "Привет, {name}!",

  "onb.country.title": "Откуда ты?",
  "onb.country.subtitle": "Страна, за которую ты будешь играть в рейтинге стран",
  "onb.country.search": "Поиск страны",
  "onb.city.title": "Твой город",
  "onb.city.subtitle": "Здесь твой дом: воевать здесь можно сразу",
  "onb.city.search": "Начни вводить название города",
  "onb.city.empty": "Ничего не найдено. Попробуй написать по-английски или выбери ближайший крупный город",
  "onb.city.hint": "Введи хотя бы 2 буквы",
  "onb.back": "Назад",
  "onb.next": "Дальше",
  "onb.start": "В бой!",
  "onb.tut1.title": "Зарабатывай",
  "onb.tut1.text": "Тапай по эмблеме и покупай улучшения: они приносят монеты каждый час, даже когда ты не в игре.",
  "onb.tut2.title": "Захватывай",
  "onb.tut2.text": "Карта мира поделена на секторы. Вкладывай монеты, чтобы захватывать и укреплять секторы своего города.",
  "onb.tut3.title": "Побеждай вместе",
  "onb.tut3.text": "Вступи в клан своего канала или чата. Каждый час клан получает очки за удержанные секторы. Сезон длится 30 дней.",
  "population": "{n} жителей",
} as const;

export type I18nKey = keyof typeof ru;

const en: Record<I18nKey, string> = {
  "app.title": "World Battle",
  "app.loading": "Loading…",
  "app.error": "Failed to load the game",
  "app.retry": "Retry",
  "app.openInTelegram": "Open the game through the Telegram bot",
  "hello": "Hello, {name}!",

  "onb.country.title": "Where are you from?",
  "onb.country.subtitle": "The country you'll represent in the country ranking",
  "onb.country.search": "Search country",
  "onb.city.title": "Your city",
  "onb.city.subtitle": "This is your home: you can fight here right away",
  "onb.city.search": "Start typing your city",
  "onb.city.empty": "Nothing found. Try another spelling or pick the nearest big city",
  "onb.city.hint": "Type at least 2 letters",
  "onb.back": "Back",
  "onb.next": "Next",
  "onb.start": "Let's go!",
  "onb.tut1.title": "Earn",
  "onb.tut1.text": "Tap the emblem and buy upgrades: they bring coins every hour, even while you're away.",
  "onb.tut2.title": "Capture",
  "onb.tut2.text": "The world map is split into sectors. Invest coins to capture and fortify sectors of your city.",
  "onb.tut3.title": "Win together",
  "onb.tut3.text": "Join your channel's or chat's clan. Every hour the clan scores points for held sectors. A season lasts 30 days.",
  "population": "{n} people",
};

const RU_LANGS = new Set(["ru", "uk", "be", "kk", "uz", "ky", "tg", "hy", "az", "ka", "tk"]);

export function detectLang(code?: string): "ru" | "en" {
  const c = (code ?? tgUser()?.language_code ?? navigator.language ?? "en").split("-")[0].toLowerCase();
  return RU_LANGS.has(c) ? "ru" : "en";
}

let lang: "ru" | "en" = detectLang();

export function setLang(value: "ru" | "en"): void {
  lang = value;
  document.documentElement.lang = value;
}

export function getLang(): "ru" | "en" {
  return lang;
}

export function t(key: I18nKey, params?: Record<string, string | number>): string {
  let text: string = (lang === "ru" ? ru : en)[key] ?? key;
  if (params) {
    for (const [k, v] of Object.entries(params)) text = text.replaceAll(`{${k}}`, String(v));
  }
  return text;
}

export function formatNumber(n: number): string {
  return new Intl.NumberFormat(lang === "ru" ? "ru-RU" : "en-US").format(Math.floor(n));
}

/** 1 234 567 -> "1,23M" */
export function compactNumber(n: number): string {
  return new Intl.NumberFormat(lang === "ru" ? "ru-RU" : "en-US", {
    notation: "compact",
    maximumFractionDigits: n >= 1000 ? 2 : 0,
  }).format(Math.floor(n));
}
