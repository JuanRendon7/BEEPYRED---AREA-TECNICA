/**
 * Hook React para SSE — actualiza el cache de TanStack Query en tiempo real.
 *
 * POLL-05: el EventSource del browser se suscribe a GET /api/events?token=...
 * Cada evento de status cambio actualiza optimistamente el device en el cache
 * de TanStack Query sin invalidar (evita refetch innecesario).
 *
 * CRITICO — EventSource y JWT:
 *   EventSource no soporta headers custom. El token va como query param.
 *   Para herramienta interna v1, esto es aceptable (T-2-30 aceptado).
 */
import { useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
import type { Device, DeviceStatus } from "@/api/client";

interface StatusUpdate {
  id: number;
  status: DeviceStatus;
}

export function useDeviceStream() {
  const queryClient = useQueryClient();
  const token = localStorage.getItem("token");

  useEffect(() => {
    if (!token) return;

    // Prefijo /api porque en dev el proxy de Vite reescribe a FastAPI
    const es = new EventSource(`/api/events?token=${token}`);

    es.onmessage = (event) => {
      try {
        const update: StatusUpdate = JSON.parse(event.data);
        // Actualizar optimistamente el device en el cache — sin refetch
        queryClient.setQueryData<Device[]>(["devices"], (old) => {
          if (!old) return old;
          return old.map((d) =>
            d.id === update.id ? { ...d, status: update.status } : d
          );
        });
      } catch {
        // Ignorar mensajes mal formateados (ej: keep-alive comments)
      }
    };

    es.onerror = () => {
      // Reconexion automatica — EventSource la maneja internamente
      // Solo loggear para debugging en dev
      if (import.meta.env.DEV) {
        console.warn("SSE connection lost — reconnecting...");
      }
    };

    return () => {
      es.close();
    };
  }, [token, queryClient]);
}
