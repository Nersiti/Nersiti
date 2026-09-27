import { useEffect } from "react";

import { t } from "./i18n";
import { useStore } from "./store";

export default function App() {
  const { status, error, state, load } = useStore();

  useEffect(() => {
    void load();
  }, [load]);

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

  return (
    <div className="center-screen">
      <h1>{t("app.title")}</h1>
      <p>{t("hello", { name: state.user.first_name })}</p>
    </div>
  );
}
