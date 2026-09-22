import { createBrowserRouter, Navigate } from "react-router-dom";
import { AdminRoute, ProtectedRoute } from "../auth/ProtectedRoute";
import { AppShell } from "../components/shell/AppShell";
import { LoginPage } from "./LoginPage";
import { RegisterPage } from "./RegisterPage";
import { WorkspacePage } from "./WorkspacePage";
import { WordFilesPage } from "./WordFilesPage";
import { EditorPage } from "./EditorPage";
import { AdminPage } from "./AdminPage";

export const router = createBrowserRouter([
  { path: "/", element: <Navigate to="/workspace" replace /> },
  { path: "/login", element: <LoginPage /> },
  { path: "/register", element: <RegisterPage /> },
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
          { path: "/word-files", element: <WordFilesPage /> },
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
