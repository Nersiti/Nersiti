import { useEffect, useState } from "react";

import { predictCoins, predictEnergy, useStore } from "./store";

/** Re-renders the component every `intervalMs` and returns the current time. */
export function useNow(intervalMs = 250): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), intervalMs);
    return () => clearInterval(id);
  }, [intervalMs]);
  return now;
}

/** Coins and energy as the player should see them right now (server state + local prediction). */
export function useLiveBalance(intervalMs = 250): { coins: number; energy: number } {
  const now = useNow(intervalMs);
  const { state, syncedAt, pendingTaps } = useStore();
  if (!state) return { coins: 0, energy: 0 };
  return {
    coins: predictCoins(state, syncedAt, pendingTaps, now),
    energy: predictEnergy(state, syncedAt, pendingTaps, now),
  };
}
