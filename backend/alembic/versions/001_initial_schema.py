"""Initial schema: devices, device_credentials, metrics, alerts, incidents, onus

Revision ID: 001
Revises:
Create Date: 2026-04-25

DECISION: PostgreSQL puro sin TimescaleDB.
- metrics.recorded_at usa BRIN index (Block Range INdex) — eficiente para
  columnas de timestamp con insercion en orden cronologico.
- La retencion de datos (30 dias) se implementa via Celery beat task en Phase 2.
"""
from alembic import op
import sqlalchemy as sa

revision: str = "001"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # ── Enums ──────────────────────────────────────────────────────────────────
    devicetype = sa.Enum(
        "mikrotik", "olt_vsol_gpon", "olt_vsol_epon", "onu",
        "ubiquiti", "mimosa", "other",
        name="devicetype"
    )
    devicestatus = sa.Enum(
        "up", "down", "warning", "unknown",
        name="devicestatus"
    )
    devicetype.create(op.get_bind(), checkfirst=True)
    devicestatus.create(op.get_bind(), checkfirst=True)

    # ── Tabla devices ──────────────────────────────────────────────────────────
    op.create_table(
        "devices",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("ip_address", sa.String(45), nullable=False),
        sa.Column("device_type", sa.Enum("mikrotik", "olt_vsol_gpon", "olt_vsol_epon",
                                         "onu", "ubiquiti", "mimosa", "other",
                                         name="devicetype"), nullable=False),
        sa.Column("site", sa.String(255), nullable=True),
        sa.Column("status", sa.Enum("up", "down", "warning", "unknown",
                                    name="devicestatus"), nullable=False, server_default="unknown"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("consecutive_failures", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("parent_device_id", sa.Integer,
                  sa.ForeignKey("devices.id", ondelete="SET NULL"), nullable=True),
        sa.Column("pon_port", sa.String(50), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
    )
    # Indices para queries del dashboard
    op.create_index("idx_devices_status", "devices", ["status"])
    op.create_index("idx_devices_site", "devices", ["site"])
    op.create_index("idx_devices_type", "devices", ["device_type"])
    op.create_index("idx_devices_active", "devices", ["is_active"])

    # ── Tabla device_credentials ───────────────────────────────────────────────
    op.create_table(
        "device_credentials",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("device_id", sa.Integer,
                  sa.ForeignKey("devices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("credential_type", sa.String(50), nullable=False),
        sa.Column("username", sa.String(255), nullable=True),
        sa.Column("encrypted_password", sa.Text, nullable=True),
        sa.Column("encrypted_api_key", sa.Text, nullable=True),
        sa.Column("port", sa.Integer, nullable=True),
    )
    # Unique: un solo registro por tipo de credencial por equipo
    op.create_index(
        "idx_device_credentials_unique",
        "device_credentials",
        ["device_id", "credential_type"],
        unique=True
    )

    # ── Tabla metrics ──────────────────────────────────────────────────────────
    # PostgreSQL puro — sin TimescaleDB. BRIN index en recorded_at para
    # eficiencia en series temporales con insercion cronologica.
    op.create_table(
        "metrics",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("device_id", sa.Integer,
                  sa.ForeignKey("devices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("metric_name", sa.String(100), nullable=False),
        sa.Column("value", sa.Numeric(precision=12, scale=4), nullable=False),
        sa.Column("unit", sa.String(20), nullable=True),
        sa.Column("interface", sa.String(100), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
    )
    # Indice compuesto para queries de tendencias (device + tiempo descendente)
    op.create_index(
        "idx_metrics_device_recorded",
        "metrics",
        ["device_id", sa.text("recorded_at DESC")]
    )
    # BRIN index en recorded_at — Block Range INdex, muy eficiente para timestamps
    # en orden cronologico de insercion. pages_per_range=128 es el default de PostgreSQL.
    # No requiere extensiones — disponible en PostgreSQL estandar Railway.
    op.create_index(
        "idx_metrics_recorded_at_brin",
        "metrics",
        ["recorded_at"],
        postgresql_using="brin",
        postgresql_with={"pages_per_range": 128},
    )

    # ── Tabla alerts ───────────────────────────────────────────────────────────
    op.create_table(
        "alerts",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("device_id", sa.Integer,
                  sa.ForeignKey("devices.id", ondelete="CASCADE"), nullable=True),
        sa.Column("alert_type", sa.String(100), nullable=False),
        sa.Column("threshold_value", sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("consecutive_polls_required", sa.Integer, nullable=False, server_default="3"),
    )

    # ── Tabla incidents ────────────────────────────────────────────────────────
    op.create_table(
        "incidents",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("device_id", sa.Integer,
                  sa.ForeignKey("devices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_seconds", sa.Integer, nullable=True),
        sa.Column("cause", sa.Text, nullable=True),
        sa.Column("alert_sent", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("recovery_alert_sent", sa.Boolean, nullable=False, server_default="false"),
    )
    # Indice para incidentes activos (resolved_at IS NULL = abiertos)
    op.create_index(
        "idx_incidents_active",
        "incidents",
        ["device_id", "resolved_at"],
        postgresql_where=sa.text("resolved_at IS NULL")
    )
    op.create_index("idx_incidents_started", "incidents", [sa.text("started_at DESC")])

    # ── Tabla onus ─────────────────────────────────────────────────────────────
    op.create_table(
        "onus",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("device_id", sa.Integer,
                  sa.ForeignKey("devices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("olt_id", sa.Integer,
                  sa.ForeignKey("devices.id", ondelete="SET NULL"), nullable=True),
        sa.Column("serial_number", sa.String(100), nullable=True),
        sa.Column("pon_port", sa.String(50), nullable=True),
        sa.Column("signal_rx_dbm", sa.Numeric(precision=8, scale=4), nullable=True),
        sa.Column("signal_tx_dbm", sa.Numeric(precision=8, scale=4), nullable=True),
        sa.Column("onu_status", sa.String(50), nullable=True),
        sa.Column("last_updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_onus_olt", "onus", ["olt_id", "pon_port"])
    op.create_index("idx_onus_device", "onus", ["device_id"])


def downgrade() -> None:
    op.drop_table("onus")
    op.drop_table("incidents")
    op.drop_table("alerts")
    op.drop_table("metrics")
    op.drop_table("device_credentials")
    op.drop_table("devices")
    sa.Enum(name="devicestatus").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="devicetype").drop(op.get_bind(), checkfirst=True)
