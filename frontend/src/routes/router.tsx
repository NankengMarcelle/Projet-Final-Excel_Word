import { createBrowserRouter, Navigate } from "react-router-dom";
import { AdminRoute, ProtectedRoute } from "../auth/ProtectedRoute";
import { AppShell } from "../components/shell/AppShell";
import { LoginPage } from "./LoginPage";
import { RegisterPage } from "./RegisterPage";
import { ForgotPasswordPage } from "./ForgotPasswordPage";
import { ResetPasswordPage } from "./ResetPasswordPage";
import { WorkspacePage } from "./WorkspacePage";
import { AllWorkbooksPage } from "./AllWorkbooksPage";
import { WordFilesPage } from "./WordFilesPage";
import { NotificationsPage } from "./NotificationsPage";
import { EditorPage } from "./EditorPage";
import { AdminPage } from "./AdminPage";

export const router = createBrowserRouter([
  { path: "/", element: <Navigate to="/workspace" replace /> },
  { path: "/login", element: <LoginPage /> },
  { path: "/register", element: <RegisterPage /> },
  { path: "/forgot-password", element: <ForgotPasswordPage /> },
  { path: "/reset-password", element: <ResetPasswordPage /> },
  {
    element: <ProtectedRoute />,
    children: [
      // Workspace gets the sidebar/header shell; the editor deliberately doesn't (see
      // AppShell.tsx) — its own collapsible chrome already handles this without costing the
      // grid vertical space the way a second, always-on global header/sidebar would.
      {
        element: <AppShell />,
        children: [
          { path: "/workspace", element: <WorkspacePage /> },
          { path: "/workspace/all", element: <AllWorkbooksPage /> },
          { path: "/word-files", element: <WordFilesPage /> },
          { path: "/notifications", element: <NotificationsPage /> },
        ],
      },
      { path: "/workbooks/:workbookId", element: <EditorPage /> },
    ],
  },
  {
    element: <AdminRoute />,
    children: [
      {
        element: <AppShell />,
        children: [{ path: "/admin", element: <AdminPage /> }],
      },
    ],
  },
]);
