import { tgUser } from "./tg";

const ru = {
  "app.title": "Битва за Мир",
  "app.loading": "Загрузка…",
  "app.error": "Не удалось загрузить игру",
  "app.retry": "Повторить",
  "app.openInTelegram": "Открой игру через Telegram-бота",
  "hello": "Привет, {name}!",
} as const;

export type I18nKey = keyof typeof ru;

const en: Record<I18nKey, string> = {
  "app.title": "World Battle",
  "app.loading": "Loading…",
  "app.error": "Failed to load the game",
  "app.retry": "Retry",
  "app.openInTelegram": "Open the game through the Telegram bot",
  "hello": "Hello, {name}!",
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
