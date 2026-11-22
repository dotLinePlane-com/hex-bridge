"""Compile actual SPI module, CAN SPI driver and bus lifecycle against fake IDF."""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile

MAIN = Path(__file__).resolve().parents[2] / "main"
MOCK = r'''
#pragma once
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include <string.h>
#include <assert.h>
typedef int esp_err_t;
typedef void *SemaphoreHandle_t;
typedef unsigned TickType_t;
#define IRAM_ATTR
#define ESP_OK 0
#define ESP_FAIL -1
#define ESP_ERR_NO_MEM 1
#define ESP_ERR_INVALID_ARG 2
#define ESP_ERR_INVALID_STATE 3
#define ESP_ERR_TIMEOUT 4
#define pdTRUE 1
#define portMAX_DELAY 0xffffffff
#define pdMS_TO_TICKS(x) (x)
#define xSemaphoreCreateMutex() ((void *)1)
static unsigned armed_count[2],semaphore_count;
static void *new_binary(void){unsigned *v=&armed_count[semaphore_count++ % 2];*v=0;return v;}
static int take_semaphore(void *a,unsigned timeout){if(a==(void*)1)return 1;unsigned *v=a;if(*v){--*v;return 1;}return 0;}
#define xSemaphoreCreateBinary() new_binary()
#define xSemaphoreTake(a,b) take_semaphore(a,b)
#define xSemaphoreGiveFromISR(a,b) (++*(unsigned *)(a))
#define pdFALSE 0
typedef int BaseType_t;
#define portYIELD_FROM_ISR() ((void)0)
#define xSemaphoreGive(a) ((void)0)
#define vSemaphoreDelete(a) ((void)0)
#define vTaskDelay(a) ((void)0)
static unsigned ticks;
#define xTaskGetTickCount() (++ticks)
#define ESP_LOGI(...) ((void)0)
#define ESP_LOGE(...) ((void)0)
#define ESP_LOGW(...) ((void)0)
#define SPI2_HOST 1
#define SPI3_HOST 2
#define SPI_DMA_DISABLED 0
#define SPI_DMA_CH_AUTO 0
#define SPI_DMA_CH1 1
#define SPI_DMA_CH2 2
#define SPICOMMON_BUSFLAG_MASTER 1
#define SPICOMMON_BUSFLAG_QUAD 2
#define SPI_DEVICE_HALFDUPLEX 1
#define SPI_DEVICE_BIT_LSBFIRST 2
#define SPI_TRANS_MODE_QIO 1
#define GPIO_MODE_OUTPUT 1
#define GPIO_PULLUP_DISABLE 0
#define GPIO_PULLDOWN_DISABLE 0
#define GPIO_INTR_DISABLE 0
typedef struct { uint64_t pin_bit_mask; int mode,pull_up_en,pull_down_en,intr_type; } gpio_config_t;
typedef struct { int sclk_io_num,mosi_io_num,miso_io_num,quadwp_io_num,quadhd_io_num,max_transfer_sz,flags; } spi_bus_config_t;
typedef struct { int clock_speed_hz,mode,spics_io_num,queue_size,flags; } spi_device_interface_config_t;
typedef struct { size_t length,rxlength; const void *tx_buffer; void *rx_buffer; int flags; } spi_transaction_t;
typedef struct { int host; } fake_device;
typedef fake_device *spi_device_handle_t;
static fake_device devices[64];
static int device_count,owner[3],users[3],init_count[3],free_count[3],gpio_writes,transfers;
static bool fail_add,fail_init,fail_tx;
static int fail_init_host;
static int chip_reply;
static unsigned chip_mode=4;
static bool ignore_chip_writes;
static spi_bus_config_t last_bus;
static int gpio_set_level(int pin,int level){assert(pin>=0 && pin<40);++gpio_writes;return 0;}
static int gpio_config(const gpio_config_t *g){assert(g->pin_bit_mask && !(g->pin_bit_mask>>40));return 0;}
static int gpio_reset_pin(int pin){assert(pin>=0 && pin<40);return 0;}
static int spi_bus_initialize(int h,const spi_bus_config_t*b,int dma){assert(dma==h);last_bus=*b;if(fail_init || fail_init_host==h)return 3;++init_count[h];return 0;}
static int spi_bus_free(int h){assert(!users[h]);++free_count[h];return 0;}
static int spi_bus_add_device(int h,const spi_device_interface_config_t*c,spi_device_handle_t*d){if(fail_add)return 1;*d=&devices[device_count++];(*d)->host=h;++users[h];return 0;}
static int spi_bus_remove_device(spi_device_handle_t d){assert(!owner[d->host]);--users[d->host];return 0;}
static int spi_device_acquire_bus(spi_device_handle_t d,unsigned t){assert(!owner[d->host]);owner[d->host]=1;return 0;}
static void spi_device_release_bus(spi_device_handle_t d){assert(owner[d->host]);owner[d->host]=0;}
static int spi_device_transmit(spi_device_handle_t d,spi_transaction_t*t){
 assert(owner[d->host]);++transfers;
 const uint8_t *write=t->tx_buffer;
 if(chip_reply==1 && write && t->length>=24 && (write[0]>>4)==2 &&
    (((write[0]&15)<<8)|write[1])==3 && !ignore_chip_writes)chip_mode=write[2]&7;
 if(t->rx_buffer){
  uint8_t *rx=t->rx_buffer;const uint8_t *tx=t->tx_buffer;
  memset(rx,chip_reply==2?255:0,t->rxlength/8);
  if (chip_reply==3 && tx) {
   for (size_t i=0;i<t->rxlength/8;++i) rx[i]=tx[i]^(d->host==SPI2_HOST?0x55:0xaa);
  }
  if(chip_reply==1 && tx && t->length>=24 && (tx[0]>>4)==3){
   unsigned addr=((tx[0]&15)<<8)|tx[1];
   if(addr==0xe00 && t->length>=32)rx[3]=4; /* OSCRDY */
   if(addr==2)rx[2]=chip_mode<<5;
  }
 }
 return fail_tx?4:0;
}

typedef struct {size_t length,trans_len;const void *tx_buffer;void *rx_buffer;void *user;} spi_slave_transaction_t;
typedef struct {int spics_io_num,mode,queue_size;void (*post_setup_cb)(spi_slave_transaction_t*);} spi_slave_interface_config_t;
static spi_slave_transaction_t *queued_slave[3];
static bool slave_done[3],slave_live[3],fail_slave_init,delay_arm;
static int fail_slave_host;
static void (*slave_setup[3])(spi_slave_transaction_t*);
static int spi_slave_initialize(int h,const spi_bus_config_t *b,const spi_slave_interface_config_t*c,int dma){
 assert(!users[h] && !slave_live[h] && !dma && c->mode==0 && c->queue_size==1);
 if(fail_slave_init || fail_slave_host==h)return ESP_FAIL;
 slave_live[h]=true;slave_setup[h]=c->post_setup_cb;return 0;
}
static int spi_slave_queue_trans(int h,spi_slave_transaction_t*t,unsigned wait){assert(!wait&&!queued_slave[h]);queued_slave[h]=t;slave_done[h]=false;if(!delay_arm)slave_setup[h](t);return 0;}
static int spi_slave_get_trans_result(int h,spi_slave_transaction_t**t,unsigned wait){assert(!wait);if(!queued_slave[h]||!slave_done[h])return ESP_ERR_TIMEOUT;*t=queued_slave[h];queued_slave[h]=NULL;return 0;}
static int spi_slave_free(int h){assert(!queued_slave[h]);slave_live[h]=false;return 0;}
static void external_clock(int h,size_t bits){assert(queued_slave[h]);queued_slave[h]->trans_len=bits;memset(queued_slave[h]->rx_buffer,h==1?0x5a:0xa5,(bits+7)/8);slave_done[h]=true;}
'''
HARNESS = r'''
#include "core/spi_bus_manager.c"
#include "modules/mod_spi.c"
/* Static identifiers in the two modules intentionally live in separate scopes. */
#undef TAG
#define TAG MCP_TAG
#define spi_transfer can_spi_transfer
#define s_bus_retained can_bus_retained
#include "modules/mcp2518fd.c"
#undef TAG
#undef s_bus_retained
static int ext_host=2,can_host=3,width=4;
static bool can_enabled=true,ext2_enabled;
static bool slave_role[2],ext1_enabled=true;
bool profile_spi_slave(int h){return slave_role[h-2];}
int profile_spi_slave_cs(int h){return h==2?27:26;}
static int ext2_host=3,ext2_cs=26,ext_cs=27;
bool profile_spi_device_enabled(int instance){return (instance==0 && ext1_enabled) || (instance==1 && ext2_enabled);}
int profile_spi_device_host(int instance){return instance==0?ext_host:ext2_host;}
int profile_spi_device_cs(int instance){return instance==0?ext_cs:ext2_cs;}
int profile_spi_host(bool can){return can?can_host:ext_host;}
int profile_spi_cs(bool can){return can?15:27;}
int profile_spi_pin(int host,int i){int pins[]={18,19,21,22,23};return pins[i];}
int profile_spi_width(int host){return width;}
bool profile_spi_enabled(int host){return true;}
uint32_t profile_spi_clock(bool can){return can?10000000:1000000;}
bool profile_enabled(enum profile_feature f){return f==PF_CAN&&can_enabled;}
int profile_pin(enum profile_signal s){return s==SIG_CAN_CS?15:39;}
static unsigned status,response_len,registered;
void topology_register(uint8_t ch,uint8_t type,void*d){++registered;}
void ubcp_frame_make_response(const ubcp_frame_t*r,ubcp_frame_t*s){*s=*r;}
esp_err_t msg_bus_send_status_response(const ubcp_frame_t*r,uint8_t s){status=s;return 0;}
esp_err_t msg_bus_send_frame(const ubcp_frame_t*r){status=r->payload[0];response_len=r->payload_len;return 0;}
static uint32_t session=1;
static unsigned command_ch(int ch,int cmd,uint8_t*p,int n){ubcp_frame_t f={.session_id=session,.cmd_code=cmd,.channel_id=ch,.payload=p,.payload_len=n};spi_handle(&f);return status;}
static unsigned command(int cmd,uint8_t*p,int n){return command_ch(UBCP_CH_SPI_EXT1,cmd,p,n);}
int main(void){
 uint8_t open[]={27,0},config[]={0,0,15,66,64,0,0,0,4},data[]={0,2,0x55,0xaa},cs[]={0};
 assert(spi_init()==0&&registered==1&&init_count[1]==1);
 assert(last_bus.quadwp_io_num==22);
 open[0]=15;assert(command(UBCP_CMD_SPI_OPEN,open,2)==UBCP_ERR_SPI_CS_INVALID);open[0]=27;
 assert(command(UBCP_CMD_SPI_OPEN,open,2)==0);
 assert(command(UBCP_CMD_SPI_CONFIG,config,9)==0);
 assert(command(UBCP_CMD_SPI_WRITE,data,4)==0&&!owner[1]);
 assert(command(UBCP_CMD_SPI_TRANSFER,data,4)==UBCP_ERR_NOT_SUPPORT);
 config[8]=1;assert(command(UBCP_CMD_SPI_CONFIG,config,9)==0);
 assert(command(UBCP_CMD_SPI_TRANSFER,data,4)==0&&response_len==5);
 fail_tx=true;assert(command(UBCP_CMD_SPI_WRITE,data,4)==UBCP_ERR_SPI_TRANSFER&&!owner[1]);fail_tx=false;
 config[7]=1;assert(command(UBCP_CMD_SPI_CONFIG,config,9)==0);
 assert(command(UBCP_CMD_SPI_CS_CONTROL,cs,1)==0&&owner[1]);
 assert(command(UBCP_CMD_SPI_WRITE,data,4)==0&&owner[1]);
 assert(command(UBCP_CMD_SPI_CLOSE,NULL,0)==0&&!owner[1]);spi_stop();assert(free_count[1]==1);
 can_host=2;width=1;
 assert(mcp2518fd_init()==0);
 assert(mcp2518fd_probe()==ESP_ERR_TIMEOUT); /* shorted/absent chip */
 chip_reply=2;assert(mcp2518fd_probe()==ESP_ERR_TIMEOUT); /* floating high */
 chip_reply=1;assert(mcp2518fd_probe()==0);
 ignore_chip_writes=true;assert(mcp2518fd_probe()==ESP_ERR_TIMEOUT);ignore_chip_writes=false;
 chip_reply=0;
 assert(spi_init()==0&&init_count[1]==2);
 assert(command(UBCP_CMD_SPI_OPEN,open,2)==0);
 config[8]=4;int before=gpio_writes;assert(command(UBCP_CMD_SPI_CONFIG,config,9)==UBCP_ERR_NOT_SUPPORT&&gpio_writes==before);
 config[8]=1;assert(command(UBCP_CMD_SPI_CONFIG,config,9)==UBCP_ERR_NOT_SUPPORT);
 config[7]=0;assert(command(UBCP_CMD_SPI_CONFIG,config,9)==0);
 assert(command(UBCP_CMD_SPI_WRITE,data,4)==0);
 uint8_t value;assert(mcp2518fd_read_byte(0,&value)==0&&!owner[1]);
 fail_add=true;assert(command(UBCP_CMD_SPI_CONFIG,config,9)==UBCP_ERR_HAL_FAIL&&!s_devices[0].open&&!s_devices[0].dev);fail_add=false;
 assert(command(UBCP_CMD_SPI_OPEN,open,2)==0);
 spi_stop();assert(free_count[1]==1&&users[1]==1);
 assert(mcp2518fd_deinit()==0&&free_count[1]==2);
 fail_add=true;assert(mcp2518fd_init()!=0&&free_count[1]==3);fail_add=false;
 fail_init=true;assert(spi_init()!=0&&s_lock==0);fail_init=false;
 ext_host=3;assert(spi_init()==0&&init_count[2]==1);spi_stop();assert(free_count[2]==1);
 /* Enabled zero-consumer hosts still initialize exactly once. */
 int init2=init_count[1],init3=init_count[2];
 assert(hex_spi_buses_init()==0&&init_count[1]==init2+1&&init_count[2]==init3+1);
 assert(last_bus.quadwp_io_num==-1&&last_bus.quadhd_io_num==-1);
 assert(hex_spi_buses_init()==0&&init_count[1]==init2+1);
 /* Two logical devices retain their own state on distinct configured hosts. */
 can_enabled=false;ext_host=2;ext2_host=3;ext2_enabled=true;
 int routes=registered;assert(spi_init()==0 && registered==routes+2);
 uint8_t open2[]={26,1};config[0]=0;config[7]=0;config[8]=1;
 assert(command(UBCP_CMD_SPI_OPEN,open,2)==0);
 assert(command_ch(UBCP_CH_SPI_EXT2,UBCP_CMD_SPI_OPEN,open2,2)==0);
 config[0]=3;assert(command_ch(UBCP_CH_SPI_EXT2,UBCP_CMD_SPI_CONFIG,config,9)==0);
 assert(s_devices[0].mode==0 && s_devices[1].mode==3);
 assert(s_devices[0].dev->host==SPI2_HOST && s_devices[1].dev->host==SPI3_HOST);
 /* A distinct deterministic peripheral per host catches misrouted TX or stale RX. */
 chip_reply=3;
 assert(command(UBCP_CMD_SPI_TRANSFER,data,4)==0 && response_len==5);
 assert(s_response[1]==0 && s_response[2]==2 && s_response[3]==0 && s_response[4]==255);
 assert(command_ch(UBCP_CH_SPI_EXT2,UBCP_CMD_SPI_TRANSFER,data,4)==0 && response_len==5);
 assert(s_response[3]==255 && s_response[4]==0);
 chip_reply=0;
 config[7]=1;assert(command(UBCP_CMD_SPI_CONFIG,config,9)==0);
 assert(command(UBCP_CMD_SPI_CS_CONTROL,cs,1)==0 && owner[1]);
 assert(command_ch(UBCP_CH_SPI_EXT2,UBCP_CMD_SPI_WRITE,data,4)==0 && !owner[2] && owner[1]);
 cs[0]=1;assert(command(UBCP_CMD_SPI_CS_CONTROL,cs,1)==0 && !owner[1]);cs[0]=0;
 assert(command_ch(UBCP_CH_SPI_EXT2,UBCP_CMD_SPI_CLOSE,NULL,0)==0);
 assert(command(UBCP_CMD_SPI_TRANSFER,data,4)==0);
 assert(command_ch(UBCP_CH_SPI_EXT2,UBCP_CMD_SPI_WRITE,data,4)==UBCP_ERR_NOT_OPEN);
 spi_stop();
 /* Same-host peers arbitrate each transaction; neither may hold CS indefinitely. */
 ext2_host=2;assert(spi_init()==0);config[0]=0;config[7]=1;
 assert(command(UBCP_CMD_SPI_OPEN,open,2)==0);
 assert(command_ch(UBCP_CH_SPI_EXT2,UBCP_CMD_SPI_OPEN,open2,2)==0);
 assert(command(UBCP_CMD_SPI_CONFIG,config,9)==UBCP_ERR_NOT_SUPPORT);
 assert(command_ch(UBCP_CH_SPI_EXT2,UBCP_CMD_SPI_CONFIG,config,9)==UBCP_ERR_NOT_SUPPORT);
 config[7]=0;assert(command(UBCP_CMD_SPI_CONFIG,config,9)==0);
 assert(command(UBCP_CMD_SPI_WRITE,data,4)==0 && !owner[1]);
 assert(command_ch(UBCP_CH_SPI_EXT2,UBCP_CMD_SPI_WRITE,data,4)==0 && !owner[1]);
 fail_add=true;assert(command(UBCP_CMD_SPI_CONFIG,config,9)==UBCP_ERR_HAL_FAIL);fail_add=false;
 assert(!s_devices[0].open && s_devices[1].open);
 assert(command_ch(UBCP_CH_SPI_EXT2,UBCP_CMD_SPI_WRITE,data,4)==0);
 spi_stop();
 /* No-CS OPEN/transfer/close never touch GPIO255 or shift by that value. */
 ext2_host=3;ext2_cs=UBCP_SPI_NO_CS;open2[0]=UBCP_SPI_NO_CS;
 assert(spi_init()==0);int writes=gpio_writes;
 assert(command_ch(UBCP_CH_SPI_EXT2,UBCP_CMD_SPI_OPEN,open2,2)==0);
 assert(command_ch(UBCP_CH_SPI_EXT2,UBCP_CMD_SPI_CONFIG,config,9)==0);
 assert(command_ch(UBCP_CH_SPI_EXT2,UBCP_CMD_SPI_TRANSFER,data,4)==0);
 config[7]=1;assert(command_ch(UBCP_CH_SPI_EXT2,UBCP_CMD_SPI_CONFIG,config,9)==UBCP_ERR_NOT_SUPPORT);
 assert(command_ch(UBCP_CH_SPI_EXT2,UBCP_CMD_SPI_CS_CONTROL,cs,1)==UBCP_ERR_NOT_SUPPORT);
 assert(command_ch(UBCP_CH_SPI_EXT2,UBCP_CMD_SPI_CLOSE,NULL,0)==0 && writes==gpio_writes);
 spi_stop();ext2_enabled=false;assert(spi_init()==0);
 assert(command_ch(UBCP_CH_SPI_EXT2,UBCP_CMD_SPI_OPEN,open2,2)==UBCP_ERR_PERMISSION);
 assert(command_ch(99,UBCP_CMD_SPI_OPEN,open2,2)==UBCP_ERR_CHANNEL_INVALID);
 spi_stop();
 /* A failure retaining the second host unwinds the first and publishes nothing. */
 for(int h=SPI2_HOST;h<=SPI3_HOST;++h){assert(hex_spi_bus_release(h)==0);configured[h==SPI2_HOST?0:1]=false;}
 ext2_enabled=true;int frees=free_count[SPI2_HOST];routes=registered;fail_init_host=SPI3_HOST;
 assert(spi_init()!=0 && !s_lock && registered==routes);
 assert(free_count[SPI2_HOST]==frees+1 && !s_devices[0].bus_retained && !s_devices[1].bus_retained);
 fail_init_host=0;assert(spi_init()==0);spi_stop();
 /* Slave-only profiles initialize no master bus; both endpoints are independent. */
 ext1_enabled=ext2_enabled=false;slave_role[0]=slave_role[1]=true;
 int master_inits=init_count[1]+init_count[2];routes=registered;
 assert(hex_spi_buses_init()==0 && init_count[1]+init_count[2]==master_inits);
 assert(hex_spi_bus_retain(SPI2_HOST)==ESP_ERR_INVALID_ARG);
 assert(spi_init()==0 && registered==routes+2);
 uint8_t preload[]={2,0x12,0x34};
 assert(command_ch(6,UBCP_CMD_SPI_SLAVE_FETCH,NULL,0)==UBCP_ERR_NOT_OPEN);
 uint8_t maximum[65]={64};
 assert(command_ch(6,UBCP_CMD_SPI_SLAVE_PREPARE,maximum,65)==0);
 external_clock(1,512);assert(command_ch(6,UBCP_CMD_SPI_SLAVE_FETCH,NULL,0)==0 && response_len==67 && s_response[1]==2 && s_response[2]==0);
 maximum[0]=0;assert(command_ch(6,UBCP_CMD_SPI_SLAVE_PREPARE,maximum,1)==UBCP_ERR_PARAM);
 maximum[0]=65;assert(command_ch(6,UBCP_CMD_SPI_SLAVE_PREPARE,maximum,65)==UBCP_ERR_PARAM);
 assert(command_ch(6,UBCP_CMD_SPI_SLAVE_PREPARE,preload,2)==UBCP_ERR_PARAM);
 assert(command_ch(6,UBCP_CMD_SPI_SLAVE_PREPARE,preload,3)==0);
 assert(queued_slave[1] && !memcmp(queued_slave[1]->tx_buffer,preload+1,2));
 assert(command_ch(6,UBCP_CMD_SPI_SLAVE_PREPARE,preload,3)==UBCP_ERR_BUSY);
 assert(command_ch(6,UBCP_CMD_SPI_SLAVE_FETCH,NULL,0)==UBCP_ERR_BUSY);
 assert(command_ch(7,UBCP_CMD_SPI_SLAVE_PREPARE,preload,3)==0);
 external_clock(1,9);
 assert(command_ch(6,UBCP_CMD_SPI_SLAVE_FETCH,NULL,0)==0 && response_len==5);
 assert(s_response[1]==0 && s_response[2]==9 && s_response[3]==0x5a);
 assert(command_ch(6,UBCP_CMD_SPI_SLAVE_FETCH,NULL,0)==UBCP_ERR_NOT_OPEN);
 /* Handover never reuses pending buffers; stale completion is discarded. */
 ++session;
 assert(command_ch(7,UBCP_CMD_SPI_SLAVE_FETCH,NULL,0)==UBCP_ERR_BUSY);
 spi_stop();assert(s_lock && slave_live[2] && queued_slave[2] && !slave_live[1]);
 external_clock(2,8);
 assert(command_ch(7,UBCP_CMD_SPI_SLAVE_FETCH,NULL,0)==UBCP_ERR_NOT_OPEN);
 assert(command_ch(7,UBCP_CMD_SPI_SLAVE_PREPARE,preload,3)==0);
 external_clock(2,16);assert(command_ch(7,UBCP_CMD_SPI_SLAVE_FETCH,NULL,0)==0 && s_response[3]==0xa5);
 spi_stop();assert(!s_lock && !slave_live[2]);
 /* No successful PREPARE before post_setup callback. Timed-out slot is retained. */
 assert(spi_init()==0);delay_arm=true;
 assert(command_ch(6,UBCP_CMD_SPI_SLAVE_PREPARE,preload,3)==UBCP_ERR_BUSY);
 assert(queued_slave[1] && s_slaves[0].pending);
 delay_arm=false;slave_setup[1](queued_slave[1]);
 preload[1]^=1;assert(command_ch(6,UBCP_CMD_SPI_SLAVE_PREPARE,preload,3)==UBCP_ERR_BUSY);preload[1]^=1;
 assert(command_ch(6,UBCP_CMD_SPI_SLAVE_PREPARE,preload,3)==0);
 assert(command_ch(6,UBCP_CMD_SPI_SLAVE_PREPARE,preload,3)==UBCP_ERR_BUSY);
 external_clock(1,8);
 assert(command_ch(6,UBCP_CMD_SPI_SLAVE_FETCH,NULL,0)==0);spi_stop();
 fail_slave_init=true;routes=registered;
 assert(spi_init()!=0 && !s_lock && registered==routes && !slave_live[1] && !slave_live[2]);
 fail_slave_init=false;fail_slave_host=SPI3_HOST;
 assert(spi_init()!=0 && !s_lock && registered==routes && !slave_live[1] && !slave_live[2]);
 fail_slave_host=0;
 /* One master remains usable while the other host waits for external clocks. */
 slave_role[0]=false;ext1_enabled=true;ext_host=2;
 assert(spi_init()==0);
 assert(command_ch(7,UBCP_CMD_SPI_SLAVE_PREPARE,preload,3)==0);
 assert(command(UBCP_CMD_SPI_OPEN,open,2)==0);
 assert(command(UBCP_CMD_SPI_TRANSFER,data,4)==0);
 assert(command_ch(7,UBCP_CMD_SPI_SLAVE_FETCH,NULL,0)==UBCP_ERR_BUSY);
 external_clock(2,8);
 assert(command_ch(7,UBCP_CMD_SPI_SLAVE_FETCH,NULL,0)==0);
 spi_stop();

 return 0;
}
'''


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("compiler", nargs="?", default="cl" if os.name == "nt" else "cc")
    args = p.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for name in ("esp_err.h esp_log.h esp_attr.h freertos/FreeRTOS.h freertos/semphr.h freertos/task.h driver/gpio.h driver/spi_master.h driver/spi_slave.h driver/uart.h").split():
            path = root / name
            path.parent.mkdir(exist_ok=True)
            path.write_text('#include "mock.h"\n')
        (root / "mock.h").write_text(MOCK + "".join(f"#define GPIO_NUM_{i} {i}\n" for i in range(40)))
        (root / "test.c").write_text(HARNESS)
        cl = Path(args.compiler).stem.lower() == "cl"
        command = ([args.compiler, "/nologo", "/std:c11", "/utf-8", "/I.", "/I" + str(MAIN), "test.c"] if cl else
                   [args.compiler, "-std=c11", "-I.", "-I" + str(MAIN), "test.c", "-o", "test"])
        subprocess.run(command, cwd=root, check=True)
        subprocess.run([str(root / ("test.exe" if os.name == "nt" else "test"))], check=True)
    print("Actual SPI/CAN drivers: master/slave roles, armed readiness, nonblocking fetch, short transfers, session drain, lifecycle and master regressions PASS")


if __name__ == "__main__":
    main()
