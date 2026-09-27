import { t } from "../i18n";

export default function Soon(props: { icon: string }) {
  return (
    <div className="screen center-screen">
      <div className="big-emoji">{props.icon}</div>
      <h2>{t("soon.title")}</h2>
      <p>{t("soon.text")}</p>
    </div>
  );
}
