/**
 * Axios instance con interceptor JWT automatico.
 *
 * Todos los requests a /api/... incluyen automaticamente:
 *   Authorization: Bearer <token de localStorage>
 *
 * Si el server retorna 401, se limpia localStorage y se redirige a /login.
 * En desarrollo, el proxy de Vite convierte /api/... → http://localhost:8000/...
 * En produccion Railway, FastAPI sirve el frontend y el prefijo /api no existe —
 * usar baseURL="" y el proxy no aplica.
 */
import axios from "axios";

export const apiClient = axios.create({
  baseURL: "/api",
  headers: {
    "Content-Type": "application/json",
  },
});

// Interceptor de request: agregar token JWT a todos los requests
apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem("token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Interceptor de response: manejar 401 globalmente
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem("token");
      window.location.href = "/login";
    }
    return Promise.reject(error);
  }
);

export type DeviceStatus = "up" | "down" | "warning" | "unknown";

export type DeviceType =
  | "mikrotik"
  | "olt_vsol_gpon"
  | "olt_vsol_epon"
  | "onu"
  | "ubiquiti"
  | "mimosa"
  | "other";

export interface Device {
  id: number;
  name: string;
  ip_address: string;
  device_type: DeviceType;
  site: string | null;
  status: DeviceStatus;
  is_active: boolean;
  consecutive_failures: number;
  last_seen_at: string | null;
  created_at: string;
  updated_at: string;
  parent_device_id: number | null;
  pon_port: string | null;
  notes: string | null;
}

export interface DeviceCreate {
  name: string;
  ip_address: string;
  device_type: DeviceType;
  site?: string;
  notes?: string;
  parent_device_id?: number;
  pon_port?: string;
}
