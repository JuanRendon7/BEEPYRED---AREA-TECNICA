"""
Parsers puros de CLI VSOL V2.3.1R.

Funciones sin efectos secundarios: reciben stdout como string,
devuelven estructuras Python. Sin I/O, sin mocks necesarios en tests.
"""
import re
from typing import Optional

_ONU_ROW = re.compile(
    r"gpon-onu_\d+/(\d+):(\d+)\s+([0-9A-Fa-f]{16})\s+\S+\s+(ONLINE|OFFLINE|RANGING)"
)
_RX_POWER = re.compile(r"^\s*Rx power\(dBm\)\s*:\s*(-?\d+\.?\d*)", re.MULTILINE)
_TX_POWER = re.compile(r"^\s*Tx power\(dBm\)\s*:\s*(-?\d+\.?\d*)", re.MULTILINE)


def parse_onu_state(stdout: str, port: int) -> list[dict]:
    """Extrae lista de ONUs desde la salida de 'show pon onu state gpon 0/X'."""
    result = []
    for m in _ONU_ROW.finditer(stdout):
        result.append({
            "port": int(m.group(1)),
            "onu_index": int(m.group(2)),
            "serial_number": m.group(3),
            "state": m.group(4),
        })
    return result


def parse_optical_info(stdout: str) -> Optional[dict]:
    """Extrae Rx/Tx dBm desde 'show pon optical-info gpon 0/X onu N'. None si sin datos."""
    rx_m = _RX_POWER.search(stdout)
    tx_m = _TX_POWER.search(stdout)
    if not rx_m and not tx_m:
        return None
    info: dict = {}
    if rx_m:
        info["signal_rx_dbm"] = float(rx_m.group(1))
    if tx_m:
        info["signal_tx_dbm"] = float(tx_m.group(1))
    return info
