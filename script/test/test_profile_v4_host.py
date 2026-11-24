"""Compile actual profile v4 UART1 role, NVS migration and recovery guards."""
import argparse
import os
import subprocess
from test_profile_host import HARNESS_PREFIX, compiled_harness

HARNESS = HARNESS_PREFIX + r'''
static unsigned command4(int op,unsigned id,const extended_t *m) {
    uint8_t p[36]={4,(uint8_t)op};put32(p+2,id);if(m)encode4(p+6,m);
    ubcp_frame_t req={.payload=p,.payload_len=(uint16_t)(m?sizeof(p):op<=READ?2:6)};
    profile_command(&req);return reply[0];
}
static unsigned command3(int op,unsigned id,const extended_t *m) {
    uint8_t p[35]={3,(uint8_t)op};put32(p+2,id);if(m)encode3(p+6,m);
    ubcp_frame_t req={.payload=p,.payload_len=(uint16_t)(m?sizeof(p):op<=READ?2:6)};
    profile_command(&req);return reply[0];
}
static unsigned command2(int op,unsigned id,const extended_t *m) {
    uint8_t p[32]={2,(uint8_t)op};put32(p+2,id);if(m)encode(p+6,m);
    ubcp_frame_t req={.payload=p,.payload_len=(uint16_t)(m?sizeof(p):op<=READ?2:6)};
    profile_command(&req);return reply[0];
}
static void fresh(void) {
    disk_len=0;clock_us=0;credentials=true;tcp=false;session_current=true;fail_write=false;profile_init();
}
static extended_t business(void) {
    extended_t m=active;m.uart1_business=1;m.legacy.mask_lo&=~PF_SERIAL;return m;
}
static unsigned stage(const extended_t *m) {
    assert(command4(SAVE,state.revision,m)==0);return get32(reply+1);
}
static void boot(unsigned id) {
    assert(command4(APPLY,id,NULL)==0);profile_init();assert(state.phase==TRIAL);
}
static void readiness(void) {profile_boot_ready();profile_network_ready();}
static void assert_old_writes_rejected(unsigned id) {
    unsigned rev=state.revision,phase=state.phase;
    for(int op=CHECK;op<=CONFIRM;op++) {
        unsigned key=op<=SAVE?rev:id;
        const extended_t *m=op<=SAVE?&active:NULL;
        assert(command3(op,key,m)==UBCP_ERR_NOT_SUPPORT);
        assert(command2(op,key,m)==UBCP_ERR_NOT_SUPPORT);
        assert(command(op,key,m?&m->legacy:NULL)==UBCP_ERR_NOT_SUPPORT);
        assert(state.revision==rev&&state.phase==phase);
    }
}
static void validate_role_and_network_entry(void) {
    fresh();assert(command4(DESCRIBE,0,NULL)==0&&length==82&&reply[1]==4);
    assert(get32(reply+6)==127&&reply[10]==0&&reply[11]==30&&reply[41]==0);
    assert(command4(READ,0,NULL)==0&&length==44&&!active.uart1_business);
    extended_t m=active;m.uart1_business=1;
    assert(command4(CHECK,state.revision,&m)==UBCP_ERR_PARAM&&reply[2]==10);
    assert(!disk_len&&state.revision==1);
    m=business();m.uart1_business=2;
    assert(command4(CHECK,state.revision,&m)==UBCP_ERR_PARAM);
    m=business();assert(command4(CHECK,state.revision,&m)==0);
    credentials=false;
    assert(command4(CHECK,state.revision,&m)==UBCP_ERR_PARAM);credentials=true;
    m.legacy.mask_lo&=~PF_WIFI;assert(command4(CHECK,state.revision,&m)==UBCP_ERR_PARAM);
    m=business();m.legacy.mask_lo&=~PF_CONTROL_TCP;assert(command4(CHECK,state.revision,&m)==UBCP_ERR_PARAM);
    m=business();fail_write=true;assert(command4(SAVE,state.revision,&m)==UBCP_ERR_UNKNOWN);
    assert(!disk_len&&state.revision==1&&!active.uart1_business);fail_write=false;
    unsigned id=stage(&m);assert(!active.uart1_business&&profile_enabled(PF_SERIAL));
    assert(command4(READ,0,NULL)==0&&length==74&&reply[43]==0&&reply[73]==1);
    assert_old_writes_rejected(id);boot(id);
    assert(active.uart1_business&&!profile_enabled(PF_SERIAL)&&profile_enabled(PF_UART));
    assert(command4(CONFIRM,id,NULL)==UBCP_ERR_BUSY);
    profile_boot_ready();assert(command4(CONFIRM,id,NULL)==UBCP_ERR_BUSY);
    profile_network_ready();assert(command4(CONFIRM,id,NULL)==UBCP_ERR_PERMISSION);
    tcp=true;session_current=false;assert(command4(CONFIRM,id,NULL)==UBCP_ERR_PERMISSION);
    session_current=true;assert(command4(CONFIRM,id,NULL)==0);
    assert(command4(CONFIRM,id,NULL)==0);profile_init();assert(active.uart1_business);
    assert_old_writes_rejected(0);
    /* Disabling business and restoring UART1 management is also transactional. */
    m=active;m.uart1_business=0;m.legacy.mask_lo|=PF_SERIAL;id=stage(&m);boot(id);readiness();
    assert_old_writes_rejected(id); /* confirmed rollback snapshot still owns UART1 business */
    assert(command4(CONFIRM,id,NULL)==UBCP_ERR_PERMISSION);tcp=false;
    assert(command4(CONFIRM,id,NULL)==0);profile_init();assert(!active.uart1_business&&profile_enabled(PF_SERIAL));
    assert(command3(CHECK,state.revision,&active)==0);
}
static void safe_recovery(void) {
    fresh();extended_t m=business();unsigned id=stage(&m);boot(id);
    profile_init();assert(!active.uart1_business&&profile_enabled(PF_SERIAL)&&state.phase==IDLE);
    id=stage(&m);boot(id);profile_driver_failed();profile_init();
    assert(!active.uart1_business&&profile_enabled(PF_SERIAL));
    id=stage(&m);boot(id);readiness();tcp=true;clock_us=deadline;
    assert(command4(CONFIRM,id,NULL)==UBCP_ERR_TIMEOUT);profile_init();
    assert(!active.uart1_business&&profile_enabled(PF_SERIAL));
    id=stage(&m);record_t *saved=(record_t*)disk;saved->candidate.uart1_business=2;
    saved->candidate_checksum=mapping_checksum(&saved->candidate);saved->checksum=checksum(saved);
    profile_init();assert(!active.uart1_business&&state.phase==IDLE);
    saved=(record_t*)disk;saved->confirmed.uart1_business=2;
    saved->confirmed_checksum=mapping_checksum(&saved->confirmed);saved->checksum=checksum(saved);
    profile_init();assert(state.revision==1&&!active.uart1_business&&profile_enabled(PF_SERIAL));
    /* A confirmed UART1 business role must also return control if credentials vanish. */
    m=business();id=stage(&m);boot(id);readiness();tcp=true;
    assert(command4(CONFIRM,id,NULL)==0);credentials=false;profile_init();
    assert(!active.uart1_business&&profile_enabled(PF_SERIAL));
}
static void migrate_v3(void) {
    fresh();record_v3_t old={0};old.version=3;old.revision=21;
    memcpy(&old.confirmed,&active,sizeof(old.confirmed));old.confirmed.bus[0].width=1;
    old.confirmed_checksum=v3_mapping_checksum(&old.confirmed);
    old.candidate_checksum=v3_mapping_checksum(&old.candidate);old.checksum=v3_checksum(&old);
    memcpy(disk,&old,sizeof(old));disk_len=sizeof(old);profile_init();
    assert(state.revision==21&&!active.uart1_business&&profile_spi_width(2)==1);
    /* Old 96-byte v3 and current 96-byte v4 records are distinguished by version. */
    assert(state.version==6);
    old.phase=STAGED;old.candidate_id=90;old.saved_from=21;
    old.candidate=old.confirmed;old.candidate.external_cs=255;
    old.candidate_checksum=v3_mapping_checksum(&old.candidate);old.checksum=v3_checksum(&old);
    memcpy(disk,&old,sizeof(old));disk_len=sizeof(old);profile_init();
    assert(state.phase==STAGED&&!active.uart1_business&&!state.candidate.uart1_business);
    assert(state.candidate.external_cs==255);
    old.phase=ARMED;old.checksum=v3_checksum(&old);
    memcpy(disk,&old,sizeof(old));disk_len=sizeof(old);profile_init();
    assert(state.phase==TRIAL&&!active.uart1_business&&profile_spi_device_cs(0)==255);
    profile_init();assert(state.phase==IDLE&&profile_spi_device_cs(0)==27);
    old.phase=STAGED;old.candidate.external2_host=4;
    old.candidate_checksum=v3_mapping_checksum(&old.candidate);old.checksum=v3_checksum(&old);
    memcpy(disk,&old,sizeof(old));disk_len=sizeof(old);profile_init();
    assert(state.phase==IDLE&&!active.uart1_business&&profile_spi_width(2)==1);
    old.confirmed.legacy.pin[SIG_UART_TX]=4;
    old.confirmed_checksum=v3_mapping_checksum(&old.confirmed);old.checksum=v3_checksum(&old);
    memcpy(disk,&old,sizeof(old));disk_len=sizeof(old);profile_init();
    assert(state.revision==1&&!active.uart1_business&&profile_pin(SIG_UART_TX)==32);
}
int main(void) {validate_role_and_network_entry();safe_recovery();migrate_v3();return 0;}
'''


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('compiler',nargs='?',default='cl' if os.name=='nt' else 'cc')
    args=parser.parse_args()
    with compiled_harness(args.compiler,HARNESS) as binary:
        subprocess.run([str(binary)],check=True)
    print('Profile v4 UART1 role, network confirmation, v3 migration and recovery: PASS')


if __name__=='__main__':
    main()
