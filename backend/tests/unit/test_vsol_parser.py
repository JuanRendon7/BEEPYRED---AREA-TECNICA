"""
Tests para vsol_parser.py — VSOL-01.

Parsers puros de CLI VSOL V2.3.1R. Todos los tests usan strings literales
que simulan la salida real del comando SSH, sin mocks.
"""
import pytest
from app.collectors.vsol_parser import parse_onu_state, parse_optical_info


# ---------------------------------------------------------------------------
# Salidas CLI de ejemplo (simulando hardware VSOL V2.3.1R)
# ---------------------------------------------------------------------------

SAMPLE_ONU_STATE_PORT1 = """\
 ONU-index          SN               Auth-type  ONU-state  ONU-status  Distance(m)
 ---------------------------------------------------------------------------------
 gpon-onu_0/1:1     4857454c12345601  SN         ONLINE     OK          1234
 gpon-onu_0/1:2     4857454c12345602  SN         OFFLINE    -           -
 gpon-onu_0/1:3     4857454c12345603  SN         RANGING    -           -
"""

SAMPLE_ONU_STATE_ONLY_ONLINE = """\
 ONU-index          SN               Auth-type  ONU-state  ONU-status  Distance(m)
 ---------------------------------------------------------------------------------
 gpon-onu_0/2:5     ABCDEF1234567890  SN         ONLINE     OK          800
"""

SAMPLE_ONU_STATE_EMPTY = """\
 ONU-index          SN               Auth-type  ONU-state  ONU-status  Distance(m)
 ---------------------------------------------------------------------------------
"""

SAMPLE_OPTICAL_BOTH = """\
ONU-index           : gpon-onu_0/1:1
Rx power(dBm)       : -19.47
Tx power(dBm)       :  2.00
OLT Rx power(dBm)   : -21.34
Temperature(C)      :  50
Voltage(V)          :  3.26
Bias-current(mA)    : 15.21
"""

SAMPLE_OPTICAL_LOW_SIGNAL = """\
ONU-index           : gpon-onu_0/1:2
Rx power(dBm)       : -29.50
Tx power(dBm)       :  1.80
OLT Rx power(dBm)   : -30.10
"""

SAMPLE_OPTICAL_NO_DATA = """\
ONU-index           : gpon-onu_0/1:3
"""

SAMPLE_OPTICAL_EMPTY = ""


# ---------------------------------------------------------------------------
# Tests de parse_onu_state
# ---------------------------------------------------------------------------

class TestParseOnuState:
    def test_online_onu_parsed(self):
        result = parse_onu_state(SAMPLE_ONU_STATE_PORT1, port=1)
        online = [o for o in result if o["state"] == "ONLINE"]
        assert len(online) == 1
        assert online[0]["serial_number"] == "4857454c12345601"
        assert online[0]["onu_index"] == 1
        assert online[0]["port"] == 1

    def test_offline_onu_parsed(self):
        result = parse_onu_state(SAMPLE_ONU_STATE_PORT1, port=1)
        offline = [o for o in result if o["state"] == "OFFLINE"]
        assert len(offline) == 1
        assert offline[0]["serial_number"] == "4857454c12345602"
        assert offline[0]["onu_index"] == 2

    def test_ranging_onu_parsed(self):
        result = parse_onu_state(SAMPLE_ONU_STATE_PORT1, port=1)
        ranging = [o for o in result if o["state"] == "RANGING"]
        assert len(ranging) == 1
        assert ranging[0]["serial_number"] == "4857454c12345603"
        assert ranging[0]["onu_index"] == 3

    def test_total_count(self):
        result = parse_onu_state(SAMPLE_ONU_STATE_PORT1, port=1)
        assert len(result) == 3

    def test_port_number_extracted_from_index(self):
        result = parse_onu_state(SAMPLE_ONU_STATE_ONLY_ONLINE, port=2)
        assert len(result) == 1
        assert result[0]["port"] == 2

    def test_onu_index_extracted_correctly(self):
        result = parse_onu_state(SAMPLE_ONU_STATE_ONLY_ONLINE, port=2)
        assert result[0]["onu_index"] == 5

    def test_serial_16_chars(self):
        result = parse_onu_state(SAMPLE_ONU_STATE_ONLY_ONLINE, port=2)
        assert len(result[0]["serial_number"]) == 16

    def test_header_lines_ignored(self):
        result = parse_onu_state(SAMPLE_ONU_STATE_PORT1, port=1)
        # Solo deben haber ONUs, no líneas de cabecera
        for onu in result:
            assert "serial_number" in onu
            assert "state" in onu

    def test_empty_table_returns_empty_list(self):
        result = parse_onu_state(SAMPLE_ONU_STATE_EMPTY, port=3)
        assert result == []

    def test_empty_string_returns_empty_list(self):
        result = parse_onu_state("", port=1)
        assert result == []

    def test_none_like_empty_returns_empty_list(self):
        result = parse_onu_state("   \n\n  ", port=1)
        assert result == []

    def test_all_three_states_present(self):
        result = parse_onu_state(SAMPLE_ONU_STATE_PORT1, port=1)
        states = {o["state"] for o in result}
        assert states == {"ONLINE", "OFFLINE", "RANGING"}


# ---------------------------------------------------------------------------
# Tests de parse_optical_info
# ---------------------------------------------------------------------------

class TestParseOpticalInfo:
    def test_rx_dbm_parsed(self):
        result = parse_optical_info(SAMPLE_OPTICAL_BOTH)
        assert result is not None
        assert result["signal_rx_dbm"] == pytest.approx(-19.47)

    def test_tx_dbm_parsed(self):
        result = parse_optical_info(SAMPLE_OPTICAL_BOTH)
        assert result is not None
        assert result["signal_tx_dbm"] == pytest.approx(2.00)

    def test_both_keys_present(self):
        result = parse_optical_info(SAMPLE_OPTICAL_BOTH)
        assert "signal_rx_dbm" in result
        assert "signal_tx_dbm" in result

    def test_negative_rx_signal_parsed(self):
        result = parse_optical_info(SAMPLE_OPTICAL_LOW_SIGNAL)
        assert result is not None
        assert result["signal_rx_dbm"] == pytest.approx(-29.50)

    def test_no_data_returns_none(self):
        result = parse_optical_info(SAMPLE_OPTICAL_NO_DATA)
        assert result is None

    def test_empty_string_returns_none(self):
        result = parse_optical_info(SAMPLE_OPTICAL_EMPTY)
        assert result is None

    def test_result_is_dict_or_none(self):
        result = parse_optical_info(SAMPLE_OPTICAL_BOTH)
        assert isinstance(result, dict)

    def test_values_are_floats(self):
        result = parse_optical_info(SAMPLE_OPTICAL_BOTH)
        assert isinstance(result["signal_rx_dbm"], float)
        assert isinstance(result["signal_tx_dbm"], float)
