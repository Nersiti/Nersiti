import { useCallback, useEffect, useState } from "react";

import { api } from "../api";
import Sheet from "../components/Sheet";
import { toast } from "../components/Toast";
import { compactNumber, getLang, t, type I18nKey } from "../i18n";
import { purchase } from "../shop";
import { useStore } from "../store";
import type { ShopInfo, ShopItemInfo } from "../types";

const ICONS: Record<string, string> = {
  coins_bag: "💰",
  energy_refill: "⚡",
  artillery: "💥",
  shield: "🛡️",
  autocollector: "🤖",
  vip: "👑",
  clan_color: "🎨",
  clan_promo: "📣",
  test_star: "🧪",
};

export default function Shop() {
  const { state, setTab } = useStore();
  const [info, setInfo] = useState<ShopInfo | null>(null);
  const [palette, setPalette] = useState(false);

  const reload = useCallback(() => {
    api<ShopInfo>("/shop")
      .then(setInfo)
      .catch(() => toast("network", "error"));
  }, []);

  useEffect(reload, [reload]);

  if (!state || !info) return <div className="screen">{t("app.loading")}</div>;

  const buy = async (item: ShopItemInfo) => {
    if (item.param === "sector") {
      toast(t("shop.shieldHint"));
      setTab("map");
      return;
    }
    if (item.param === "color") {
      setPalette(true);
      return;
    }
    if (await purchase(item.id)) setTimeout(reload, 1600);
  };

  return (
    <div className="screen">
      <p className="hint">{t("shop.intro")}</p>
      {state.vip_until && (
        <div className="notice ok">
          {t("shop.vipActive", { date: new Date(state.vip_until).toLocaleDateString(getLang()) })}
        </div>
      )}
      <div className="card-grid">
        {info.items.map((item) => (
          <button
            key={item.id}
            className={`upg-card shop-card ${item.id === "vip" ? "vip" : ""} ${item.available ? "" : "locked"}`}
            disabled={!item.available}
            onClick={() => void buy(item)}
          >
            <div className="upg-icon">{ICONS[item.id] ?? "⭐"}</div>
            <div className="upg-name">{t(`shop.title.${item.id}` as I18nKey)}</div>
            <div className="hint small">
              {item.id === "coins_bag"
                ? `+${compactNumber(info.coins_bag_amount)} 🪙`
                : t(`shop.desc.${item.id}` as I18nKey)}
            </div>
            {item.daily_limit !== null && (
              <div className="hint small">{t("shop.limit", { used: item.used_today, limit: item.daily_limit })}</div>
            )}
            {item.clan_owner_only && !info.is_clan_owner && <div className="hint small">{t("shop.ownerOnly")}</div>}
            <div className="upg-cost star-cost">
              ⭐ {item.stars}
              {item.subscription ? t("shop.perMonth") : ""}
            </div>
          </button>
        ))}
      </div>

      <ColorSheet
        open={palette}
        colors={info.palette}
        onClose={() => setPalette(false)}
        onPick={async (color) => {
          setPalette(false);
          await purchase("clan_color", color);
        }}
      />
    </div>
  );
}

export function ColorSheet(props: {
  open: boolean;
  colors: string[];
  onClose: () => void;
  onPick: (color: string) => void;
}) {
  return (
    <Sheet open={props.open} onClose={props.onClose}>
      <h3>{t("shop.pickColor")}</h3>
      <div className="palette">
        {props.colors.map((c) => (
          <button key={c} className="swatch" style={{ background: c }} onClick={() => props.onPick(c)} />
        ))}
      </div>
    </Sheet>
  );
}
