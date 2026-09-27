import { create } from "zustand";

import { api, ApiError } from "./api";
import { setLang } from "./i18n";
import { startParam } from "./tg";
import type { GameConfig, PlayerState, SessionResponse } from "./types";

interface Store {
  status: "loading" | "ready" | "error";
  error: string | null;
  state: PlayerState | null;
  config: GameConfig | null;
  isNewPlayer: boolean;
  load: () => Promise<void>;
  setState: (state: PlayerState) => void;
}

export const useStore = create<Store>((set) => ({
  status: "loading",
  error: null,
  state: null,
  config: null,
  isNewPlayer: false,

  load: async () => {
    set({ status: "loading", error: null });
    try {
      const res = await api<SessionResponse>("/session", { body: { start_param: startParam() ?? null } });
      setLang(res.state.user.lang);
      set({ status: "ready", state: res.state, config: res.config, isNewPlayer: res.created });
    } catch (e) {
      set({ status: "error", error: e instanceof ApiError ? e.code : "network" });
    }
  },

  setState: (state) => set({ state }),
}));
