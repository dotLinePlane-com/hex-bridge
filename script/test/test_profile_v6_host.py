"""Compile the v6 profile handler and exercise its wire format and NVS upgrade."""
import argparse
import os
import subprocess

from test_profile_host import HARNESS_PREFIX, compiled_harness


HARNESS = HARNESS_PREFIX + r"""
static uint8_t request6(int op, uint32_t id, const extended_t *m) {
    uint8_t data[122] = {6, op};
    put32(data + 2, id);
    if (m) encode6(data + 6, m);
    ubcp_frame_t frame = {.payload=data, .payload_len=m ? sizeof(data) : op <= READ ? 2 : 6};
    profile_command(&frame);
    return reply[0];
}
static void migrate5(void) {
    record_v5_t old = {0};
    uint8_t wire[34];
    old.version = 5;
    old.revision = 27;
    old.phase = STAGED;
    old.confirmed_id = 14;
    old.candidate_id = 26;
    memcpy(&old.confirmed, &active, sizeof(old.confirmed));
    encode5(wire, &active);
    old.confirmed_checksum = crc(wire, sizeof(wire));
    old.candidate = old.confirmed;
    old.candidate.bus[0].width = 1;
    wire[7] = 1;
    old.candidate_checksum = crc(wire, sizeof(wire));
    old.checksum = crc(&old, offsetof(record_v5_t, checksum));
    memcpy(disk, &old, sizeof(old));
    disk_len = sizeof(old);
    profile_init();
    assert(state.revision == 27 && state.confirmed_id == 14 && state.candidate_id == 26);
    assert(request6(READ, 0, NULL) == 0 && length == 246);
    assert(reply[14+7] == 4 && reply[14+116+7] == 1);
    for (int i=0; i<14; ++i) {
        assert(reply[14+46+5*i] == 255 && reply[14+116+46+5*i] == 255);
    }
    assert(request6(CANCEL, 26, NULL) == 0 && state.phase == IDLE);
}
int main(void) {
    profile_init();
    assert(request6(DESCRIBE, 0, NULL) == 0 && length == 168);
    assert(get32(reply+6) == 0x7ff && reply[11] == 116);
    migrate5();
    extended_t m=active;
    m.bus[0].enabled = m.external_enabled = 0;
    m.i2c[0]=(profile_i2c_t){1,18,19,0,0,100};
    m.i2c[1]=(profile_i2c_t){1,21,22,1,3,232};
    m.gpio[13]=(profile_gpio_t){27,3,0,0,0};
    assert(request6(CHECK, state.revision, &m)==0);
    m.gpio[0]=m.gpio[13];
    assert(request6(CHECK, state.revision, &m)==2 && reply[1] && reply[2]==6);
    m.gpio[0]=active.gpio[0];
    m.i2c[0].scl=36;
    assert(request6(CHECK, state.revision, &m)==2 && reply[2]==5);
    m.i2c[0].scl=18;
    fail_write=true;
    assert(request6(SAVE, state.revision, &m)==UBCP_ERR_UNKNOWN && !state.candidate_id);
    fail_write=false;
    assert(request6(SAVE, state.revision, &m)==0);
    unsigned id=get32(reply+1);
    assert(command(CANCEL,id,NULL)==UBCP_ERR_NOT_SUPPORT);
    assert(request6(APPLY,id,NULL)==0);
    profile_init();
    assert(state.phase==TRIAL && profile_i2c(1)->sda==22 && profile_gpio(13)->pin==27);
    profile_boot_ready(); profile_network_ready();
    assert(request6(CONFIRM,id,NULL)==0);
    profile_init();
    assert(state.phase==IDLE && !state.candidate_id && profile_i2c(0)->enabled);
    assert(request6(READ,0,NULL)==0 && length==130);
    return 0;
}
"""


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("compiler", nargs="?", default="cl" if os.name == "nt" else "cc")
    with compiled_harness(parser.parse_args().compiler, HARNESS) as executable:
        subprocess.run([str(executable)], check=True)
    print("PASS v6 mapping, diagnostics, v5 staged migration, old writes and persistence")
