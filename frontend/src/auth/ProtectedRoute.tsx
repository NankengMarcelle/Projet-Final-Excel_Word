import { Navigate, Outlet } from "react-router-dom";
import { useAuth } from "./useAuth";
import { LoadingState } from "../components/common/LoadingState";
import { copy } from "../i18n/copy";
import { useLang } from "../i18n/useLang";

export function ProtectedRoute() {
  const { user, isLoading } = useAuth();
  const { lang } = useLang();
  const t = copy[lang];

  if (isLoading) {
    return <LoadingState message={t.loadingSessionMsg} />;
  }

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  return <Outlet />;
}

export function AdminRoute() {
  const { user, isLoading } = useAuth();
  const { lang } = useLang();
  const t = copy[lang];

  if (isLoading) {
    return <LoadingState message={t.loadingSessionMsg} />;
  }

  if (!user || user.role !== "admin") {
    return <Navigate to="/workspace" replace />;
  }

  return <Outlet />;
}
