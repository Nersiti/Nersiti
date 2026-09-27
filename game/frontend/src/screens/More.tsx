import { useEffect } from "react";

import { t, type I18nKey } from "../i18n";
import { useStore, type MoreScreen } from "../store";
import { haptic, webApp } from "../tg";
import Leaderboard from "./Leaderboard";
import Profile from "./Profile";
import Shop from "./Shop";
import Soon from "./Soon";

const ITEMS: { id: MoreScreen; icon: string }[] = [
  { id: "leaderboard", icon: "🏆" },
  { id: "tasks", icon: "🎯" },
  { id: "shop", icon: "⭐" },
  { id: "profile", icon: "👤" },
];

export default function More() {
  const { more, setMore } = useStore();

  // Telegram's native back button returns to the menu.
  useEffect(() => {
    const back = webApp()?.BackButton;
    if (!back) return;
    const onBack = () => setMore("menu");
    if (more === "menu") {
      back.hide();
      return;
    }
    back.show();
    back.onClick(onBack);
    return () => {
      back.offClick(onBack);
      back.hide();
    };
  }, [more, setMore]);

  if (more === "menu") {
    return (
      <div className="screen">
        {ITEMS.map((item) => (
          <button
            key={item.id}
            className="menu-item"
            onClick={() => {
              haptic("select");
              setMore(item.id);
            }}
          >
            <span className="menu-icon">{item.icon}</span>
            <span className="grow">
              <span className="menu-title">{t(`more.${item.id}` as I18nKey)}</span>
              <span className="hint small">{t(`more.${item.id}.hint` as I18nKey)}</span>
            </span>
            <span className="hint">›</span>
          </button>
        ))}
      </div>
    );
  }

  return (
    <>
      {!webApp() && (
        <button className="back-link" onClick={() => setMore("menu")}>
          ‹ {t("back")}
        </button>
      )}
      {more === "leaderboard" && <Leaderboard />}
      {more === "profile" && <Profile />}
      {more === "tasks" && <Soon icon="🎯" />}
      {more === "shop" && <Shop />}
    </>
  );
}
