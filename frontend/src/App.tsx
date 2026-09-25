/**
 * App.tsx — root application component.
 * Sets up routing, global providers, and accessibility class injection.
 */

import { BrowserRouter, Routes, Route } from "react-router-dom";
import { AppProvider } from "@/contexts/AppContext";
import { WorkspacePage } from "@/pages/WorkspacePage";
import { SettingsPage } from "@/pages/SettingsPage";
import { useAccessibility } from "@/hooks/useAccessibility";

function AppRoutes() {
  const { a11yClass } = useAccessibility();

  return (
    <div className={a11yClass("h-screen")}>
      <Routes>
        <Route path="/" element={<WorkspacePage />} />
        <Route path="/settings" element={<SettingsPage />} />
      </Routes>
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AppProvider>
        <AppRoutes />
      </AppProvider>
    </BrowserRouter>
  );
}
