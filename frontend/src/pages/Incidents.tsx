/**
 * Pagina de historial de incidentes — INC-03.
 * Lista incidentes con filtros por sitio y estado (abierto/cerrado).
 * Consume GET /api/v1/incidents con paginacion.
 */
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/api/client";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

interface Incident {
  id: number;
  device_id: number;
  device_name: string;
  device_site: string | null;
  started_at: string;
  resolved_at: string | null;
  duration_seconds: number | null;
}

function formatDuration(seconds: number | null): string {
  if (seconds === null) return "—";
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}

export function IncidentsPage() {
  const navigate = useNavigate();
  const [site, setSite] = useState("");
  const [openOnly, setOpenOnly] = useState(false);

  const { data: incidents = [], isLoading } = useQuery<Incident[]>({
    queryKey: ["incidents", site, openOnly],
    queryFn: async () => {
      const params = new URLSearchParams();
      if (site) params.append("site", site);
      if (openOnly) params.append("open_only", "true");
      params.append("limit", "100");
      const res = await apiClient.get<Incident[]>(`/v1/incidents?${params}`);
      return res.data;
    },
  });

  return (
    <div className="min-h-screen bg-slate-950 text-slate-50">
      <header className="border-b border-slate-800 px-6 py-3 flex items-center justify-between">
        <h1 className="text-lg font-semibold">Incidentes</h1>
        <nav className="flex items-center gap-4">
          <Button variant="ghost" size="sm" onClick={() => navigate("/dashboard")}>
            Dashboard
          </Button>
          <Button variant="ghost" size="sm" onClick={() => navigate("/inventory")}>
            Inventario
          </Button>
        </nav>
      </header>

      <main className="p-6 space-y-4">
        {/* Filtros */}
        <div className="flex items-center gap-2">
          <Input
            placeholder="Filtrar por sitio..."
            value={site}
            onChange={(e) => setSite(e.target.value)}
            className="w-48 bg-slate-900 border-slate-700 text-slate-50 placeholder:text-slate-500"
          />
          <Button
            variant={openOnly ? "default" : "outline"}
            size="sm"
            onClick={() => setOpenOnly(!openOnly)}
          >
            {openOnly ? "Solo abiertos (activo)" : "Solo abiertos"}
          </Button>
        </div>

        {/* Tabla */}
        {isLoading ? (
          <p className="text-muted-foreground">Cargando incidentes...</p>
        ) : incidents.length === 0 ? (
          <p className="text-muted-foreground">No hay incidentes registrados.</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-800 text-left text-muted-foreground">
                <th className="pb-2 pr-4">Equipo</th>
                <th className="pb-2 pr-4">Sitio</th>
                <th className="pb-2 pr-4">Inicio</th>
                <th className="pb-2 pr-4">Fin</th>
                <th className="pb-2 pr-4">Duracion</th>
                <th className="pb-2">Estado</th>
              </tr>
            </thead>
            <tbody>
              {incidents.map((inc) => (
                <tr key={inc.id} className="border-b border-slate-900 hover:bg-slate-900">
                  <td className="py-2 pr-4 font-medium">{inc.device_name}</td>
                  <td className="py-2 pr-4 text-xs">{inc.device_site ?? "—"}</td>
                  <td className="py-2 pr-4 text-xs">
                    {new Date(inc.started_at).toLocaleString("es-CO")}
                  </td>
                  <td className="py-2 pr-4 text-xs">
                    {inc.resolved_at
                      ? new Date(inc.resolved_at).toLocaleString("es-CO")
                      : "—"}
                  </td>
                  <td className="py-2 pr-4 text-xs">{formatDuration(inc.duration_seconds)}</td>
                  <td className="py-2">
                    <Badge variant={inc.resolved_at ? "secondary" : "destructive"}>
                      {inc.resolved_at ? "Resuelto" : "Abierto"}
                    </Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </main>
    </div>
  );
}
