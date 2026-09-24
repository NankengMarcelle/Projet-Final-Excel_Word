import { NotificationList } from "../components/common/NotificationList";
import { useNotifications } from "../components/common/NotificationContext";
import { copy } from "../i18n/copy";
import { useLang } from "../i18n/useLang";
import "./NotificationsPage.css";

export function NotificationsPage() {
  const { lang } = useLang();
  const t = copy[lang];
  const { notifications, markAllRead, clearAll, unreadCount } = useNotifications();

  return (
    <main className="notifications-main">
      <section className="notifications-heading-section">
        <div>
          <h1 className="notifications-heading">{t.navNotifications}</h1>
          <p className="notifications-subtitle">{t.notificationsSubtitle}</p>
        </div>
        {notifications.length > 0 && (
          <div className="notifications-actions">
            <button type="button" className="notifications-action-btn" onClick={markAllRead} disabled={unreadCount === 0}>
              {t.markAllReadLabel}
            </button>
            <button type="button" className="notifications-action-btn" onClick={clearAll}>
              {t.clearAllLabel}
            </button>
          </div>
        )}
      </section>
      <section className="notifications-list-section">
        <NotificationList notifications={notifications} emptyMessage={t.notificationsEmpty} />
      </section>
    </main>
  );
}
