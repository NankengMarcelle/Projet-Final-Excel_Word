import { CheckCircleIcon, AlertCircleIcon } from "../icons/EditorIcons";
import type { NotificationRecord } from "./NotificationContext";
import type { Lang } from "../../i18n/LangContext";
import { useLang } from "../../i18n/useLang";

function localeFor(lang: Lang): string {
  return lang === "fr" ? "fr-FR" : "en-US";
}

// Same day as now: just the time (matches how a chat/notification list reads once you already
// know "today"). Anything older also needs the date, since "14:32" alone stops being useful the
// moment it's not from today.
function formatNotificationTime(timestamp: number, lang: Lang): string {
  const date = new Date(timestamp);
  const now = new Date();
  const isToday =
    date.getFullYear() === now.getFullYear() &&
    date.getMonth() === now.getMonth() &&
    date.getDate() === now.getDate();
  const locale = localeFor(lang);
  if (isToday) {
    return date.toLocaleTimeString(locale, { hour: "numeric", minute: "2-digit" });
  }
  return date.toLocaleDateString(locale, { month: "short", day: "numeric" }) +
    ", " +
    date.toLocaleTimeString(locale, { hour: "numeric", minute: "2-digit" });
}

export function NotificationList({
  notifications,
  emptyMessage,
  limit,
}: {
  notifications: NotificationRecord[];
  emptyMessage: string;
  // Caps how many are actually rendered (the bell dropdown only shows a recent handful; the full
  // page shows everything) without needing two separate list components.
  limit?: number;
}) {
  const { lang } = useLang();
  const visible = limit ? notifications.slice(0, limit) : notifications;

  if (visible.length === 0) {
    return <p className="notification-list-empty">{emptyMessage}</p>;
  }

  return (
    <ul className="notification-list">
      {visible.map((notification) => (
        <li
          key={notification.id}
          className={`notification-list-item notification-list-item-${notification.variant} ${
            notification.read ? "" : "unread"
          }`}
        >
          {notification.variant === "success" ? <CheckCircleIcon /> : <AlertCircleIcon />}
          <div className="notification-list-item-body">
            <span className="notification-list-item-message">{notification.message}</span>
            <span className="notification-list-item-time">{formatNotificationTime(notification.timestamp, lang)}</span>
          </div>
        </li>
      ))}
    </ul>
  );
}
