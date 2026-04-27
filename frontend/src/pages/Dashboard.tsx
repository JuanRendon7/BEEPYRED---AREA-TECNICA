/**
 * Dashboard principal — INV-04, POLL-05.
 *
 * Carga la lista de dispositivos via GET /api/devices (TanStack Query).
 * useDeviceStream() suscribe al SSE y actualiza el cache en tiempo real.
 * El tecnico ve UP/DOWN/WARNING/UNKNOWN sin recargar la pagina.
 */
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { apiClient, type Device } from "@/api/client";
import { DeviceCard } from "@/components/DeviceCard";
import { useDeviceStream } from "@/hooks/useDeviceStream";
import { Button } from "@/components/ui/button";

async function fetchDevices(): Promise<Device[]> {
  const response = await apiClient.get<Device[]>("/devices");
  return response.data;
}

export function DashboardPage() {
  const navigate = useNavigate();

  const { data: devices, isLoading, isError } = useQuery({
    queryKey: ["devices"],
    queryFn: fetchDevices,
    refetchInterval: 30_000, // Refetch cada 30s como fallback si SSE falla
  });

  // SSE: actualiza el cache de TanStack Query en tiempo real
  useDeviceStream();

  const handleLogout = () => {
    localStorage.removeItem("token");
    navigate("/login", { replace: true });
  };

  // Resumen de estados
  const upCount = devices?.filter((d) => d.status === "up").length ?? 0;
  const downCount = devices?.filter((d) => d.status === "down").length ?? 0;
  const warningCount = devices?.filter((d) => d.status === "warning").length ?? 0;

  return (
    <div className="min-h-screen bg-slate-950 text-slate-50">
      {/* Header */}
      <header className="border-b border-slate-800 px-6 py-3 flex items-center justify-between">
        <h1 className="text-lg font-semibold">BEEPYRED NOC</h1>
        <nav className="flex items-center gap-4">
          <Button variant="ghost" size="sm" onClick={() => navigate("/inventory")}>
            Inventario
          </Button>
          <Button variant="ghost" size="sm" onClick={() => navigate("/incidents")}>
            Incidentes
          </Button>
          <Button variant="outline" size="sm" onClick={handleLogout}>
            Salir
          </Button>
        </nav>
      </header>

      <main className="p-6">
        {/* Resumen */}
        <div className="flex gap-4 mb-6">
          <div className="text-center">
            <p className="text-2xl font-bold text-green-400">{upCount}</p>
            <p className="text-xs text-muted-foreground">UP</p>
          </div>
          <div className="text-center">
            <p className="text-2xl font-bold text-red-400">{downCount}</p>
            <p className="text-xs text-muted-foreground">DOWN</p>
          </div>
          <div className="text-center">
            <p className="text-2xl font-bold text-yellow-400">{warningCount}</p>
            <p className="text-xs text-muted-foreground">WARNING</p>
          </div>
          <div className="text-center">
            <p className="text-2xl font-bold">{devices?.length ?? 0}</p>
            <p className="text-xs text-muted-foreground">TOTAL</p>
          </div>
        </div>

        {/* Grid de dispositivos */}
        {isLoading && <p className="text-muted-foreground">Cargando equipos...</p>}
        {isError && <p className="text-red-500">Error al cargar equipos. Verificar conexion.</p>}
        {devices && devices.length === 0 && (
          <p className="text-muted-foreground">
            No hay equipos en el inventario.{" "}
            <Button variant="link" onClick={() => navigate("/inventory")}>
              Agregar equipos
            </Button>
          </p>
        )}
        {devices && devices.length > 0 && (
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3">
            {devices.map((device) => (
              <DeviceCard key={device.id} device={device} />
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
