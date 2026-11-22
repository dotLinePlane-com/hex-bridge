"""Compile actual profile v5 SPI roles, migration and transaction guards."""
import argparse
import os
import subprocess
from test_profile_host import HARNESS_PREFIX, compiled_harness

HARNESS = HARNESS_PREFIX + r'''
static unsigned request(int version,int op,unsigned id,const extended_t *m) {
    uint8_t p[40]={(uint8_t)version,(uint8_t)op};put32(p+2,id);
    unsigned n=version==5?34:version==4?30:version==3?29:version==2?26:11;
    if(m) {
        if(version==5)encode5(p+6,m);else if(version==4)encode4(p+6,m);
        else if(version==3)encode3(p+6,m);else if(version==2)encode(p+6,m);
        else memcpy(p+6,&m->legacy,11);
    }
    ubcp_frame_t req={.payload=p,.payload_len=(uint16_t)(m?6+n:op<=READ?2:6)};
    profile_command(&req);return reply[0];
}
static void fresh(void) {
    disk_len=0;clock_us=0;credentials=true;tcp=false;session_current=true;fail_write=false;profile_init();
}
static bool diagnostic(int reason,int subject,int gpio,int other) {
    for(unsigned i=0;i<reply[1];i++) {
        uint8_t *d=reply+2+4*i;
        if(d[0]==reason&&d[1]==subject&&d[2]==gpio&&d[3]==other)return true;
    }
    return false;
}
static extended_t slave(int host) {
    extended_t m=active;
    m.legacy.mask_lo&=~(PF_CAN|PF_UART);
    m.external_enabled=m.external2_enabled=0;
    m.bus[0].enabled=m.bus[1].enabled=0;
    int h=host-2;m.bus[h].enabled=1;m.bus[h].width=1;
    m.bus[h].pin[0]=35;m.bus[h].pin[1]=36;m.bus[h].pin[2]=27;
    m.role[h]=1;m.slave_cs[h]=39;
    return m;
}
static unsigned stage(const extended_t *m) {
    assert(request(5,SAVE,state.revision,m)==0);return get32(reply+1);
}
static void boot(unsigned id) {
    assert(request(5,APPLY,id,NULL)==0);profile_init();assert(state.phase==TRIAL);
}
static void old_writes(unsigned id) {
    unsigned revision=state.revision,phase=state.phase;
    for(int v=1;v<=4;v++) {
        assert(request(v,READ,0,NULL)==0);
        for(int op=CHECK;op<=CONFIRM;op++) {
            assert(request(v,op,op<=SAVE?revision:id,op<=SAVE?&active:NULL)==UBCP_ERR_NOT_SUPPORT);
            assert(state.revision==revision&&state.phase==phase);
        }
    }
}
static void validate(void) {
    fresh();assert(request(5,DESCRIBE,0,NULL)==0&&length==86);
    assert(get32(reply+6)==511&&reply[11]==34&&reply[42]==0&&reply[43]==255&&reply[44]==0&&reply[45]==255);
    assert(request(5,READ,0,NULL)==0&&length==48);
    assert(!profile_spi_slave(1)&&!profile_spi_slave(2)&&!profile_spi_slave(3)&&!profile_spi_slave(4));
    assert(profile_spi_slave_cs(1)==255&&profile_spi_slave_cs(2)==255);
    for(int host=2;host<=3;host++) {
        extended_t m=slave(host);int h=host-2;
        assert(request(5,CHECK,state.revision,&m)==0&&!disk_len);
        m.role[h]=2;assert(request(5,CHECK,state.revision,&m)==2&&diagnostic(7,21+h,255,255));
        m=slave(host);m.bus[h].width=4;
        assert(request(5,CHECK,state.revision,&m)==2&&diagnostic(7,21+h,255,255));
        m=slave(host);m.slave_cs[h]=255;
        assert(request(5,CHECK,state.revision,&m)==2&&diagnostic(5,19+h,255,255));
        m=slave(host);m.slave_cs[h]=15;
        assert(request(5,CHECK,state.revision,&m)==2&&diagnostic(5,19+h,15,255));
        m=slave(host);m.slave_cs[h]=4;
        assert(request(5,CHECK,state.revision,&m)==2&&diagnostic(5,19+h,4,255));
        m=slave(host);m.bus[h].pin[2]=35;
        assert(request(5,CHECK,state.revision,&m)==2&&diagnostic(5,6+5*h,35,255));
        m=slave(host);m.slave_cs[h]=36;
        assert(request(5,CHECK,state.revision,&m)==2&&diagnostic(6,19+h,36,5+5*h));
        m=slave(host);m.external_enabled=1;m.external_host=host;m.external_cs=13;
        assert(request(5,CHECK,state.revision,&m)==2&&diagnostic(11,14,host,21+h));
        m=slave(host);m.external2_enabled=1;m.external2_host=host;m.external2_cs=13;
        assert(request(5,CHECK,state.revision,&m)==2&&diagnostic(11,17,host,21+h));
        m=slave(host);m.legacy.mask_lo|=PF_CAN;m.mcp_host=host;sync_legacy(&m);
        assert(request(5,CHECK,state.revision,&m)==2&&diagnostic(11,15,host,21+h));
        m=slave(host);m.bus[h].enabled=0;m.slave_cs[h]=255;
        assert(request(5,CHECK,state.revision,&m)==0);
    }
    extended_t m=active;m.bus[0].width=1;m.bus[0].pin[0]=35;
    assert(request(5,CHECK,state.revision,&m)==2&&diagnostic(5,4,35,255));
    uint8_t wire[40]={5,SAVE};put32(wire+2,state.revision);encode5(wire+6,&active);
    ubcp_frame_t bad={.payload=wire,.payload_len=39};profile_command(&bad);
    assert(reply[0]==2&&state.revision==1&&!disk_len);
}
static void trials(void) {
    for(int host=2;host<=3;host++) {
        fresh();extended_t m=slave(host);fail_write=true;
        assert(request(5,SAVE,state.revision,&m)==UBCP_ERR_UNKNOWN&&!disk_len&&!profile_spi_slave(host));
        fail_write=false;unsigned id=stage(&m);old_writes(id);
        assert(request(5,READ,0,NULL)==0&&length==82);
        assert(!profile_spi_slave(host));boot(id);
        assert(profile_spi_slave(host)&&profile_enabled(PF_SPI)&&profile_spi_slave_cs(host)==39);
        assert(!profile_spi_device_enabled(0)&&!profile_spi_device_enabled(1));
        assert(request(5,CONFIRM,id,NULL)==UBCP_ERR_BUSY);
        profile_boot_ready();profile_network_ready();assert(request(5,CONFIRM,id,NULL)==0);
        profile_init();assert(profile_spi_slave(host));old_writes(0);
        m=extend(&defaults);id=stage(&m);boot(id);old_writes(id);
        profile_boot_ready();profile_network_ready();assert(request(5,CONFIRM,id,NULL)==0);
        assert(request(4,CHECK,state.revision,&active)==0);
        m=slave(host);id=stage(&m);boot(id);clock_us=deadline;
        assert(request(5,CONFIRM,id,NULL)==UBCP_ERR_TIMEOUT);profile_init();
        assert(!profile_spi_slave(host)&&state.phase==IDLE);
        id=stage(&m);boot(id);profile_driver_failed();profile_init();assert(!profile_spi_slave(host));
        id=stage(&m);boot(id);profile_init();assert(!profile_spi_slave(host));
        /* Even dormant values must not be lost through an old schema write. */
        m=active;m.slave_cs[host-2]=39;id=stage(&m);old_writes(id);
        assert(request(5,CANCEL,id,NULL)==0);
    }
}
static void migrate_v4(void) {
    fresh();record_v4_t old={0};old.version=4;old.revision=41;
    memcpy(&old.confirmed,&active,sizeof(old.confirmed));
    old.confirmed_checksum=v4_mapping_checksum(&old.confirmed);
    old.candidate_checksum=v4_mapping_checksum(&old.candidate);old.checksum=v4_checksum(&old);
    memcpy(disk,&old,sizeof(old));disk_len=sizeof(old);profile_init();
    assert(state.version==5&&state.revision==41&&disk_len==sizeof(record_t));
    assert(active.slave_cs[0]==255&&active.slave_cs[1]==255&&!profile_spi_slave(2));
    old.phase=ARMED;old.candidate_id=42;old.candidate=old.confirmed;old.candidate.bus[0].width=1;
    old.candidate_checksum=v4_mapping_checksum(&old.candidate);old.checksum=v4_checksum(&old);
    memcpy(disk,&old,sizeof(old));disk_len=sizeof(old);profile_init();
    assert(state.phase==TRIAL&&profile_spi_width(2)==1&&active.slave_cs[0]==255);
    profile_init();assert(state.phase==IDLE&&profile_spi_width(2)==4);
    old.phase=STAGED;old.candidate_checksum^=1;old.checksum=v4_checksum(&old);
    memcpy(disk,&old,sizeof(old));disk_len=sizeof(old);profile_init();
    assert(state.phase==IDLE&&state.revision==42&&profile_spi_width(2)==4);
    old.confirmed_checksum^=1;old.checksum=v4_checksum(&old);
    memcpy(disk,&old,sizeof(old));disk_len=sizeof(old);profile_init();assert(state.revision==1);
    fresh();extended_t m=slave(2);unsigned id=stage(&m);
    record_t *saved=(record_t*)disk;saved->candidate.slave_cs[0]=255;
    saved->candidate_checksum=mapping_checksum(&saved->candidate);saved->checksum=checksum(saved);
    profile_init();assert(state.phase==IDLE&&!profile_spi_slave(2));
    saved=(record_t*)disk;saved->confirmed.role[0]=2;
    saved->confirmed_checksum=mapping_checksum(&saved->confirmed);saved->checksum=checksum(saved);
    profile_init();assert(state.revision==1&&!profile_spi_slave(2));
}
int main(void) {validate();trials();migrate_v4();return 0;}
'''

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('compiler',nargs='?',default='cl' if os.name=='nt' else 'cc')
    args=parser.parse_args()
    with compiled_harness(args.compiler,HARNESS) as binary:
        subprocess.run([str(binary)],check=True)
    print('Profile v5 SPI roles, directions, ownership, legacy guards, v4 migration and trials: PASS')

if __name__=='__main__':
    main()
