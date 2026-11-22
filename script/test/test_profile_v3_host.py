"""Compile actual profile v3: dual SPI devices, no-CS policy and NVS compatibility."""
import argparse
import os
import subprocess
from test_profile_host import HARNESS_PREFIX, compiled_harness

HARNESS = HARNESS_PREFIX + r'''
static unsigned command3(int op, unsigned id, const extended_t *m) {
    uint8_t p[35]={3,(uint8_t)op};put32(p+2,id);
    if(m)encode3(p+6,m);
    ubcp_frame_t req={.payload=p,.payload_len=(uint16_t)(m?sizeof(p):op<=READ?2:6)};
    profile_command(&req);return reply[0];
}
static unsigned command2(int op, unsigned id, const extended_t *m) {
    uint8_t p[32]={2,(uint8_t)op};put32(p+2,id);
    if(m)encode(p+6,m);
    ubcp_frame_t req={.payload=p,.payload_len=(uint16_t)(m?sizeof(p):op<=READ?2:6)};
    profile_command(&req);return reply[0];
}
static void fresh(void) {
    disk_len=0;clock_us=0;credentials=true;tcp=false;session_current=true;fail_write=false;
    profile_init();
}
static unsigned stage3(const extended_t *m) {
    assert(command3(SAVE,state.revision,m)==0);return get32(reply+1);
}
static void confirm3(unsigned id) {
    assert(command3(APPLY,id,NULL)==0);profile_init();
    profile_boot_ready();profile_network_ready();assert(command3(CONFIRM,id,NULL)==0);
}
static void descriptors_and_independent_devices(void) {
    fresh();
    assert(command3(DESCRIBE,0,NULL)==0&&length==81&&reply[1]==3);
    assert(get32(reply+6)==63&&reply[10]==0&&reply[11]==29);
    assert(reply[38]==0&&reply[39]==2&&reply[40]==255);
    assert(command3(READ,0,NULL)==0&&length==43);
    assert(profile_spi_device_enabled(0)&&!profile_spi_device_enabled(1));
    assert(profile_spi_device_host(0)==2&&profile_spi_device_host(1)==2);
    assert(profile_spi_device_cs(0)==27&&profile_spi_device_cs(1)==255);
    extended_t m=active;
    m.legacy.mask_hi=0; /* release DAP GPIO25/26 */
    m.external2_enabled=1;m.external2_host=3;m.external2_cs=25;
    assert(command3(CHECK,state.revision,&m)==0&&!disk_len);
    unsigned id=stage3(&m);
    assert(command3(READ,0,NULL)==0&&length==72&&reply[1]==STAGED);
    assert(!profile_spi_device_enabled(1)); /* saving does not rewire running state */
    unsigned revision=state.revision;
    for(int op=CHECK;op<=CONFIRM;op++) {
        const extended_t *mapping=op<=SAVE?&m:NULL;
        unsigned key=op<=SAVE?revision:id;
        assert(command2(op,key,mapping)==UBCP_ERR_NOT_SUPPORT);
        assert(command(op,key,mapping?&mapping->legacy:NULL)==UBCP_ERR_NOT_SUPPORT);
        assert(state.revision==revision&&state.phase==STAGED&&state.candidate_id==id);
    }
    confirm3(id);profile_init();
    assert(profile_spi_device_enabled(0)&&profile_spi_device_enabled(1));
    assert(profile_spi_device_host(0)==2&&profile_spi_device_host(1)==3);
    assert(profile_spi_device_cs(0)==27&&profile_spi_device_cs(1)==25);
    assert(command(DESCRIBE,0,NULL)==0&&length==57); /* old descriptor stays frozen */
    assert(command2(DESCRIBE,0,NULL)==0&&length==78);
    /* Old clients must not silently drop the enabled second device. */
    assert(command2(SAVE,state.revision,&active)==UBCP_ERR_NOT_SUPPORT);
    assert(command(SAVE,state.revision,&active.legacy)==UBCP_ERR_NOT_SUPPORT);
}
static void no_cs_ownership_and_validation(void) {
    fresh();extended_t m=active;
    m.external_cs=255;
    assert(command2(CHECK,state.revision,&m)==UBCP_ERR_PARAM);
    assert(command3(CHECK,state.revision,&m)==0);
    unsigned id=stage3(&m);confirm3(id);profile_init();
    assert(profile_spi_device_cs(0)==255);
    /* v1/v2 cannot encode or overwrite no-CS semantics. */
    assert(command2(SAVE,state.revision,&active)==UBCP_ERR_NOT_SUPPORT);
    m=active;m.external2_enabled=1;m.external2_host=2;m.external2_cs=25;m.legacy.mask_hi=0;
    assert(command3(CHECK,state.revision,&m)==UBCP_ERR_PARAM&&reply[2]==9);
    m.external2_host=3;m.external2_cs=255;
    assert(command3(CHECK,state.revision,&m)==UBCP_ERR_PARAM&&reply[2]==9); /* CAN on SPI3 */
    m.legacy.mask_lo&=~PF_CAN;
    assert(command3(CHECK,state.revision,&m)==0); /* one no-CS device on each host */
    m.external2_host=2;
    assert(command3(CHECK,state.revision,&m)==UBCP_ERR_PARAM);
    m=active;m.external_cs=27;m.external2_enabled=1;m.external2_host=2;m.external2_cs=27;
    assert(command3(CHECK,state.revision,&m)==UBCP_ERR_PARAM); /* duplicate CS */
    for(unsigned pin=0;pin<40;pin++) {
        if(board[pin]==FLEX)continue;
        m=active;m.external_cs=27;m.external2_cs=pin;
        assert(command3(CHECK,state.revision,&m)==UBCP_ERR_PARAM); /* disabled still retains valid mappings */
    }
    m=active;m.external2_enabled=1;m.external2_host=3;m.external2_cs=25;m.legacy.mask_hi=0;
    m.bus[1].enabled=0;
    assert(command3(CHECK,state.revision,&m)==UBCP_ERR_PARAM); /* device cannot outlive host */
    m=active;m.external2_host=4;
    assert(command3(CHECK,state.revision,&m)==UBCP_ERR_PARAM);
}
static void compatibility_and_recovery(void) {
    fresh();extended_t defaults3=active;
    /* Recreate the exact old NVS ABI, rather than using the new record type. */
    record_v2_t old={0};old.version=2;old.revision=17;
    memcpy(&old.confirmed,&active,sizeof(old.confirmed));
    old.confirmed.bus[0].width=1;
    old.confirmed_checksum=v2_mapping_checksum(&old.confirmed);
    old.candidate_checksum=v2_mapping_checksum(&old.candidate);
    old.checksum=v2_checksum(&old);
    memcpy(disk,&old,sizeof(old));disk_len=sizeof(old);profile_init();
    assert(state.revision==17&&profile_spi_width(2)==1&&!profile_spi_device_enabled(1));
    assert(profile_spi_device_cs(1)==255&&profile_spi_device_host(1)==2);
    /* Staged v2 candidate survives migration; an armed one gets one trial. */
    old.phase=STAGED;old.candidate_id=88;old.saved_from=17;
    old.candidate=old.confirmed;old.candidate.legacy.mask_hi=0;old.candidate.external_cs=25;
    old.candidate_checksum=v2_mapping_checksum(&old.candidate);old.checksum=v2_checksum(&old);
    memcpy(disk,&old,sizeof(old));disk_len=sizeof(old);profile_init();
    assert(state.phase==STAGED&&state.candidate_id==88&&profile_spi_device_cs(0)==27);
    assert(!state.candidate.external2_enabled&&state.candidate.external2_cs==255);
    old.phase=ARMED;old.checksum=v2_checksum(&old);
    memcpy(disk,&old,sizeof(old));disk_len=sizeof(old);profile_init();
    assert(state.phase==TRIAL&&profile_spi_device_cs(0)==25&&!profile_spi_device_enabled(1));
    profile_init();assert(state.phase==IDLE&&profile_spi_device_cs(0)==27);
    /* A broken old candidate cannot discard the protected confirmed map. */
    old.phase=STAGED;old.candidate.external_cs=4;
    old.candidate_checksum=v2_mapping_checksum(&old.candidate);old.checksum=v2_checksum(&old);
    memcpy(disk,&old,sizeof(old));disk_len=sizeof(old);profile_init();
    assert(state.phase==IDLE&&state.revision>=17&&profile_spi_device_cs(0)==27);
    extended_t m=active;m.external_cs=255;unsigned id=stage3(&m);
    /* Interrupted trial and startup driver failure both restore prior wiring. */
    assert(command3(APPLY,id,NULL)==0);profile_init();assert(profile_spi_device_cs(0)==255);
    profile_init();assert(!profile_is_trial()&&profile_spi_device_cs(0)==27);
    id=stage3(&m);assert(command3(APPLY,id,NULL)==0);profile_init();
    profile_driver_failed();profile_init();assert(profile_spi_device_cs(0)==27);
    id=stage3(&m);assert(command3(APPLY,id,NULL)==0);profile_init();
    profile_boot_ready();profile_network_ready();clock_us=deadline;
    assert(command3(CONFIRM,id,NULL)==UBCP_ERR_TIMEOUT);profile_init();assert(profile_spi_device_cs(0)==27);
    /* A damaged v3 candidate recovers independently checksummed confirmed map. */
    id=stage3(&m);((record_t*)disk)->candidate.external2_host=4;
    profile_init();assert(state.phase==IDLE&&!state.candidate_id&&profile_spi_width(2)==1);
    ((record_t*)disk)->confirmed.external2_host=4;
    profile_init();assert(state.revision==1&&profile_spi_width(2)==defaults3.bus[0].width);
    /* Corrupt v2 migration cannot authorize unsafe GPIO wiring. */
    old.confirmed.external_cs=4;
    old.confirmed_checksum=v2_mapping_checksum(&old.confirmed);old.checksum=v2_checksum(&old);
    memcpy(disk,&old,sizeof(old));disk_len=sizeof(old);profile_init();
    assert(state.revision==1&&profile_spi_device_cs(0)==27);
}
int main(void) {
    descriptors_and_independent_devices();no_cs_ownership_and_validation();compatibility_and_recovery();
    return 0;
}
'''


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('compiler',nargs='?',default='cl' if os.name=='nt' else 'cc')
    args=parser.parse_args()
    with compiled_harness(args.compiler,HARNESS) as binary:
        subprocess.run([str(binary)],check=True)
    print('Profile v3 dual devices, no-CS ownership, v2 migration and safe rollback: PASS')


if __name__=='__main__':
    main()
