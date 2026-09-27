import { t, type I18nKey } from "../i18n";
import { useStore, type Tab } from "../store";
import { haptic } from "../tg";

const TABS: { id: Tab; icon: string; label: I18nKey }[] = [
  { id: "hq", icon: "🏰", label: "nav.hq" },
  { id: "map", icon: "🗺️", label: "nav.map" },
  { id: "upgrades", icon: "⚙️", label: "nav.upgrades" },
  { id: "clan", icon: "⚔️", label: "nav.clan" },
  { id: "more", icon: "☰", label: "nav.more" },
];

export default function BottomNav() {
  const { tab, setTab } = useStore();
  return (
    <nav className="bottom-nav">
      {TABS.map((item) => (
        <button
          key={item.id}
          className={`nav-item ${tab === item.id ? "active" : ""}`}
          onClick={() => {
            if (tab !== item.id) haptic("select");
            setTab(item.id);
          }}
        >
          <span className="nav-icon">{item.icon}</span>
          <span className="nav-label">{t(item.label)}</span>
        </button>
      ))}
    </nav>
  );
}
