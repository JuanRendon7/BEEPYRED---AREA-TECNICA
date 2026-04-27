/**
 * Tarjeta de un dispositivo con badge de estado UP/DOWN/WARNING/UNKNOWN.
 * INV-04: El estado se actualiza en tiempo real via SSE (hook useDeviceStream).
 */
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { Device, DeviceStatus } from "@/api/client";

const STATUS_LABELS: Record<DeviceStatus, string> = {
  up: "UP",
  down: "DOWN",
  warning: "WARNING",
  unknown: "UNKNOWN",
};

const STATUS_VARIANTS: Record<DeviceStatus, "default" | "destructive" | "outline" | "secondary"> = {
  up: "default",
  down: "destructive",
  warning: "secondary",
  unknown: "outline",
};

interface DeviceCardProps {
  device: Device;
}

export function DeviceCard({ device }: DeviceCardProps) {
  return (
    <Card className="hover:shadow-md transition-shadow">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-medium truncate">
            {device.name}
          </CardTitle>
          <Badge variant={STATUS_VARIANTS[device.status]}>
            {STATUS_LABELS[device.status]}
          </Badge>
        </div>
      </CardHeader>
      <CardContent>
        <p className="text-xs text-muted-foreground font-mono">{device.ip_address}</p>
        <p className="text-xs text-muted-foreground mt-1">
          {device.device_type.replace(/_/g, " ").toUpperCase()}
        </p>
        {device.site && (
          <p className="text-xs text-muted-foreground mt-1">{device.site}</p>
        )}
        {device.status === "down" && (
          <p className="text-xs text-red-500 mt-1">
            Fallos consecutivos: {device.consecutive_failures}
          </p>
        )}
      </CardContent>
    </Card>
  );
}
