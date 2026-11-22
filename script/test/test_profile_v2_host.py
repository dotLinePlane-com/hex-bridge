"""Compile real extended profile storage, migration and trial guards with in-memory NVS."""
import argparse
import subprocess
from test_profile_host import HARNESS_PREFIX, compiled_harness

HARNESS = HARNESS_PREFIX + r'''
static unsigned command2(int op,unsigned id,const extended_t *m) {
    uint8_t p[32]={2,(uint8_t)op};put32(p+2,id);
    if(m)encode(p+6,m);
    ubcp_frame_t req={.payload=p,.payload_len=(uint16_t)(m?32:op<=READ?2:6)};
    profile_command(&req);return reply[0];
}
static void boot_ready_all(void){profile_boot_ready();profile_network_ready();}
static void fresh(void){disk_len=0;clock_us=0;credentials=true;tcp=false;session_current=true;fail_write=false;profile_init();}
int main(void) {
    fresh();
    assert(command2(DESCRIBE,0,NULL)==0 && length==78 && reply[1]==2 && reply[11]==26);
    assert(command2(READ,0,NULL)==0 && length==40);
    extended_t m=active;
    assert(profile_spi_host(true)==3 && profile_spi_host(false)==2);
    assert(profile_spi_width(2)==4 && profile_spi_pin(2,4)==23);
    assert(command2(CHECK,state.revision,&m)==0 && !disk_len);
    /* 13 occupied signals in single mode; GPIO22/23 released. */
    m.bus[0].width=1;
    assert(command2(CHECK,state.revision,&m)==0);
    assert(command2(SAVE,state.revision,&m)==0);unsigned id=get32(reply+1),rev=state.saved_from;
    assert(command2(SAVE,rev,&m)==0 && get32(reply+1)==id);
    assert(command(CHECK,state.revision,&defaults)==UBCP_ERR_NOT_SUPPORT);
    assert(command(CANCEL,id,NULL)==UBCP_ERR_NOT_SUPPORT);
    assert(command(APPLY,id,NULL)==UBCP_ERR_NOT_SUPPORT);
    assert(command(CONFIRM,id,NULL)==UBCP_ERR_NOT_SUPPORT);
    assert(command2(APPLY,id,NULL)==0);profile_init();
    assert(state.phase==TRIAL && profile_spi_width(2)==1);
    assert(command2(CONFIRM,id,NULL)==UBCP_ERR_BUSY);
    profile_boot_ready();assert(command2(CONFIRM,id,NULL)==UBCP_ERR_BUSY);
    profile_network_ready();session_current=false;
    assert(command2(CONFIRM,id,NULL)==UBCP_ERR_PERMISSION);
    session_current=true;assert(command2(CONFIRM,id,NULL)==0);
    assert(command2(CONFIRM,id,NULL)==0);profile_init();assert(profile_spi_width(2)==1);
    m=active;m.external_cs=15;
    assert(command2(CHECK,state.revision,&m)==UBCP_ERR_PARAM);
    m=active;m.external_cs=m.legacy.pin[SIG_CAN_CS];
    assert(command2(CHECK,state.revision,&m)==UBCP_ERR_PARAM);
    m=active;m.external_cs=14;
    assert(command2(CHECK,state.revision,&m)==UBCP_ERR_PARAM);
    m=active;m.bus[0].enabled=0;
    assert(command2(CHECK,state.revision,&m)==UBCP_ERR_PARAM && reply[2]==8);
    m=active;m.external_host=4;
    assert(command2(CHECK,state.revision,&m)==UBCP_ERR_PARAM && reply[2]==7);
    m=active;m.bus[0].width=4;m.bus[0].pin[3]=35;
    assert(command2(CHECK,state.revision,&m)==UBCP_ERR_PARAM);
    m=active;m.external_enabled=0;m.bus[0].enabled=0;
    assert(command2(SAVE,state.revision,&m)==0);id=get32(reply+1);
    assert(command2(APPLY,id,NULL)==0);profile_init();boot_ready_all();
    profile_driver_failed();assert(driver_failed);profile_init();assert(state.phase==IDLE && profile_enabled(PF_SPI));
    /* Failed NVS commit preserves revision and confirmed snapshot. */
    m=active;unsigned prior=state.revision;fail_write=true;
    assert(command2(SAVE,prior,&m)==UBCP_ERR_UNKNOWN && state.revision==prior);fail_write=false;
    assert(command2(SAVE,prior,&m)==0);id=get32(reply+1);
    /* Candidate corruption recovers independently protected confirmed mapping. */
    ((record_t*)disk)->candidate.external_cs=4;profile_init();
    assert(state.phase==IDLE && profile_spi_width(2)==1 && !state.candidate_id);
    /* Confirmed corruption cannot authorize any active pin configuration. */
    ((record_t*)disk)->confirmed.legacy.pin[0]=4;profile_init();
    assert(state.revision==1 && profile_pin(SIG_UART_TX)==HEX_EXT_UART_TX_PIN);
    /* Exact v1 record migrates CAN-disabled mappings without reserving SPI3. */
    legacy_record_t old={0};old.version=1;old.revision=9;old.confirmed=defaults;
    old.confirmed.mask_lo&=~PF_CAN;old.confirmed.pin[0]=14;
    memcpy(disk,&old,sizeof(old));disk_len=sizeof(old);profile_init();
    assert(state.revision==9 && !profile_spi_enabled(3) && profile_pin(SIG_UART_TX)==14);
    /* Invalid old disabled signal cannot evade the original board table. */
    old.confirmed.pin[SIG_CAN_SCK]=18;memcpy(disk,&old,sizeof(old));disk_len=sizeof(old);profile_init();
    assert(state.revision==1 && profile_pin(SIG_UART_TX)==HEX_EXT_UART_TX_PIN);
    /* Interrupted v1 trial recovers confirmed; armed enters exactly one trial. */
    old=(legacy_record_t){0};old.version=1;old.revision=3;old.confirmed=defaults;
    old.candidate=defaults;old.candidate.mask_hi=0;old.phase=STAGED;old.candidate_id=4;
    memcpy(disk,&old,sizeof(old));disk_len=sizeof(old);profile_init();
    assert(state.phase==STAGED && profile_enabled(PF_DAP));
    old.phase=ARMED;memcpy(disk,&old,sizeof(old));disk_len=sizeof(old);profile_init();
    assert(state.phase==TRIAL && !profile_enabled(PF_DAP));
    profile_init();assert(state.phase==IDLE && profile_enabled(PF_DAP));
    /* Oversized and unsupported requests cannot mutate revision or storage. */
    fresh();unsigned untouched=state.revision;
    uint8_t bad[2]={6,DESCRIBE};ubcp_frame_t req={.payload=bad,.payload_len=2};
    profile_command(&req);assert(reply[0]==UBCP_ERR_VERSION && !disk_len);
    bad[0]=2;req.payload_len=2049;profile_command(&req);
    assert(reply[0]==UBCP_ERR_PARAM && state.revision==untouched && !disk_len);
    fresh();m=active;m.legacy.mask_hi=0;m.legacy.mask_lo=PF_WIFI|PF_CONTROL_TCP;
    assert(command2(SAVE,state.revision,&m)==0);id=get32(reply+1);
    assert(command2(APPLY,id,NULL)==0);profile_init();boot_ready_all();
    assert(!profile_wifi_forget_allowed());tcp=true;
    assert(command2(CONFIRM,id,NULL)==0);profile_init();
    assert(!profile_wifi_forget_allowed() && !profile_enabled(PF_SERIAL));
    m=active;m.legacy.mask_lo|=PF_SERIAL;
    assert(command2(SAVE,state.revision,&m)==0);id=get32(reply+1);
    assert(command2(APPLY,id,NULL)==0);profile_init();
    assert(profile_enabled(PF_SERIAL) && !profile_wifi_forget_allowed());
    profile_init();assert(!profile_enabled(PF_SERIAL));
    credentials=false;profile_init();assert(profile_enabled(PF_SERIAL));
    fresh();m=active;m.bus[0].width=1;
    assert(command2(SAVE,state.revision,&m)==0);id=get32(reply+1);
    assert(command2(APPLY,id,NULL)==0);profile_init();boot_ready_all();
    clock_us=deadline;assert(command2(CONFIRM,id,NULL)==UBCP_ERR_TIMEOUT);
    profile_init();assert(state.phase==IDLE && profile_spi_width(2)==4);
    return 0;
}
'''

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("compiler",nargs="?",default="cl")
    args=parser.parse_args()
    with compiled_harness(args.compiler,HARNESS) as binary:
        subprocess.run([str(binary)],check=True)
    print("Extended profile migration, validation, persistence and trial guards: PASS")

if __name__=="__main__":
    main()
