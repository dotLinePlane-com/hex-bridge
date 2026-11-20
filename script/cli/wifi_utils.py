"""Wi-Fi STA wire formats from protocol/08-Network.md (no credential logging)."""

WIFI_STA_CAPABILITY = 1 << 12
WIFI_STATES = ('IDLE', 'CONNECTING', 'WAIT_IP', 'IPV4_READY', 'RETRY_WAIT', 'FAILED')
WIFI_REASONS = ('NONE', 'AP_NOT_FOUND', 'AUTH_FAILED', 'LINK_LOST',
                'IP_TIMEOUT', 'DRIVER_ERROR', 'SAVE_FAILED')


def require_wifi_capability(info):
    if len(info) < 14 or info[0] != 0:
        raise ValueError('Invalid GET_INFO response')
    if not int.from_bytes(info[12:14], 'big') & WIFI_STA_CAPABILITY:
        raise ValueError('Firmware does not advertise WIFI_STA (bit 12)')


def build_wifi_join(ssid, key=b'', save=False, auth=1):
    ssid = ssid.encode('utf-8') if isinstance(ssid, str) else bytes(ssid)
    if isinstance(key, str):
        try:
            key = key.encode('ascii')
        except UnicodeEncodeError:
            raise ValueError('WPA2 password must be printable ASCII') from None
    if not 1 <= len(ssid) <= 32:
        raise ValueError('SSID must contain 1-32 UTF-8 bytes')
    if auth not in (0, 1) or save not in (False, True):
        raise ValueError('Invalid Wi-Fi authentication or save mode')
    if auth == 0 and key:
        raise ValueError('Open networks require an empty password')
    if auth == 1 and (not 8 <= len(key) <= 63 or not all(32 <= c <= 126 for c in key)):
        raise ValueError('WPA2 password must contain 8-63 printable ASCII bytes')
    return bytes([0, int(save), auth, len(ssid), len(key)]) + ssid + key


def parse_wifi_status(payload):
    if not payload or payload[0]:
        raise ValueError('WIFI_STATUS did not return success')
    if len(payload) < 6 or payload[5] > 32 or len(payload) != 6 + payload[5]:
        raise ValueError('Invalid WIFI_STATUS length')
    state, reason, channel, rssi = payload[1:5]
    if state >= len(WIFI_STATES) or reason >= len(WIFI_REASONS):
        raise ValueError('Invalid WIFI_STATUS state or reason')
    return dict(state=WIFI_STATES[state], state_code=state,
                reason=WIFI_REASONS[reason], reason_code=reason,
                channel=channel, rssi=rssi if rssi < 128 else rssi - 256,
                ssid=payload[6:].decode('utf-8', errors='replace'))
