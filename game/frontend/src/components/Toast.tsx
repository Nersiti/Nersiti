import { create } from "zustand";

import { ApiError } from "../api";
import { errorText } from "../i18n";

interface ToastStore {
  text: string | null;
  kind: "info" | "error" | "success";
  show: (text: string, kind?: "info" | "error" | "success") => void;
}

let timer: ReturnType<typeof setTimeout> | undefined;

export const useToast = create<ToastStore>((set) => ({
  text: null,
  kind: "info",
  show: (text, kind = "info") => {
    clearTimeout(timer);
    set({ text, kind });
    timer = setTimeout(() => set({ text: null }), 2500);
  },
}));

export function toast(text: string, kind: "info" | "error" | "success" = "info"): void {
  useToast.getState().show(text, kind);
}

export default function Toast() {
  const { text, kind } = useToast();
  if (!text) return null;
  return <div className={`toast toast-${kind}`}>{text}</div>;
}

/** Shows an API/network error in plain words. */
export function toastError(e: unknown, prefix?: string): void {
  toast(errorText(e instanceof ApiError ? e.code : "network", prefix), "error");
}
