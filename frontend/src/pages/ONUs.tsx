/**
 * Pagina de ONUs GPON — VSOL-01/03.
 * Lista ONUs con filtros por sitio y estado, tabla con señal optica.
 * Consume GET /api/v1/onus con paginacion.
 */
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/api/client";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

interface ONU {
  id: number;
  device_id: number;
  olt_id: number | null;
  serial_number: string | null;
  pon_port: string | null;
  onu_index: number | null;
  signal_rx_dbm: number | null;
  signal_tx_dbm: number | null;
  onu_status: string | null;
  last_updated_at: string | null;
  device_name: string | null;
  site: string | null;
  olt_name: string | null;
}

const STATE_VARIANTS: Record<string, "default" | "secondary" | "destructive" | "outline"> = {
  ONLINE: "default",
  OFFLINE: "destructive",
  RANGING: "outline",
};

function SignalCell({ dbm }: { dbm: number | null }) {
  if (dbm === null) return <span className="text-slate-500">—</span>;
  const val = Number(dbm);
  const color = val < -28 ? "text-red-400" : val < -25 ? "text-yellow-400" : "text-green-400";
  return <span className={color}>{val.toFixed(2)} dBm</span>;
}

export function ONUsPage() {
  const navigate = useNavigate();
  const [site, setSite] = useState("");
  const [state, setState] = useState("");
  const [page, setPage] = useState(0);
  const PAGE_SIZE = 50;

  const { data: onus = [], isLoading } = useQuery<ONU[]>({
    queryKey: ["onus", site, state, page],
    queryFn: async () => {
      const params = new URLSearchParams();
      if (site) params.append("site", site);
      if (state) params.append("state", state);
      params.append("limit", String(PAGE_SIZE));
      params.append("offset", String(page * PAGE_SIZE));
      const res = await apiClient.get<ONU[]>(`/v1/onus?${params}`);
      return res.data;
    },
  });

  const states = ["", "ONLINE", "OFFLINE", "RANGING"];

  return (
    <div className="min-h-screen bg-slate-950 text-slate-50">
      <header className="border-b border-slate-800 px-6 py-3 flex items-center justify-between">
        <h1 className="text-lg font-semibold">ONUs GPON</h1>
        <nav className="flex items-center gap-4">
          <Button variant="ghost" size="sm" onClick={() => navigate("/dashboard")}>
            Dashboard
          </Button>
          <Button variant="ghost" size="sm" onClick={() => navigate("/inventory")}>
            Inventario
          </Button>
          <Button variant="ghost" size="sm" onClick={() => navigate("/incidents")}>
            Incidentes
          </Button>
        </nav>
      </header>

      <main className="p-6 space-y-4">
        {/* Filtros */}
        <div className="flex items-center gap-2 flex-wrap">
          <Input
            placeholder="Filtrar por sitio..."
            value={site}
            onChange={(e) => { setSite(e.target.value); setPage(0); }}
            className="w-44 bg-slate-900 border-slate-700 text-slate-50 placeholder:text-slate-500"
          />
          <div className="flex gap-1">
            {states.map((s) => (
              <Button
                key={s || "all"}
                variant={state === s ? "default" : "outline"}
                size="sm"
                onClick={() => { setState(s); setPage(0); }}
              >
                {s || "Todos"}
              </Button>
            ))}
          </div>
        </div>

        {/* Tabla */}
        {isLoading ? (
          <p className="text-slate-400">Cargando ONUs...</p>
        ) : onus.length === 0 ? (
          <p className="text-slate-400">No hay ONUs registradas con los filtros actuales.</p>
        ) : (
          <>
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-800 text-left text-slate-400">
                  <th className="pb-2 pr-3">Serial</th>
                  <th className="pb-2 pr-3">Puerto</th>
                  <th className="pb-2 pr-3">Índice</th>
                  <th className="pb-2 pr-3">Estado</th>
                  <th className="pb-2 pr-3">Rx</th>
                  <th className="pb-2 pr-3">Tx</th>
                  <th className="pb-2 pr-3">OLT</th>
                  <th className="pb-2">Sitio</th>
                </tr>
              </thead>
              <tbody>
                {onus.map((onu) => (
                  <tr key={onu.id} className="border-b border-slate-900 hover:bg-slate-900">
                    <td className="py-2 pr-3 font-mono text-xs">{onu.serial_number ?? "—"}</td>
                    <td className="py-2 pr-3 text-xs">{onu.pon_port ?? "—"}</td>
                    <td className="py-2 pr-3 text-xs text-center">{onu.onu_index ?? "—"}</td>
                    <td className="py-2 pr-3">
                      {onu.onu_status ? (
                        <Badge variant={STATE_VARIANTS[onu.onu_status] ?? "secondary"}>
                          {onu.onu_status}
                        </Badge>
                      ) : (
                        <span className="text-slate-500">—</span>
                      )}
                    </td>
                    <td className="py-2 pr-3 text-xs">
                      <SignalCell dbm={onu.signal_rx_dbm} />
                    </td>
                    <td className="py-2 pr-3 text-xs">
                      <SignalCell dbm={onu.signal_tx_dbm} />
                    </td>
                    <td className="py-2 pr-3 text-xs text-slate-300">{onu.olt_name ?? "—"}</td>
                    <td className="py-2 text-xs text-slate-400">{onu.site ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>

            {/* Paginacion */}
            <div className="flex items-center gap-2 pt-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setPage((p) => Math.max(0, p - 1))}
                disabled={page === 0}
              >
                Anterior
              </Button>
              <span className="text-xs text-slate-400">Página {page + 1}</span>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setPage((p) => p + 1)}
                disabled={onus.length < PAGE_SIZE}
              >
                Siguiente
              </Button>
            </div>
          </>
        )}
      </main>
    </div>
  );
}
