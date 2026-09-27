import { api, ApiError } from "./api";
import { toast } from "./components/Toast";
import { errorText, t } from "./i18n";
import { useStore } from "./store";
import { haptic, openInvoice } from "./tg";

function shopError(code: string): string {
  return errorText(code, "shop.err");
}

/** Buys a shop item for Telegram Stars. Resolves true when paid. */
export async function purchase(itemId: string, param?: string): Promise<boolean> {
  let link: string;
  try {
    link = (await api<{ invoice_link: string }>("/shop/invoice", { body: { item_id: itemId, param } })).invoice_link;
  } catch (e) {
    haptic("error");
    toast(shopError(e instanceof ApiError ? e.code : "network"), "error");
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

export { shopError as shopErrorText };
