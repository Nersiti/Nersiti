import { t } from "./i18n";
import { tgUser } from "./tg";

export default function App() {
  const user = tgUser();
  return (
    <div className="center-screen">
      <h1>{t("app.title")}</h1>
      <p>{user ? t("hello", { name: user.first_name }) : t("app.openInTelegram")}</p>
    </div>
  );
}
