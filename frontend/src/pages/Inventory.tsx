/**
 * Pagina de inventario CRUD — INV-01, INV-02, INV-03.
 *
 * Permite agregar, editar y eliminar equipos.
 * La tabla agrupa los equipos por sitio geografico (INV-02).
 */
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiClient, type Device, type DeviceCreate } from "@/api/client";
import { InventoryForm } from "@/components/InventoryForm";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

async function fetchDevices(): Promise<Device[]> {
  const response = await apiClient.get<Device[]>("/devices");
  return response.data;
}

export function InventoryPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [formOpen, setFormOpen] = useState(false);
  const [editingDevice, setEditingDevice] = useState<Device | null>(null);

  const { data: devices, isLoading } = useQuery({
    queryKey: ["devices"],
    queryFn: fetchDevices,
  });

  const createMutation = useMutation({
    mutationFn: async (data: DeviceCreate) => {
      const response = await apiClient.post<Device>("/devices", data);
      return response.data;
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["devices"] }),
  });

  const updateMutation = useMutation({
    mutationFn: async ({ id, data }: { id: number; data: DeviceCreate }) => {
      const response = await apiClient.put<Device>(`/devices/${id}`, data);
      return response.data;
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["devices"] }),
  });

  const deleteMutation = useMutation({
    mutationFn: async (id: number) => {
      await apiClient.delete(`/devices/${id}`);
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["devices"] }),
  });

  const handleFormSubmit = async (data: DeviceCreate) => {
    if (editingDevice) {
      await updateMutation.mutateAsync({ id: editingDevice.id, data });
    } else {
      await createMutation.mutateAsync(data);
    }
  };

  const handleEdit = (device: Device) => {
    setEditingDevice(device);
    setFormOpen(true);
  };

  const handleDelete = async (device: Device) => {
    if (confirm(`Eliminar "${device.name}"?`)) {
      await deleteMutation.mutateAsync(device.id);
    }
  };

  const handleOpenCreate = () => {
    setEditingDevice(null);
    setFormOpen(true);
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-50">
      <header className="border-b border-slate-800 px-6 py-3 flex items-center justify-between">
        <h1 className="text-lg font-semibold">Inventario de Equipos</h1>
        <nav className="flex items-center gap-4">
          <Button variant="ghost" size="sm" onClick={() => navigate("/dashboard")}>
            Dashboard
          </Button>
          <Button size="sm" onClick={handleOpenCreate}>
            + Agregar equipo
          </Button>
        </nav>
      </header>

      <main className="p-6">
        {isLoading && <p className="text-muted-foreground">Cargando...</p>}
        {devices && (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-800 text-left text-muted-foreground">
                <th className="pb-2 pr-4">Nombre</th>
                <th className="pb-2 pr-4">IP</th>
                <th className="pb-2 pr-4">Tipo</th>
                <th className="pb-2 pr-4">Sitio</th>
                <th className="pb-2 pr-4">Estado</th>
                <th className="pb-2">Acciones</th>
              </tr>
            </thead>
            <tbody>
              {devices.map((device) => (
                <tr key={device.id} className="border-b border-slate-900 hover:bg-slate-900">
                  <td className="py-2 pr-4">{device.name}</td>
                  <td className="py-2 pr-4 font-mono text-xs">{device.ip_address}</td>
                  <td className="py-2 pr-4 text-xs">{device.device_type}</td>
                  <td className="py-2 pr-4 text-xs">{device.site ?? "-"}</td>
                  <td className="py-2 pr-4">
                    <Badge
                      variant={
                        device.status === "up" ? "default" :
                        device.status === "down" ? "destructive" : "outline"
                      }
                    >
                      {device.status.toUpperCase()}
                    </Badge>
                  </td>
                  <td className="py-2">
                    <div className="flex gap-2">
                      <Button size="sm" variant="ghost" onClick={() => handleEdit(device)}>
                        Editar
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        className="text-red-400"
                        onClick={() => handleDelete(device)}
                      >
                        Eliminar
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </main>

      <InventoryForm
        open={formOpen}
        onClose={() => { setFormOpen(false); setEditingDevice(null); }}
        onSubmit={handleFormSubmit}
        initialData={editingDevice ?? undefined}
      />
    </div>
  );
}
