import { create } from "zustand";

import { api, ApiError } from "./api";
import { setLang } from "./i18n";
import { startParam } from "./tg";
import type { ClanSummary, GameConfig, PlayerState, SeasonInfo, SessionResponse } from "./types";

export type Tab = "hq" | "map" | "upgrades" | "clan" | "more";
export type MoreScreen = "menu" | "leaderboard" | "profile" | "tasks" | "shop";

interface Store {
  status: "loading" | "ready" | "error";
  error: string | null;
  state: PlayerState | null;
  config: GameConfig | null;
  isNewPlayer: boolean;
  offlineEarned: number;
  /** Clan from a c_<id> link, offered after onboarding. */
  inviteClan: ClanSummary | null;
  /** Client clock (ms) when `state` was received: used to predict energy/passive income. */
  syncedAt: number;
  /** Taps made locally but not yet sent to the server. */
  pendingTaps: number;
  flushing: boolean;
  tab: Tab;
  more: MoreScreen;
  season: SeasonInfo | null;
  /** Client clock (ms) when `season` was received. */
  seasonAt: number;

  load: () => Promise<void>;
  setState: (state: PlayerState) => void;
  setTab: (tab: Tab) => void;
  setMore: (screen: MoreScreen) => void;
  loadSeason: () => Promise<void>;
  dismissOffline: () => void;
  dismissInvite: () => void;
  tap: () => boolean;
  flushTaps: (keepalive?: boolean) => Promise<void>;
}

export const useStore = create<Store>((set, get) => ({
  status: "loading",
  error: null,
  state: null,
  config: null,
  isNewPlayer: false,
  offlineEarned: 0,
  inviteClan: null,
  syncedAt: Date.now(),
  pendingTaps: 0,
  flushing: false,
  tab: "hq",
  more: "menu",
  season: null,
  seasonAt: 0,

  load: async () => {
    set({ status: "loading", error: null });
    try {
      const res = await api<SessionResponse>("/session", { body: { start_param: startParam() ?? null } });
      setLang(res.state.user.lang);
      set({
        status: "ready",
        state: res.state,
        config: res.config,
        isNewPlayer: res.created,
        offlineEarned: res.offline_earned,
        inviteClan: res.invite_clan,
        syncedAt: Date.now(),
      });
    } catch (e) {
      set({ status: "error", error: e instanceof ApiError ? e.code : "network" });
    }
  },

  setState: (state) => set({ state, syncedAt: Date.now() }),
  setTab: (tab) => set({ tab, more: "menu" }),
  setMore: (more) => set({ more }),
  loadSeason: async () => {
    try {
      set({ season: await api<SeasonInfo>("/season"), seasonAt: Date.now() });
    } catch {
      /* optional UI element */
    }
  },
  dismissOffline: () => set({ offlineEarned: 0 }),
  dismissInvite: () => set({ inviteClan: null }),

  tap: () => {
    const { state, syncedAt, pendingTaps } = get();
    if (!state) return false;
    if (predictEnergy(state, syncedAt, pendingTaps, Date.now()) < 1) return false;
    set({ pendingTaps: pendingTaps + 1 });
    return true;
  },

  flushTaps: async (keepalive = false) => {
    const { pendingTaps, flushing } = get();
    if (pendingTaps <= 0 || flushing) return;
    set({ flushing: true });
    try {
      const res = await api<{ earned: number; state: PlayerState }>("/tap", {
        body: { taps: pendingTaps },
        keepalive,
      });
      // Taps made while the request was in flight stay pending.
      set((s) => ({ state: res.state, syncedAt: Date.now(), pendingTaps: s.pendingTaps - pendingTaps }));
    } catch (e) {
      // Rate-limited or network error: keep the taps and retry on the next flush.
      if (e instanceof ApiError && e.status !== 429) set((s) => ({ pendingTaps: s.pendingTaps - pendingTaps }));
    } finally {
      set({ flushing: false });
    }
  },
}));

export function predictEnergy(state: PlayerState, syncedAt: number, pendingTaps: number, now: number): number {
  const regen = Math.floor(((now - syncedAt) / 1000) * state.energy_regen_per_sec);
  return Math.max(0, Math.min(state.energy_max, state.energy + regen) - pendingTaps);
}

export function predictCoins(state: PlayerState, syncedAt: number, pendingTaps: number, now: number): number {
  const hours = Math.min((now - syncedAt) / 3_600_000, state.offline_cap_hours);
  return state.coins + pendingTaps * state.tap_power + Math.floor(state.income_per_hour * hours);
}

/** Flushes pending taps before a request that depends on the server-side balance. */
export async function withFlushedTaps<T>(fn: () => Promise<T>): Promise<T> {
  while (useStore.getState().flushing) await new Promise((r) => setTimeout(r, 50));
  await useStore.getState().flushTaps();
  return fn();
}
