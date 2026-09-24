import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { CheckCircleIcon, AlertCircleIcon } from "../icons/EditorIcons";
import { copy } from "../../i18n/copy";
import { useLang } from "../../i18n/useLang";
import { useAuth } from "../../auth/useAuth";

type NotificationVariant = "success" | "error";

export interface NotificationRecord {
  id: string;
  message: string;
  variant: NotificationVariant;
  // epoch ms — kept as a number (not a Date) so it survives the JSON round-trip through
  // localStorage without a revive step.
  timestamp: number;
  read: boolean;
}

interface Toast {
  id: number;
  message: string;
  variant: NotificationVariant;
}

interface NotificationContextValue {
  // Fire-and-forget: several long-running actions (uploading a workbook, converting to Word,
  // creating a child sheet) used to end in total silence — the button's own spinner stopped and
  // that was the only signal anything had happened at all, success or failure alike. Every call
  // both pops the transient toast AND records a NotificationRecord, so the same event is still
  // findable later from the notification bell/page even after the toast itself has dismissed.
  showToast: (message: string, variant?: NotificationVariant) => void;
  notifications: NotificationRecord[];
  unreadCount: number;
  markAllRead: () => void;
  clearAll: () => void;
}

const NotificationContext = createContext<NotificationContextValue | undefined>(undefined);

const AUTO_DISMISS_MS = 4500;
// Not a real per-user backend log, just a local convenience history — capped so one very active
// session can't grow this into an unbounded localStorage blob.
const MAX_HISTORY = 50;

// Keyed by user id, not one shared bucket — this is localStorage, which is per-browser, not
// per-account. Without this, logging out and a different person logging in on the same machine
// would see the previous person's notification history (e.g. "Workbook X uploaded" for a
// workbook they never touched). `null` (no signed-in user yet, e.g. still bootstrapping auth on
// a fresh page load) deliberately has no storage key at all, not a shared "anonymous" one.
function storageKeyFor(userId: string | null): string | null {
  return userId ? `sheetflow.notifications.${userId}` : null;
}

function loadHistory(key: string | null): NotificationRecord[] {
  if (!key) return [];
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    // Corrupt JSON, private-browsing storage quirks, etc. — an empty history is a safe fallback,
    // never worth surfacing as an error to the user.
    return [];
  }
}

function saveHistory(key: string | null, notifications: NotificationRecord[]): void {
  if (!key) return;
  try {
    localStorage.setItem(key, JSON.stringify(notifications));
  } catch {
    // Best-effort only — a full/blocked localStorage shouldn't break notifications for the
    // current session, just their persistence across reloads.
  }
}

// Mounted once, above the router (see main.tsx) — same reasoning as any other app-wide, fire-
// once notification: a toast triggered right before a navigation (or from a panel that closes
// itself on success, like ChildSheetPanel/ConvertToWordPanel do) shouldn't vanish with whatever
// page or component triggered it.
export function NotificationProvider({ children }: { children: ReactNode }) {
  const { lang } = useLang();
  const t = copy[lang];
  const { user } = useAuth();
  const userId = user?.id ?? null;
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [notifications, setNotifications] = useState<NotificationRecord[]>(() => loadHistory(storageKeyFor(userId)));
  const nextToastIdRef = useRef(0);

  // Re-hydrate whenever the signed-in user changes — covers the initial async auth check
  // resolving (userId goes null -> real id right after mount) and an actual account switch
  // (logout, then a different user logging in on the same browser): each gets its own history
  // loaded fresh instead of inheriting whatever was in memory from the previous user.
  useEffect(() => {
    setNotifications(loadHistory(storageKeyFor(userId)));
  }, [userId]);

  useEffect(() => {
    saveHistory(storageKeyFor(userId), notifications);
  }, [notifications, userId]);

  const dismissToast = useCallback((id: number) => {
    setToasts((current) => current.filter((toast) => toast.id !== id));
  }, []);

  const showToast = useCallback(
    (message: string, variant: NotificationVariant = "success") => {
      const toastId = nextToastIdRef.current++;
      setToasts((current) => [...current, { id: toastId, message, variant }]);
      setTimeout(() => dismissToast(toastId), AUTO_DISMISS_MS);

      const record: NotificationRecord = {
        id: `${Date.now()}-${toastId}`,
        message,
        variant,
        timestamp: Date.now(),
        read: false,
      };
      setNotifications((current) => [record, ...current].slice(0, MAX_HISTORY));
    },
    [dismissToast]
  );

  const markAllRead = useCallback(() => {
    setNotifications((current) => current.map((n) => (n.read ? n : { ...n, read: true })));
  }, []);

  const clearAll = useCallback(() => {
    setNotifications([]);
  }, []);

  const unreadCount = useMemo(() => notifications.filter((n) => !n.read).length, [notifications]);

  const value = useMemo(
    () => ({ showToast, notifications, unreadCount, markAllRead, clearAll }),
    [showToast, notifications, unreadCount, markAllRead, clearAll]
  );

  return (
    <NotificationContext.Provider value={value}>
      {children}
      <div className="toast-stack" role="status" aria-live="polite">
        {toasts.map((toast) => (
          <div key={toast.id} className={`toast toast-${toast.variant}`}>
            {toast.variant === "success" ? <CheckCircleIcon /> : <AlertCircleIcon />}
            <span className="toast-message">{toast.message}</span>
            <button
              type="button"
              className="toast-dismiss"
              onClick={() => dismissToast(toast.id)}
              aria-label={t.closeLabel}
              title={t.closeLabel}
            >
              ×
            </button>
          </div>
        ))}
      </div>
    </NotificationContext.Provider>
  );
}

function useNotificationContext(): NotificationContextValue {
  const context = useContext(NotificationContext);
  if (!context) {
    throw new Error("useNotificationContext must be used within a NotificationProvider");
  }
  return context;
}

// Narrow view for call sites that only ever fire toasts (UploadForm, ChildSheetPanel,
// ConvertToWordPanel) — keeps their imports reading as "I show a toast," not "I touch the whole
// notification system."
export function useToast(): Pick<NotificationContextValue, "showToast"> {
  const { showToast } = useNotificationContext();
  return { showToast };
}

// Full view for the notification bell and the notifications page.
export function useNotifications(): NotificationContextValue {
  return useNotificationContext();
}
