// Thin typed wrapper over https://telegram.org/js/telegram-web-app.js
// Docs: https://core.telegram.org/bots/webapps

export interface TgUser {
  id: number;
  first_name: string;
  last_name?: string;
  username?: string;
  language_code?: string;
  is_premium?: boolean;
  photo_url?: string;
}

interface TgWebApp {
  initData: string;
  initDataUnsafe: { user?: TgUser; start_param?: string };
  version: string;
  platform: string;
  colorScheme: "light" | "dark";
  themeParams: Record<string, string>;
  isVersionAtLeast(version: string): boolean;
  ready(): void;
  expand(): void;
  close(): void;
  disableVerticalSwipes?: () => void;
  setHeaderColor?: (color: string) => void;
  setBackgroundColor?: (color: string) => void;
  HapticFeedback: {
    impactOccurred(style: "light" | "medium" | "heavy" | "rigid" | "soft"): void;
    notificationOccurred(type: "error" | "success" | "warning"): void;
    selectionChanged(): void;
  };
  BackButton: {
    show(): void;
    hide(): void;
    onClick(cb: () => void): void;
    offClick(cb: () => void): void;
  };
  openInvoice?: (url: string, cb?: (status: "paid" | "cancelled" | "failed" | "pending") => void) => void;
  openTelegramLink(url: string): void;
  openLink(url: string): void;
  shareToStory?: (
    mediaUrl: string,
    params?: { text?: string; widget_link?: { url: string; name?: string } },
  ) => void;
  shareMessage?: (preparedMessageId: string, cb?: (sent: boolean) => void) => void;
  addToHomeScreen?: () => void;
  showAlert(message: string, cb?: () => void): void;
  showConfirm(message: string, cb?: (ok: boolean) => void): void;
  onEvent(event: string, cb: (...args: unknown[]) => void): void;
  offEvent(event: string, cb: (...args: unknown[]) => void): void;
}

declare global {
  interface Window {
    Telegram?: { WebApp: TgWebApp };
  }
}

export function webApp(): TgWebApp | undefined {
  const wa = window.Telegram?.WebApp;
  // Outside Telegram the script still defines WebApp, but with empty initData.
  return wa && wa.initData ? wa : undefined;
}

export function initTelegram(): void {
  const wa = window.Telegram?.WebApp;
  if (!wa) return;
  wa.ready();
  wa.expand();
  // Without this, panning the map down collapses the Mini App.
  if (wa.isVersionAtLeast("7.7")) wa.disableVerticalSwipes?.();
  applyTheme();
  wa.onEvent("themeChanged", applyTheme);
}

function applyTheme(): void {
  const wa = window.Telegram?.WebApp;
  const root = document.documentElement;
  root.dataset.scheme = wa?.colorScheme ?? "dark";
  for (const [key, value] of Object.entries(wa?.themeParams ?? {})) {
    root.style.setProperty(`--tg-${key.replace(/_/g, "-")}`, value);
  }
}

export function initData(): string {
  return webApp()?.initData ?? "";
}

export function tgUser(): TgUser | undefined {
  return webApp()?.initDataUnsafe.user;
}

/** Referral / clan code: from the direct link (?startapp=) or from the bot button (?sp=). */
export function startParam(): string | undefined {
  const fromTg = webApp()?.initDataUnsafe.start_param;
  if (fromTg) return fromTg;
  return new URLSearchParams(window.location.search).get("sp") ?? undefined;
}

export function haptic(kind: "tap" | "success" | "error" | "select" = "tap"): void {
  const h = webApp()?.HapticFeedback;
  if (!h) return;
  if (kind === "tap") h.impactOccurred("light");
  else if (kind === "select") h.selectionChanged();
  else h.notificationOccurred(kind);
}

/** Opens a t.me link inside Telegram (or a new tab outside it). */
export function openTgLink(url: string): void {
  const wa = webApp();
  if (wa && url.startsWith("https://t.me/")) wa.openTelegramLink(url);
  else window.open(url, "_blank");
}

export function shareLink(url: string, text: string): void {
  openTgLink(`https://t.me/share/url?url=${encodeURIComponent(url)}&text=${encodeURIComponent(text)}`);
}

export function confirmDialog(message: string): Promise<boolean> {
  const wa = webApp();
  if (wa) return new Promise((resolve) => wa.showConfirm(message, (ok) => resolve(ok)));
  return Promise.resolve(window.confirm(message));
}
