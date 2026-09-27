import { useCallback, useEffect, useState } from "react";

import { api, ApiError } from "../api";
import { toast } from "../components/Toast";
import { useLiveBalance } from "../hooks";
import { compactNumber, formatNumber, t, type I18nKey } from "../i18n";
import { useStore, withFlushedTaps } from "../store";
import { haptic } from "../tg";
import type { CardCategory, ComboStatus, PlayerState, UpgradeCard } from "../types";

const CATEGORIES: CardCategory[] = ["economy", "army", "defense", "boost"];

export const CARD_ICONS: Record<string, string> = {
  market: "🏪",
  workshop: "🔧",
  factory: "🏭",
  bank: "🏦",
  port: "⚓",
  tech_park: "💻",
  barracks: "🪖",
  range: "🎯",
  air_base: "✈️",
  walls: "🧱",
  bunkers: "🛡️",
  air_defense: "📡",
  multitap: "👆",
  battery: "🔋",
};

export function effectText(card: UpgradeCard, value: number): string {
  const n = card.effect === "attack_bp" || card.effect === "defense_bp" ? value / 100 : value;
  const shown = card.effect === "battery" ? n * (card.battery_step ?? 500) : n;
  return t(`eff.${card.effect}` as I18nKey, { n: compactNumber(shown) });
}

export default function Upgrades() {
  const setState = useStore((s) => s.setState);
  const state = useStore((s) => s.state);
  const { coins } = useLiveBalance(500);
  const [category, setCategory] = useState<CardCategory>("economy");
  const [cards, setCards] = useState<UpgradeCard[]>([]);
  const [combo, setCombo] = useState<ComboStatus | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const reload = useCallback(async () => {
    const res = await api<{ cards: UpgradeCard[]; combo: ComboStatus }>("/upgrades");
    setCards(res.cards);
    setCombo(res.combo);
  }, []);

  useEffect(() => {
    void reload().catch(() => toast("network", "error"));
  }, [reload]);

  const buy = async (card: UpgradeCard) => {
    setBusy(card.id);
    try {
      const res = await withFlushedTaps(() =>
        api<{ card: UpgradeCard; combo: ComboStatus; combo_reward: number; state: PlayerState }>(
          `/upgrades/${card.id}/buy`,
          { body: {} },
        ),
      );
      haptic("success");
      setState(res.state);
      setCards((list) => list.map((c) => (c.id === res.card.id ? res.card : c)));
      setCombo(res.combo);
      if (res.combo_reward > 0) toast(t("upg.combo.reward", { n: formatNumber(res.combo_reward) }), "success");
    } catch (e) {
      haptic("error");
      const code = e instanceof ApiError ? e.code : "network";
      toast(code === "not_enough_coins" ? t("upg.notEnough") : code, "error");
    } finally {
      setBusy(null);
    }
  };

  if (!state) return null;

  return (
    <div className="screen">
      <div className="upg-header">
        <div className="coin-counter small">
          <span className="coin-icon">🪙</span>
          {formatNumber(coins)}
        </div>
        <div className="hint">
          {t("hq.perHour")}: +{compactNumber(state.income_per_hour)}
        </div>
      </div>

      {combo && <ComboBanner combo={combo} />}

      <div className="tabs">
        {CATEGORIES.map((c) => (
          <button key={c} className={`tab ${c === category ? "active" : ""}`} onClick={() => setCategory(c)}>
            {t(`upg.cat.${c}` as I18nKey)}
          </button>
        ))}
      </div>

      <div className="card-grid">
        {cards
          .filter((c) => c.category === category)
          .map((card) => {
            const maxed = card.next_cost === null;
            const affordable = !maxed && coins >= (card.next_cost ?? 0);
            return (
              <button
                key={card.id}
                className={`upg-card ${affordable ? "" : "locked"}`}
                disabled={maxed || busy !== null}
                onClick={() => void buy(card)}
              >
                <div className="upg-icon">{CARD_ICONS[card.id] ?? "⭐"}</div>
                <div className="upg-name">{t(`card.${card.id}` as I18nKey)}</div>
                <div className="upg-level">{t("upg.level", { n: card.level })}</div>
                {!maxed && card.next_gain !== null && (
                  <div className="upg-gain">{effectText(card, card.next_gain)}</div>
                )}
                {card.level > 0 && (
                  <div className="hint small">{t("upg.now", { v: effectText(card, card.total_effect) })}</div>
                )}
                <div className="upg-cost">
                  {maxed ? t("upg.max") : <>🪙 {compactNumber(card.next_cost ?? 0)}</>}
                </div>
              </button>
            );
          })}
      </div>
    </div>
  );
}

function ComboBanner({ combo }: { combo: ComboStatus }) {
  const slots = Array.from({ length: combo.total }, (_, i) => combo.found[i]);
  return (
    <div className={`combo ${combo.claimed ? "done" : ""}`}>
      <div className="grow">
        <div className="combo-title">{t("upg.combo.title")}</div>
        <div className="hint small">{combo.claimed ? t("upg.combo.done") : t("upg.combo.text")}</div>
        <div className="combo-reward">🪙 +{compactNumber(combo.reward)}</div>
      </div>
      <div className="combo-slots">
        {slots.map((id, i) => (
          <div key={i} className={`combo-slot ${id ? "found" : ""}`}>
            {id ? CARD_ICONS[id] : "?"}
          </div>
        ))}
      </div>
    </div>
  );
}
