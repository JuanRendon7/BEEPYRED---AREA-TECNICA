/**
 * Configuracion de React Router con PrivateRoute guard.
 *
 * AUTH-03: Sin token valido en localStorage, /dashboard e /inventory
 * redirigen a /login automaticamente.
 *
 * Rutas:
 *   /login      → LoginPage (publica)
 *   /dashboard  → DashboardPage (protegida)
 *   /inventory  → InventoryPage (protegida)
 *   /incidents  → IncidentsPage (protegida)
 *   /           → redirect a /dashboard
 */
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import type { ReactNode } from "react";
import { LoginPage } from "@/pages/Login";
import { DashboardPage } from "@/pages/Dashboard";
import { InventoryPage } from "@/pages/Inventory";
import { IncidentsPage } from "@/pages/Incidents";

function PrivateRoute({ children }: { children: ReactNode }) {
  const token = localStorage.getItem("token");
  if (!token) {
    return <Navigate to="/login" replace />;
  }
  return <>{children}</>;
}

export function AppRouter() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route
          path="/dashboard"
          element={
            <PrivateRoute>
              <DashboardPage />
            </PrivateRoute>
          }
        />
        <Route
          path="/inventory"
          element={
            <PrivateRoute>
              <InventoryPage />
            </PrivateRoute>
          }
        />
        <Route
          path="/incidents"
          element={
            <PrivateRoute>
              <IncidentsPage />
            </PrivateRoute>
          }
        />
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
