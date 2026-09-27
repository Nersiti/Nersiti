import { useEffect } from "react";

import BottomNav from "./components/BottomNav";
import Toast from "./components/Toast";
import { t } from "./i18n";
import Hq from "./screens/Hq";
import Onboarding from "./screens/Onboarding";
import Soon from "./screens/Soon";
import Upgrades from "./screens/Upgrades";
import { useStore } from "./store";

const TAP_FLUSH_INTERVAL_MS = 10_000;

export default function App() {
  const { status, error, state, load, tab } = useStore();

  useEffect(() => {
    void load();
  }, [load]);

  // Send accumulated taps every 10s and when the app goes to the background.
  useEffect(() => {
    const flush = (keepalive = false) => void useStore.getState().flushTaps(keepalive);
    const id = setInterval(() => flush(), TAP_FLUSH_INTERVAL_MS);
    const onVisibility = () => {
      if (document.visibilityState === "hidden") flush(true);
    };
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      clearInterval(id);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, []);

  if (status === "loading") {
    return <div className="center-screen">{t("app.loading")}</div>;
  }

  if (status === "error" || !state) {
    return (
      <div className="center-screen">
        <h1>{t("app.error")}</h1>
        <p>{error === "unauthorized" ? t("app.openInTelegram") : error}</p>
        <button className="btn" onClick={() => void load()}>
          {t("app.retry")}
        </button>
      </div>
    );
  }

  if (!state.onboarded) return <Onboarding />;

  return (
    <div className="app">
      <main className="app-main">
        {tab === "hq" && <Hq />}
        {tab === "upgrades" && <Upgrades />}
        {tab === "map" && <Soon icon="🗺️" />}
        {tab === "clan" && <Soon icon="⚔️" />}
        {tab === "more" && <Soon icon="☰" />}
      </main>
      <BottomNav />
      <Toast />
    </div>
  );
}
