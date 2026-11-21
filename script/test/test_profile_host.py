"""Compile the real profile handler with in-memory NVS. Run with cl (VS prompt) or cc."""
import argparse
import os
import subprocess
import tempfile
from pathlib import Path

MAIN = Path(__file__).resolve().parents[2] / "main"
STUBS = """
#pragma once
#include <stdint.h>
#include <stdbool.h>
#include <assert.h>
#include <string.h>
typedef int nvs_handle_t;
typedef int esp_err_t;
typedef int SemaphoreHandle_t;
#define ESP_OK 0
#define ESP_ERR_NO_MEM 1
#define ESP_ERR_NVS_NOT_FOUND 2
#define NVS_READWRITE 0
#define ESP_ERROR_CHECK(x) assert((x)==0)
#define ESP_LOGW(...) ((void)0)
#define pdPASS 1
#define portMAX_DELAY 1
#define pdMS_TO_TICKS(x) (x)
#define xSemaphoreCreateMutex() 1
#define xSemaphoreTake(a,b) ((void)0)
#define xSemaphoreGive(a) ((void)0)
#define xTaskCreate(a,b,c,d,e,f) ((void)(a),1)
#define vTaskDelete(x) ((void)0)
#define vTaskDelay(x) ((void)0)
#define uart_wait_tx_done(a,b) ((void)0)
static unsigned restarts;
#define esp_restart() (++restarts)
static int64_t clock_us;
#define esp_timer_get_time() (clock_us)
static unsigned char disk[256], staged[256];
static size_t disk_len, staged_len;
static bool fail_write;
#define nvs_flash_init_partition(p) 0
#define nvs_open_from_partition(p,n,m,h) (*(h)=1,0)
static int nvs_get_blob(int h,const char*k,void *v,size_t*n){
    if (!disk_len) return ESP_ERR_NVS_NOT_FOUND;
    assert(*n>=disk_len); memcpy(v,disk,disk_len); *n=disk_len; return 0;
}
static int nvs_set_blob(int h,const char*k,const void*v,size_t n){
    assert(n<=sizeof(staged));memcpy(staged,v,n);staged_len=n;return 0;
}
static int nvs_commit(int h){
    if(fail_write)return 1;
    memcpy(disk,staged,staged_len);disk_len=staged_len;return 0;
}
"""
HARNESS = r"""
#include "core/device_profile.c"
static bool credentials, tcp;
bool mod_network_has_saved_credentials(void) {return credentials;}
bool mcp_transport_using_tcp(void) {return tcp;}
static uint8_t reply[100];
static size_t length;
void ubcp_frame_make_response(const ubcp_frame_t *r,ubcp_frame_t *s){*s=*r;}
esp_err_t msg_bus_send_frame(const ubcp_frame_t *r){
    length=r->payload_len; assert(length<=sizeof(reply));memcpy(reply,r->payload,length);return 0;
}
static unsigned command(int op,unsigned id,const mapping_t*m){
    uint8_t p[32]={1,(uint8_t)op};
    put32(p+2,id);
    if(m)memcpy(p+6,m,sizeof(*m));
    ubcp_frame_t req={.payload=p,.payload_len=(uint16_t)(m?6+sizeof(*m):op<=READ?2:6)};
    profile_command(&req);
    return reply[0];
}
int main(void){
    profile_init();
    assert(command(DESCRIBE,0,NULL)==0 && length==57);
    assert(reply[17+4]==CONTROL_TX && reply[17+34]==CONTROL_RX);
    assert(command(READ,0,NULL)==0 && length==25 && get32(reply+2)==1);
    mapping_t m=defaults;
    for(unsigned pin=0;pin<40;pin++){
        if(board[pin]<CONSOLE_TX)continue;
        m.pin[SIG_UART_TX]=pin;
        assert(command(CHECK,1,&m)==UBCP_ERR_PARAM && reply[2]==5);
    }
    m=defaults;m.pin[SIG_UART_TX]=35;
    assert(command(CHECK,1,&m)==UBCP_ERR_PARAM && reply[2]==5);
    m=defaults;m.pin[SIG_UART_TX]=25;
    assert(command(CHECK,1,&m)==UBCP_ERR_PARAM && reply[2]==6);
    m.mask_hi=0;m.pin[SIG_UART_RX]=26;
    assert(command(CHECK,1,&m)==0 && !disk_len);
    assert(command(SAVE,1,&m)==0);unsigned id=get32(reply+1);
    assert(command(SAVE,1,&m)==0 && get32(reply+1)==id);
    assert(command(READ,0,NULL)==0 && reply[1]==STAGED && length==36);
    assert(profile_pin(SIG_UART_TX)==32);
    assert(command(CHECK,1,&m)==UBCP_ERR_SEQ_MISMATCH);
    assert(command(CANCEL,id,NULL)==0);
    m.mask_lo=PF_CONTROL_TCP;
    assert(command(CHECK,state.revision,&m)==UBCP_ERR_PARAM && reply[1]==2);
    m.mask_lo=PF_CONTROL_TCP|PF_WIFI;
    assert(command(CHECK,state.revision,&m)==UBCP_ERR_PARAM && reply[2]==4);
    credentials=true;
    fail_write=true;
    assert(command(SAVE,state.revision,&m)==UBCP_ERR_UNKNOWN && state.phase==IDLE);
    fail_write=false;
    assert(command(SAVE,state.revision,&m)==0);id=get32(reply+1);
    assert(command(APPLY,id,NULL)==0 && restarts==1);
    profile_init();assert(state.phase==TRIAL && profile_pin(SIG_UART_TX)==25);
    assert(command(APPLY,id,NULL)==0 && restarts==1);
    assert(command(SAVE,state.revision,&m)==UBCP_ERR_BUSY);
    clock_us=deadline;assert(command(CONFIRM,id,NULL)==UBCP_ERR_TIMEOUT);
    trial_timeout(NULL);assert(restarts==2);
    profile_init();assert(state.phase==IDLE && profile_pin(SIG_UART_TX)==32);
    assert(command(SAVE,state.revision,&m)==0);id=get32(reply+1);
    assert(command(APPLY,id,NULL)==0);profile_init();tcp=true;
    assert(command(CONFIRM,id,NULL)==0 && command(CONFIRM,id,NULL)==0);
    profile_init();assert(!profile_enabled(PF_SERIAL) && profile_pin(SIG_UART_TX)==25);
    m.mask_lo |= PF_SERIAL;
    assert(command(SAVE,state.revision,&m)==0);id=get32(reply+1);
    assert(command(APPLY,id,NULL)==0);profile_init();
    assert(command(CONFIRM,id,NULL)==UBCP_ERR_PERMISSION);
    tcp=false;assert(command(CONFIRM,id,NULL)==0);
    return 0;
}
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("compiler", nargs="?", default="cl" if os.name == "nt" else "cc")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for name in ("esp_err.h esp_system.h esp_log.h esp_timer.h freertos/FreeRTOS.h "
                     "freertos/semphr.h freertos/task.h nvs_flash.h nvs.h driver/gpio.h "
                     "driver/uart.h driver/spi_master.h").split():
            header = root / name
            header.parent.mkdir(exist_ok=True)
            header.write_text('#include "mock.h"\n')
        (root / "mock.h").write_text(STUBS + "".join(f"#define GPIO_NUM_{i} {i}\n" for i in range(40)))
        (root / "test.c").write_text(HARNESS)
        if Path(args.compiler).stem.lower() == "cl":
            cmd = [args.compiler, "/nologo", "/std:c11", "/utf-8", "/I.", "/I" + str(MAIN), "test.c"]
        else:
            cmd = [args.compiler, "-std=c11", "-I.", "-I" + str(MAIN), "test.c", "-o", "test"]
        subprocess.run(cmd, cwd=root, check=True)
        subprocess.run([str(root / ("test.exe" if os.name == "nt" else "test"))], check=True)
    print("Device profile protocol, validation, persistence and rollback: PASS")


if __name__ == "__main__":
    main()
