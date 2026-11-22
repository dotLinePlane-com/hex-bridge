"""Compile the real UART module against deterministic IDF mocks; no hardware writes."""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile

MAIN = Path(__file__).resolve().parents[2] / "main"
MOCK = r'''
#pragma once
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>
typedef int esp_err_t;
#define ESP_OK 0
#define ESP_FAIL -1
#define ESP_ERR_NO_MEM 1
#define ESP_ERR_INVALID_ARG 2
#define ESP_ERR_TIMEOUT 3
#define pdTRUE 1
#define pdPASS 1
#define portMAX_DELAY 0xffffffff
#define pdMS_TO_TICKS(x) (x)
#define ESP_LOGI(...) ((void)0)
#define ESP_LOGW(...) ((void)0)
#define ESP_LOGE(...) ((void)0)
#define ESP_LOGD(...) ((void)0)
#define ESP_LOGV(...) ((void)0)
typedef unsigned TickType_t;
typedef int BaseType_t;
typedef void (*TaskFunction_t)(void *);
typedef struct {TaskFunction_t fn;void *arg;} task_t;
typedef task_t *TaskHandle_t;
typedef struct {int count;} sem_t;
typedef sem_t *SemaphoreHandle_t;
typedef struct {int type;} uart_event_t;
typedef struct {uart_event_t events[8];int count,index;} queue_t;
typedef queue_t *QueueHandle_t;
static sem_t sems[8];static int sem_count,sem_deleted,task_deleted;
static task_t tasks[32];static int task_count;static bool fail_task,fail_install;
static SemaphoreHandle_t xSemaphoreCreateBinary(void){sems[sem_count].count=0;return &sems[sem_count++];}
static int xSemaphoreTake(SemaphoreHandle_t s,unsigned timeout){if(s->count){s->count=0;return 1;}assert(!timeout);return 0;}
static int xSemaphoreGive(SemaphoreHandle_t s){s->count=1;return 1;}
static void vSemaphoreDelete(SemaphoreHandle_t s){assert(s);++sem_deleted;}
static int xQueueReceive(QueueHandle_t q,uart_event_t *e,unsigned timeout){if(q->index==q->count)return 0;*e=q->events[q->index++];return 1;}
static int xTaskCreate(TaskFunction_t fn,const char*n,unsigned stack,void*arg,unsigned priority,TaskHandle_t*out){if(fail_task)return 0;*out=&tasks[task_count++];(*out)->fn=fn;(*out)->arg=arg;return 1;}
static void vTaskDelete(void*t){++task_deleted;}
static void vTaskDelay(unsigned ticks){}
#define UART_NUM_1 1
#define UART_NUM_2 2
#define UART_DATA_5_BITS 5
#define UART_DATA_6_BITS 6
#define UART_DATA_7_BITS 7
#define UART_DATA_8_BITS 8
#define UART_PARITY_DISABLE 0
#define UART_PARITY_ODD 1
#define UART_PARITY_EVEN 2
#define UART_STOP_BITS_1 1
#define UART_STOP_BITS_1_5 2
#define UART_STOP_BITS_2 3
#define UART_HW_FLOWCTRL_DISABLE 0
#define UART_SCLK_APB 0
#define UART_PIN_NO_CHANGE -1
#define UART_DATA 1
#define UART_BREAK 2
#define UART_BUFFER_FULL 3
#define UART_FIFO_OVF 4
#define UART_FRAME_ERR 5
#define UART_PARITY_ERR 6
#define GPIO_MODE_OUTPUT 1
#define GPIO_MODE_INPUT_OUTPUT 2
typedef int uart_word_length_t;
typedef int uart_stop_bits_t;
typedef int uart_parity_t;
typedef struct {int baud_rate,data_bits,parity,stop_bits,flow_ctrl,source_clk;} uart_config_t;
static bool installed[3];static int deleted[3],tx_pin_seen[3],rx_pin_seen[3],baud[3],word[3],stop[3],parity[3];
static queue_t queues[3];static unsigned writes[3],flushes[3];static uint8_t tx[3][128];
static size_t buffered[3];static int break_pin;
static uint32_t session=1;static volatile bool *running;static int read_step,read_limit,change_at;
static int rx_port;static const char *read_plan[8];
static int uart_driver_install(int n,int r,int t,int size,QueueHandle_t*q,int flags){assert(!installed[n]);if(fail_install)return 1;installed[n]=true;memset(&queues[n],0,sizeof(queue_t));*q=&queues[n];return 0;}
static int uart_driver_delete(int n){assert(installed[n]);installed[n]=false;++deleted[n];return 0;}
static int uart_param_config(int n,const uart_config_t*c){assert(installed[n]);baud[n]=c->baud_rate;return 0;}
static int uart_set_pin(int n,int tx,int rx,int rts,int cts){assert(installed[n]);tx_pin_seen[n]=tx;rx_pin_seen[n]=rx;return 0;}
static int uart_set_baudrate(int n,unsigned b){assert(installed[n]);baud[n]=b;return 0;}
static int uart_set_word_length(int n,int b){word[n]=b;return 0;}
static int uart_set_stop_bits(int n,int b){stop[n]=b;return 0;}
static int uart_set_parity(int n,int b){parity[n]=b;return 0;}
static int uart_get_baudrate(int n,uint32_t*b){*b=baud[n];return 0;}
static int uart_write_bytes(int n,const void*d,size_t len){assert(installed[n]);assert(writes[n]+len<128);memcpy(tx[n]+writes[n],d,len);writes[n]+=len;return (int)len;}
static int uart_get_buffered_data_len(int n,size_t*l){assert(installed[n]);*l=buffered[n];return 0;}
static int uart_get_tx_buffer_free_size(int n,size_t*l){assert(installed[n]);*l=1024;return 0;}
static int uart_flush_input(int n){assert(installed[n]);++flushes[n];return 0;}
static int uart_wait_tx_done(int n,unsigned t){assert(installed[n]);return 0;}
static int gpio_set_direction(int pin,int mode){break_pin=pin;return 0;}
static int gpio_set_level(int pin,int level){assert(pin==break_pin);return 0;}
static int uart_read_bytes(int n,void*out,size_t len,unsigned timeout){
 assert(n==rx_port && installed[n]);
 const char *p=read_plan[read_step];int size=p?(int)strlen(p):0;assert(size<=(int)len);
 ++read_step;if(change_at==read_step)++session;
 if(size)memcpy(out,p,size);if(read_step>=read_limit)*running=false;return size;
}
'''
HARNESS = r'''
#include "modules/mod_uart.c"
#include "core/topology.c"
static bool uart2_enabled=true,uart1_enabled;
static int uart2_tx=32,uart2_rx=35;
bool profile_enabled(enum profile_feature f){return f==PF_UART && uart2_enabled;}
bool profile_uart1_business_enabled(void){return uart1_enabled;}
int profile_pin(enum profile_signal s){return s==SIG_UART_TX?uart2_tx:uart2_rx;}
uint32_t mcp_transport_session_id(void){return session;}
bool mcp_transport_session_is_current(uint32_t s){return s==session;}
void ubcp_frame_make_response(const ubcp_frame_t*r,ubcp_frame_t*s){*s=*r;}
void ubcp_frame_make_event(ubcp_frame_t*f,uint8_t cmd,uint8_t ch,uint16_t seq){memset(f,0,sizeof(*f));f->cmd_code=cmd;f->channel_id=ch;}
static uint8_t status,response[2048];static unsigned response_len,event_count,rejected;
static unsigned event_channels[32],event_commands[32],event_lengths[32];static uint8_t event_data[32][32];
static unsigned flow_state,flow_usage,flow_capacity;
esp_err_t msg_bus_send_status_response(const ubcp_frame_t*r,uint8_t s){status=s;return 0;}
esp_err_t msg_bus_send_frame(const ubcp_frame_t*f){
 if(f->cmd_code==UBCP_CMD_UART_RECV || f->cmd_code==UBCP_CMD_FLOW_CONTROL){
  if(f->session_id!=session){++rejected;return ESP_ERR_TIMEOUT;}
  unsigned i=event_count++;event_channels[i]=f->channel_id;event_commands[i]=f->cmd_code;
  event_lengths[i]=f->payload_len;assert(f->payload_len<=32);memcpy(event_data[i],f->payload,f->payload_len);
 }else{response_len=f->payload_len;memcpy(response,f->payload,f->payload_len);status=f->payload[0];}return 0;
}
void msg_bus_update_flow_state(uint8_t m,uint8_t s,uint16_t u,uint16_t c){flow_state=s;flow_usage=u;flow_capacity=c;}
static unsigned command(int ch,int cmd,uint8_t*p,int n){ubcp_frame_t f={.cmd_code=cmd,.channel_id=ch,.payload=p,.payload_len=n,.session_id=session};uart_module_handle_cmd(&f);return status;}
static void run_rx(uart_channel_t*ch,const char*first,const char*second,int limit,int change){
 for(int i=0;i<8;++i)read_plan[i]=NULL;read_plan[0]=first;read_plan[1]=second;
 read_plan[2]="new\n";read_plan[3]=NULL;read_step=0;read_limit=limit;change_at=change;
 rx_port=ch->uart_num;running=&ch->rx_running;ch->rx_running=true;
 ch->rx_task_handle->fn(ch->rx_task_handle->arg);
 assert(!ch->rx_running && ch->rx_stopped->count==1);
}
int main(void){
 topology_init();assert(uart_module_init()==0 && topology_for_each(NULL,NULL)==1);
 assert(topology_find(1) && !topology_find(2));
 uint8_t passive[]={0},data[]={0,3,'a','b','c'},config[]={0,0,225,0,8,1,0,0,0,4,20},flush[]={0};
 assert(command(2,UBCP_CMD_UART_OPEN,passive,1)==UBCP_ERR_PERMISSION);
 assert(command(99,UBCP_CMD_UART_OPEN,passive,1)==UBCP_ERR_CHANNEL_INVALID);
 assert(!installed[1]);uart_module_stop();assert(!deleted[1]);
 uart1_enabled=true;topology_init();assert(uart_module_init()==0 && topology_for_each(NULL,NULL)==2);
 for(int mode=0;mode<4;++mode){
  uint8_t open[]={(uint8_t)mode};
  assert(command(1,UBCP_CMD_UART_OPEN,open,1)==0);
  assert(command(2,UBCP_CMD_UART_OPEN,open,1)==0);
  assert(command(1,UBCP_CMD_UART_OPEN,open,1)==UBCP_ERR_ALREADY_OPEN);
  assert(tx_pin_seen[1]==4 && rx_pin_seen[1]==34 && tx_pin_seen[2]==32 && rx_pin_seen[2]==35);
  /* Per-instance configuration/status/send and all four real RX tasks. */
  for(int i=0;i<2;++i){
   uart_channel_t*ch=&s_channels[i];ch->rx_threshold=4;ch->rx_timeout_ms=20;
   if(i==0){queues[2].events[0].type=UART_PARITY_ERR;queues[2].count=1;}
   int before=event_count;run_rx(ch,i?"two\n":"one\n",NULL,mode==3?2:1,0);
   assert(event_count==before+1 && event_channels[before]==ch->channel_id);
   assert(event_commands[before]==UBCP_CMD_UART_RECV && event_lengths[before]==7);
   assert(memcmp(event_data[before]+3,i?"two\n":"one\n",4)==0 && ch->rx_count==4);
  }
  assert(command(1,UBCP_CMD_UART_SEND,data,5)==0 && s_channels[0].tx_count==3 && s_channels[1].tx_count==0);
  data[2]='x';assert(command(2,UBCP_CMD_UART_SEND,data,5)==0 && s_channels[1].tx_count==3);data[2]='a';
  assert(command(2,UBCP_CMD_UART_CONFIG,config,11)==0 && baud[1]==57600 && baud[2]==115200);
  assert(s_channels[0].error_count==1 && s_channels[1].error_count==0);
  assert(command(2,UBCP_CMD_UART_STATUS,NULL,0)==0 && response_len==19 && response[13]==3 && response[17]==4);
  assert(command(2,UBCP_CMD_UART_SET_BREAK,NULL,0)==0 && break_pin==4 && tx_pin_seen[1]==4 && rx_pin_seen[1]==34);
  assert(command(1,UBCP_CMD_UART_SET_BREAK,NULL,0)==0 && break_pin==32);
  assert(command(2,UBCP_CMD_UART_FLUSH,flush,1)==0);
  if(mode==0){
   int first=event_count;buffered[1]=1900;buffered[2]=100;
   check_rx_flow(&s_channels[1],session);assert(flow_state==1 && flow_usage==2000 && flow_capacity==4096);
   check_rx_flow(&s_channels[0],session);assert(flow_state==1);
   assert(event_count==first+1 && event_channels[first]==2 && event_commands[first]==UBCP_CMD_FLOW_CONTROL);
   buffered[1]=0;check_rx_flow(&s_channels[1],session);assert(flow_state==0 && event_count==first+2);
   buffered[2]=0;
  }
  assert(command(2,0xa8,config,11)==UBCP_ERR_NOT_SUPPORT);
  assert(command(1,UBCP_CMD_UART_CLOSE,NULL,0)==0 && !installed[2] && installed[1]);
  assert(command(2,UBCP_CMD_UART_CLOSE,NULL,0)==0 && !installed[1]);
 }
 /* Fixed pins never inherit UART2's remap; UART1 works while UART2 is disabled. */
 uart2_enabled=false;uart2_tx=25;uart2_rx=36;topology_init();assert(uart_module_init()==0 && !topology_find(1) && topology_find(2));
 assert(command(1,UBCP_CMD_UART_OPEN,passive,1)==UBCP_ERR_PERMISSION);
 assert(command(2,UBCP_CMD_UART_OPEN,passive,1)==0 && tx_pin_seen[1]==4 && rx_pin_seen[1]==34);
 /* Stale RX and flow events never migrate to the next connection. */
 unsigned before=event_count;run_rx(&s_channels[1],"old",NULL,1,1);assert(event_count==before && s_channels[1].rx_count==0);
 unsigned old_session=session-1;send_recv_event(old_session,2,0,(uint8_t*)"old",3);
 send_flow_event(old_session,2,0,100,2048);assert(rejected==2);
 assert(command(2,UBCP_CMD_UART_CLOSE,NULL,0)==0);
 /* Buffered line/fixed/timeout fragments are discarded at a session boundary. */
 for(int mode=1;mode<4;++mode){
  uint8_t open[]={(uint8_t)mode};assert(command(2,UBCP_CMD_UART_OPEN,open,1)==0);
  s_channels[1].rx_threshold=4;before=event_count;
  run_rx(&s_channels[1],"old","x",mode==3?4:3,2);
  assert(event_count==before+1 && memcmp(event_data[before]+3,"new\n",4)==0);
  assert(command(2,UBCP_CMD_UART_CLOSE,NULL,0)==0);
 }
 /* Configuration restarts only the selected task and reports restart failure. */
 uint8_t fixed[]={2};assert(command(2,UBCP_CMD_UART_OPEN,fixed,1)==0);
 run_rx(&s_channels[1],"test",NULL,1,0);
 config[9]=8;assert(command(2,UBCP_CMD_UART_CONFIG,config,11)==0);
 run_rx(&s_channels[1],"1234","5678",2,0);
 fail_task=true;config[9]=4;assert(command(2,UBCP_CMD_UART_CONFIG,config,11)==UBCP_ERR_UNKNOWN && !installed[1]);fail_task=false;
 /* Failed opens never affect the other controller or leave a running driver. */
 fail_task=true;assert(command(2,UBCP_CMD_UART_OPEN,passive,1)==UBCP_ERR_UNKNOWN && !installed[1]);fail_task=false;
 fail_install=true;assert(command(2,UBCP_CMD_UART_OPEN,passive,1)==UBCP_ERR_UNKNOWN && !installed[1]);fail_install=false;
 uart_module_stop();assert(sem_deleted==sem_count && !installed[1] && !installed[2]);
 return 0;
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("compiler", nargs="?", default="cl" if os.name == "nt" else "cc")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for name in ("esp_err.h esp_log.h freertos/FreeRTOS.h freertos/task.h freertos/semphr.h "
                     "freertos/queue.h driver/uart.h driver/gpio.h driver/spi_master.h").split():
            path = root / name
            path.parent.mkdir(exist_ok=True)
            path.write_text('#include "mock.h"\n')
        (root / "mock.h").write_text(MOCK + "".join(f"#define GPIO_NUM_{i} {i}\n" for i in range(40)))
        (root / "test.c").write_text(HARNESS)
        cl = Path(args.compiler).stem.lower() == "cl"
        command = ([args.compiler, "/nologo", "/std:c11", "/experimental:c11atomics", "/utf-8", "/I.", "/I" + str(MAIN), "test.c"] if cl else
                   [args.compiler, "-std=c11", "-I.", "-I" + str(MAIN), "test.c", "-o", "test"])
        subprocess.run(command, cwd=root, check=True)
        subprocess.run([str(root / ("test.exe" if os.name == "nt" else "test"))], check=True)
    print("Actual UART driver: dual channels, four RX modes, session isolation and cleanup PASS")


if __name__ == "__main__":
    main()
