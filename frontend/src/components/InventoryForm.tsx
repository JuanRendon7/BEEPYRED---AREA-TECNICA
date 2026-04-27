/**
 * Formulario modal para crear/editar equipos — INV-01, INV-03.
 */
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import type { Device, DeviceCreate, DeviceType } from "@/api/client";

const DEVICE_TYPES: { value: DeviceType; label: string }[] = [
  { value: "mikrotik", label: "Mikrotik RouterOS" },
  { value: "olt_vsol_gpon", label: "OLT VSOL GPON" },
  { value: "olt_vsol_epon", label: "OLT VSOL EPON" },
  { value: "onu", label: "ONU" },
  { value: "ubiquiti", label: "Ubiquiti" },
  { value: "mimosa", label: "Mimosa" },
  { value: "other", label: "Otro" },
];

interface InventoryFormProps {
  open: boolean;
  onClose: () => void;
  onSubmit: (data: DeviceCreate) => Promise<void>;
  initialData?: Device;
}

export function InventoryForm({
  open,
  onClose,
  onSubmit,
  initialData,
}: InventoryFormProps) {
  const [name, setName] = useState(initialData?.name ?? "");
  const [ipAddress, setIpAddress] = useState(initialData?.ip_address ?? "");
  const [deviceType, setDeviceType] = useState<DeviceType>(
    initialData?.device_type ?? "mikrotik"
  );
  const [site, setSite] = useState(initialData?.site ?? "");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      await onSubmit({
        name,
        ip_address: ipAddress,
        device_type: deviceType,
        site: site || undefined,
      });
      onClose();
    } catch {
      setError("Error al guardar el equipo. Verificar datos.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {initialData ? "Editar equipo" : "Agregar equipo"}
          </DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label>Nombre</Label>
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Router Torre Norte"
              required
            />
          </div>
          <div className="space-y-2">
            <Label>Direccion IP</Label>
            <Input
              value={ipAddress}
              onChange={(e) => setIpAddress(e.target.value)}
              placeholder="192.168.1.1"
              required
            />
          </div>
          <div className="space-y-2">
            <Label>Tipo de equipo</Label>
            <select
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
              value={deviceType}
              onChange={(e) => setDeviceType(e.target.value as DeviceType)}
            >
              {DEVICE_TYPES.map((t) => (
                <option key={t.value} value={t.value}>
                  {t.label}
                </option>
              ))}
            </select>
          </div>
          <div className="space-y-2">
            <Label>Sitio geografico (opcional)</Label>
            <Input
              value={site}
              onChange={(e) => setSite(e.target.value)}
              placeholder="Torre Norte, Nodo Centro..."
            />
          </div>
          {error && <p className="text-sm text-red-500">{error}</p>}
          <div className="flex gap-2 justify-end">
            <Button type="button" variant="outline" onClick={onClose}>
              Cancelar
            </Button>
            <Button type="submit" disabled={loading}>
              {loading ? "Guardando..." : "Guardar"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
