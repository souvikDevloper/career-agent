import { useEffect, useState } from "react";
import { getSession, onSession } from "./lib/auth";
import { MeProvider } from "./lib/me";
import { match, RouterProvider, useRouter } from "./lib/router";
import { ToastProvider } from "./components/ui";
import { Landing } from "./pages/Landing";
import { AuthPage } from "./pages/Auth";
import { Home } from "./pages/Home";
import { AgentPage } from "./pages/Agent";
import { JobsPage } from "./pages/Jobs";
import { ApplicationsPage } from "./pages/Applications";
import { ApplicationDetailPage } from "./pages/ApplicationDetail";
import { TasksPage } from "./pages/Tasks";
import { InsightsPage } from "./pages/Insights";
import { ConnectorsPage } from "./pages/Connectors";
import { ProfilePage } from "./pages/Profile";
import { SettingsPage } from "./pages/Settings";

function Routes() {
  const { path, navigate } = useRouter();
  const [session, setSession] = useState(getSession());
  useEffect(() => onSession((s) => setSession(s)), []);
  const inApp = path.startsWith("/app");

  useEffect(() => {
    if (inApp && !session) navigate("/login", true);
    if ((path === "/login" || path === "/signup") && session) navigate("/app", true);
  }, [inApp, session, path, navigate]);

  if (!inApp) {
    if (path === "/login") return <AuthPage mode="login" />;
    if (path === "/signup") return <AuthPage mode="signup" />;
    return <Landing />;
  }
  if (!session) return null;
  const detail = match("/app/applications/:id", path);
  return (
    <MeProvider>
      {detail ? <ApplicationDetailPage id={detail.id} />
        : path === "/app/agent" ? <AgentPage />
        : path === "/app/jobs" ? <JobsPage />
        : path === "/app/applications" ? <ApplicationsPage />
        : path === "/app/tasks" ? <TasksPage />
        : path === "/app/insights" ? <InsightsPage />
        : path === "/app/connectors" ? <ConnectorsPage />
        : path === "/app/profile" ? <ProfilePage />
        : path === "/app/settings" ? <SettingsPage />
        : <Home />}
    </MeProvider>
  );
}

export function App() {
  return (
    <RouterProvider>
      <ToastProvider>
        <Routes />
      </ToastProvider>
    </RouterProvider>
  );
}
