import { api, ApiError } from "./api";
import { toast } from "./components/Toast";
import { t, type I18nKey } from "./i18n";
import { useStore } from "./store";
import { haptic, openInvoice } from "./tg";

function errorText(code: string): string {
  const key = `shop.err.${code}` as I18nKey;
  const text = t(key);
  return text === key ? code : text;
}

/** Buys a shop item for Telegram Stars. Resolves true when paid. */
export async function purchase(itemId: string, param?: string): Promise<boolean> {
  let link: string;
  try {
    link = (await api<{ invoice_link: string }>("/shop/invoice", { body: { item_id: itemId, param } })).invoice_link;
  } catch (e) {
    haptic("error");
    toast(errorText(e instanceof ApiError ? e.code : "network"), "error");
    return false;
  }
  const status = await openInvoice(link);
  if (status === "paid") {
    haptic("success");
    toast(t("shop.paid"), "success");
    // The bot grants the item from the successful_payment webhook: give it a moment.
    const { refresh } = useStore.getState();
    setTimeout(() => void refresh(), 1500);
    setTimeout(() => void refresh(), 5000);
    return true;
  }
  if (status === "pending") toast(t("shop.pending"));
  if (status === "failed") toast(t("shop.failed"), "error");
  return false;
}

export { errorText as shopErrorText };
