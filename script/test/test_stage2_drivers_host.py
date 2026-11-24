"""Compile real Stage 2 drivers against bounded queues and peripheral fault mocks."""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile

MAIN = Path(__file__).resolve().parents[2] / 'main'
MOCK = r'''
#pragma once
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdlib.h>
#include <string.h>
#include <assert.h>
typedef int esp_err_t;
#define ESP_OK 0
#define ESP_ERR_NO_MEM 1
#define ESP_ERR_INVALID_ARG 2
#define ESP_ERR_INVALID_STATE 3
#define ESP_ERR_TIMEOUT 4
#define ESP_ERR_INVALID_RESPONSE 5
#define ESP_ERR_NOT_FOUND 6
#define ESP_FAIL -1
#define pdTRUE 1
#define pdFALSE 0
#define pdPASS 1
#define pdMS_TO_TICKS(x) (x)
#define portMAX_DELAY 0xffffffffu
typedef int BaseType_t;
typedef void *TaskHandle_t;
typedef void *SemaphoreHandle_t;
#define xSemaphoreCreateMutex() ((void *)1)
#define xSemaphoreTake(a,b) 1
#define xSemaphoreGive(a) ((void)0)
#define vSemaphoreDelete(a) ((void)0)
static void (*delay_hook)(void);
#define vTaskDelay(a) do{clock_us+=(int64_t)(a)*1000;if(delay_hook)delay_hook();}while(0)
#define vTaskDelete(a) ((void)0)
#define portYIELD_FROM_ISR() ((void)0)
static int task_fail;
static int fake_task_create(void(*fn)(void*),const char*n,int stack,void*arg,int prio,void**out){*out=NULL;return task_fail?0:pdPASS;}
#define xTaskCreate fake_task_create
static int64_t clock_us;
static int64_t esp_timer_get_time(void){return clock_us;}
typedef struct { unsigned cap,size,head,count; uint8_t data[4096]; } fake_queue;
typedef fake_queue *QueueHandle_t;
static void (*queue_empty)(void);
static QueueHandle_t xQueueCreate(unsigned cap,unsigned size){fake_queue*q=calloc(1,sizeof(*q));q->cap=cap;q->size=size;assert(cap*size<=4096);return q;}
static int xQueueSend(QueueHandle_t q,const void*p,unsigned wait){if(q->count==q->cap)return 0;memcpy(q->data+((q->head+q->count)%q->cap)*q->size,p,q->size);q->count++;return 1;}
static int xQueueReceive(QueueHandle_t q,void*p,unsigned wait){if(!q->count){if(queue_empty)queue_empty();return 0;}memcpy(p,q->data+q->head*q->size,q->size);q->head=(q->head+1)%q->cap;q->count--;return 1;}
static int xQueueSendFromISR(QueueHandle_t q,const void*p,int*wake){return xQueueSend(q,p,0);}
static void xQueueReset(QueueHandle_t q){q->count=q->head=0;}
static void vQueueDelete(QueueHandle_t q){free(q);}
static unsigned uxQueueMessagesWaiting(QueueHandle_t q){return q->count;}

typedef int gpio_mode_t;
typedef int gpio_int_type_t;
#define GPIO_MODE_INPUT 0
#define GPIO_MODE_INPUT_OUTPUT 1
#define GPIO_MODE_INPUT_OUTPUT_OD 2
#define GPIO_INTR_DISABLE 0
#define GPIO_INTR_POSEDGE 1
#define GPIO_INTR_NEGEDGE 2
#define GPIO_INTR_ANYEDGE 3
#define GPIO_INTR_HIGH_LEVEL 4
#define GPIO_INTR_LOW_LEVEL 8
#define GPIO_FLOATING 0
#define GPIO_PULLUP_ONLY 1
#define GPIO_PULLDOWN_ONLY 2
#define GPIO_PULLUP_PULLDOWN 3
typedef struct{uint64_t pin_bit_mask;int mode,pull_up_en,pull_down_en,intr_type;} gpio_config_t;
static int levels[40],modes[40],interrupts[40],writes,attached[40];
static int gpio_get_level(int p){assert(p>=0&&p<40);return levels[p];}
static int gpio_set_level(int p,int value){assert(p>=0&&p<40);writes++;levels[p]=value;return 0;}
static int gpio_config(const gpio_config_t*c){for(int i=0;i<40;i++)if(c->pin_bit_mask&(1ULL<<i))modes[i]=c->mode;return 0;}
static int gpio_set_direction(int p,int mode){modes[p]=mode;return 0;}
static int gpio_set_pull_mode(int p,int pull){return 0;}
static int gpio_intr_disable(int p){interrupts[p]=0;return 0;}
static int gpio_intr_enable(int p){interrupts[p]=1;return 0;}
static int gpio_set_intr_type(int p,int type){return 0;}
static int gpio_isr_handler_remove(int p){attached[p]=0;return 0;}
static int gpio_isr_handler_add(int p,void(*handler)(void*),void*arg){attached[p]=1;return 0;}
static int gpio_install_isr_service(int flags){return ESP_ERR_INVALID_STATE;}
static int gpio_reset_pin(int p){return 0;}

typedef struct{int port;} fake_bus;
typedef struct{fake_bus*bus;unsigned address,width,speed;} fake_device;
typedef fake_bus *i2c_master_bus_handle_t;
typedef fake_device *i2c_master_dev_handle_t;
typedef struct{int i2c_port,scl_io_num,sda_io_num,clk_source,glitch_ignore_cnt;struct{unsigned enable_internal_pullup:1;} flags;}i2c_master_bus_config_t;
typedef struct{unsigned dev_addr_length,device_address,scl_speed_hz;}i2c_device_config_t;
#define I2C_CLK_SRC_DEFAULT 0
#define I2C_ADDR_BIT_LEN_10 10
#define I2C_ADDR_BIT_LEN_7 7
static int bus_live,device_live,transfer_error,transfer_count,last_port,last_operation,reset_port=-1,last_timeout;
static unsigned resets[2],probe_count;static bool poisoned[2];
static unsigned last_address,last_width,last_speed,last_write_len,last_read_len;
static uint8_t last_write[2048];
static int i2c_new_master_bus(const i2c_master_bus_config_t*c,fake_bus**b){*b=malloc(sizeof(**b));(*b)->port=c->i2c_port;bus_live++;return 0;}
static int i2c_del_master_bus(fake_bus*b){free(b);bus_live--;return 0;}
static int i2c_master_bus_add_device(fake_bus*b,const i2c_device_config_t*c,fake_device**d){*d=malloc(sizeof(**d));**d=(fake_device){b,c->device_address,c->dev_addr_length,c->scl_speed_hz};device_live++;return 0;}
static int i2c_master_bus_rm_device(fake_device*d){free(d);device_live--;return 0;}
static int i2c_master_bus_reset(fake_bus*b){
 reset_port=b->port;resets[b->port]++;
 /* Mirror ESP32: reset may returnOK while a held SDA prevents a clean STOP. */
 poisoned[b->port]=!levels[b->port?21:18]||!levels[b->port?22:19];return 0;
}
static int transfer(fake_device*d,const void*w,unsigned wl,void*r,unsigned rl,int timeout,int operation){
 transfer_count++;last_timeout=timeout;last_port=d->bus->port;last_address=d->address;last_width=d->width;last_speed=d->speed;
 last_operation=operation;last_write_len=wl;last_read_len=rl;if(wl)memcpy(last_write,w,wl);
 if(rl)memset(r,0xa0+d->bus->port,rl);
 if(poisoned[d->bus->port]){poisoned[d->bus->port]=false;return ESP_ERR_INVALID_RESPONSE;}
 if(transfer_error==ESP_ERR_TIMEOUT)poisoned[d->bus->port]=true;
 return transfer_error;
}
static int i2c_master_transmit(fake_device*d,const void*w,unsigned wl,int t){return transfer(d,w,wl,NULL,0,t,1);}
static int i2c_master_receive(fake_device*d,void*r,unsigned rl,int t){return transfer(d,NULL,0,r,rl,t,2);}
static int i2c_master_transmit_receive(fake_device*d,const void*w,unsigned wl,void*r,unsigned rl,int t){return transfer(d,w,wl,r,rl,t,3);}
static int i2c_master_probe(fake_bus*b,unsigned address,int timeout){probe_count++;clock_us+=1000;return transfer_error?transfer_error:address==0x50?ESP_OK:ESP_ERR_NOT_FOUND;}
'''
COMMON = r'''
#include "core/device_profile.h"
#include "core/topology.h"
#include "core/msg_bus.h"
#include "transport/mcp_transport.h"
static profile_i2c_t i2c_config[2]={{1,18,19,0,3,232},{1,21,22,1,3,232}};
static profile_gpio_t gpio_profiles[14];
const profile_i2c_t *profile_i2c(int i){return &i2c_config[i];}
const profile_gpio_t *profile_gpio(int i){return &gpio_profiles[i];}
bool profile_gpio_capable(int pin,int mode,int pull,int trigger){
 if(pin==35)return mode==0&&pull==0;
 if(pin==36||pin==39)return mode==0&&pull==0&&trigger==0;
 return pin==13||pin==14||pin==18||pin==19||pin==21||pin==22||pin==23||pin==25||pin==26||pin==27||pin==32;
}
void profile_driver_failed(void){assert(0);}
static uint32_t test_session=1;
uint32_t mcp_transport_session_id(void){return test_session;}
bool mcp_transport_session_is_current(uint32_t s){return s!=0&&s==test_session;}
static ubcp_route_entry_t routes[16];static int route_count;
esp_err_t topology_register(uint8_t ch,uint8_t type,void*driver){routes[route_count++]=(ubcp_route_entry_t){ch,type,driver};return 0;}
const ubcp_route_entry_t *topology_find(uint8_t ch){for(int i=0;i<route_count;i++)if(routes[i].channel_id==ch)return &routes[i];return NULL;}
static uint8_t reply[2048];static unsigned reply_len,replies;static uint32_t reply_session,reply_timestamp;static uint8_t reply_cmd,reply_channel;static bool reply_has_timestamp;
void ubcp_frame_make_response(const ubcp_frame_t*r,ubcp_frame_t*s){*s=*r;}
esp_err_t msg_bus_send_frame(const ubcp_frame_t*r){replies++;reply_timestamp=r->timestamp;reply_cmd=r->cmd_code;reply_channel=r->channel_id;reply_has_timestamp=r->has_timestamp;reply_len=r->payload_len;reply_session=r->session_id;memcpy(reply,r->payload,reply_len);return 0;}
esp_err_t msg_bus_send_status_response(const ubcp_frame_t*r,uint8_t status){ubcp_frame_t s=*r;s.payload=&status;s.payload_len=1;return msg_bus_send_frame(&s);}
static unsigned flow_pauses,flow_last;
void msg_bus_update_flow_state(uint8_t m,uint8_t s,uint16_t used,uint16_t cap){flow_last=s;if(s)flow_pauses++;}
'''
I2C = COMMON + r'''
#include "modules/mod_i2c.c"
static uint8_t out[2048];
static unsigned request(int instance,int cmd,const uint8_t*p,unsigned len){
 ubcp_frame_t r={.cmd_code=cmd,.payload=(uint8_t *)p,.payload_len=len,.session_id=test_session};
 return execute(&contexts[instance],&r,out);
}
static void release_sda(void){if(clock_us>=50000)levels[19]=1;}
static void cancel_session(void){if(clock_us>=50000)test_session=2;}
static context_t *running;
static void finish_worker(void){running->stopping=true;}
static void run(context_t*c){running=c;c->stopping=false;queue_empty=finish_worker;worker(c);queue_empty=NULL;}
int main(void){
 levels[18]=levels[19]=levels[21]=levels[22]=1;
 assert(init()==0&&route_count==2&&bus_live==2&&mod_i2c_available());
 assert(contexts[0].queue!=contexts[1].queue);
 contexts[0].session=contexts[1].session=test_session;
 uint8_t mode=0;
 assert(request(0,0x34,NULL,0)==1&&out[0]==UBCP_ERR_NOT_OPEN);
 assert(request(0,0x30,&mode,1)==1&&out[0]==0);
 assert(request(0,0x30,&mode,1)==1&&out[0]==UBCP_ERR_ALREADY_OPEN);
 assert(request(1,0x30,&mode,1)==1&&out[0]==0);
 uint8_t rd[]={0,0x50,2,0x12,0x34,0,4};
 assert(request(0,0x34,rd,sizeof(rd))==7&&out[0]==0&&out[3]==0xa0&&last_operation==3);
 assert(last_write_len==2&&last_write[0]==0x12&&last_write[1]==0x34&&last_width==7&&last_speed==100000);
 assert(request(1,0x34,rd,sizeof(rd))==7&&out[3]==0xa1&&last_port==1&&last_speed==400000&&device_live==2);
 int transfers=transfer_count;
 assert(request(0,0x34,rd,sizeof(rd)-1)==1&&out[0]==2&&transfer_count==transfers);
 uint8_t wr[]={0,0x50,2,0x12,0x34,0,2,0x88,0x99};
 assert(request(0,0x33,wr,sizeof(wr))==3&&out[1]==0&&out[2]==2);
 assert(last_write_len==4&&!memcmp(last_write,"\x12\x34\x88\x99",4));
 uint8_t bare[]={0,0x50,0,0,3};assert(request(0,0x34,bare,5)==6&&last_operation==2);
 uint8_t combined[]={0,0x50,0,1,0,2,0x42};assert(request(0,0x35,combined,7)==5&&last_operation==3);
 combined[3]=0;assert(request(0,0x35,combined,6)==5&&last_operation==2);
 uint8_t oversized[]={0,0x50,0,7,254};assert(request(0,0x34,oversized,5)==1&&out[0]==2);
 uint8_t invalid[]={4,0,0,0,1};assert(request(0,0x34,invalid,5)==1&&out[0]==UBCP_ERR_I2C_ADDR_INVALID);
 transfer_error=ESP_ERR_INVALID_RESPONSE;transfers=transfer_count;
 assert(request(0,0x33,wr,sizeof(wr))==1&&out[0]==UBCP_ERR_I2C_NACK&&transfer_count==transfers+1);
 transfers=transfer_count;clock_us=0;levels[19]=0;poisoned[0]=true;
 assert(request(0,0x34,rd,sizeof(rd))==1&&out[0]==UBCP_ERR_TIMEOUT&&reset_port==-1&&clock_us==1000000&&transfer_count==transfers&&contexts[0].needs_reset);
 /* Device recreation alone cannot clear the poisoned controller; deferred reset can. */
 levels[19]=1;transfer_error=0;
 assert(request(0,0x31,NULL,0)==1&&out[0]==0);mode=0;assert(request(0,0x30,&mode,1)==1&&out[0]==0);
 assert(contexts[0].needs_reset);assert(request(0,0x33,wr,sizeof(wr))==3&&out[0]==0&&transfer_count==transfers+1&&resets[0]==1&&!resets[1]);
 transfer_error=ESP_ERR_TIMEOUT;
 assert(request(0,0x34,rd,sizeof(rd))==1&&out[0]==UBCP_ERR_TIMEOUT&&reset_port==0&&device_live==1);
 transfer_error=0;assert(request(1,0x34,rd,sizeof(rd))==7&&out[3]==0xa1);
 uint8_t scan[]={8,0x77};assert(request(0,0x36,scan,2)==3&&out[1]==1&&out[2]==0x50&&resets[0]==2&&!contexts[0].needs_reset);
 /* Preflight, recovery and transaction share one request deadline. */
 clock_us=0;levels[19]=0;delay_hook=release_sda;transfers=transfer_count;
 assert(request(0,0x34,rd,sizeof(rd))==7&&out[0]==0&&clock_us==50000&&last_timeout==950&&transfer_count==transfers+1);
 delay_hook=NULL;clock_us=0;levels[19]=0;transfers=transfer_count;delay_hook=cancel_session;
 assert(request(0,0x34,rd,sizeof(rd))==1&&out[0]==UBCP_ERR_PERMISSION&&clock_us==50000&&transfer_count==transfers);
 delay_hook=NULL;levels[19]=1;test_session=1;contexts[0].session=1;
 /* Scan also resets after release without discarding the first probe. */
 assert(request(0,0x36,scan,2)==3&&out[1]==1&&out[2]==0x50&&!contexts[0].needs_reset);
 contexts[0].timeout=60;clock_us=0;levels[19]=0;delay_hook=release_sda;probe_count=0;
 assert(request(0,0x36,scan,2)==1&&out[0]==UBCP_ERR_TIMEOUT&&clock_us==60000&&probe_count==10);
 delay_hook=NULL;contexts[0].timeout=1000;

 uint8_t config[]={0,6,0x1a,0x80,0,10};assert(request(0,0x32,config,6)==1&&out[0]==0&&contexts[0].speed==400000);
 config[5]=0;assert(request(0,0x32,config,6)==1&&out[0]==2&&contexts[0].timeout==10);
 assert(request(0,0x31,NULL,0)==1&&out[0]==0);mode=1;assert(request(0,0x30,&mode,1)==1&&out[0]==0);
 uint8_t ten[]={3,0xff,0,0,1};assert(request(0,0x34,ten,5)==4&&last_address==1023&&last_width==10);
 assert(request(0,0x36,scan,2)==1&&out[0]==UBCP_ERR_NOT_SUPPORT);
 /* The dispatcher copies input; queue backpressure has a fixed bound. */
 defaults(&contexts[0]);
 uint8_t open_mode=0;ubcp_frame_t q={.cmd_code=0x30,.channel_id=8,.session_id=test_session,.payload=&open_mode,.payload_len=1};
 for(int i=0;i<4;i++)handle(&q);handle(&q);assert(reply[0]==UBCP_ERR_BUSY&&uxQueueMessagesWaiting(contexts[0].queue)==4);
 open_mode=1;run(&contexts[0]);assert(contexts[0].mode==0); /* copied payload, not parser memory */
 replies=0;q.session_id=test_session;handle(&q);test_session++;run(&contexts[0]);assert(!replies&&!contexts[0].open);
 stop();assert(bus_live==0&&device_live==0&&!contexts[0].queue&&!contexts[1].out);
 task_fail=1;assert(init()==ESP_ERR_NO_MEM&&bus_live==0&&!contexts[0].out&&!contexts[0].queue);
 return 0;
}
'''
GPIO = COMMON + r'''
#include "modules/mod_gpio.c"
static uint8_t out[9];
static void finish_event_tick(void){clock_us+=10000;stopping=true;}
static void tick(void){stopping=false;queue_empty=finish_event_tick;event_task(NULL);queue_empty=NULL;}
static unsigned request(int group,int cmd,const uint8_t*p,unsigned len){ubcp_frame_t r={.cmd_code=cmd,.payload=(uint8_t *)p,.payload_len=len};return execute(&r,&groups[group],out);}
int main(void){
 for(int i=0;i<14;i++)gpio_profiles[i].pin=255;
 gpio_profiles[0]=(profile_gpio_t){23,3,0,0,0};
 gpio_profiles[1]=(profile_gpio_t){27,3,0,0,0};
 gpio_profiles[2]=(profile_gpio_t){32,3,0,0,0};
 gpio_profiles[3]=(profile_gpio_t){35,1,0,0,0};
 assert(init()==0&&route_count==2&&mod_gpio_available()&&groups[1].base==32);
 uint8_t write[]={23,1};assert(request(0,0x81,write,2)==1&&out[0]==0&&levels[23]==1);
 uint8_t read[]={3};levels[35]=1;assert(request(1,0x82,read,1)==2&&out[1]==1);
 uint8_t all[]={255,255,255,255};assert(request(1,0x87,all,4)==9&&be32(out+1)==8&&be32(out+5)==1);
 uint8_t mask[]={8,128,0,0,8,0,0,0}; /* GPIO23 and27 */
 assert(request(0,0x86,mask,8)==1&&out[0]==0&&levels[23]==0&&levels[27]==1);
 uint8_t dir[]={27,0};assert(request(0,0x80,dir,2)==1&&out[0]==0);
 int before=writes;mask[4]=0;mask[5]=128;
 assert(request(0,0x86,mask,8)==1&&out[0]==UBCP_ERR_GPIO_DIR_MISMATCH&&writes==before&&levels[23]==0);
 uint8_t invalid[]={22,1};assert(request(0,0x81,invalid,2)==1&&out[0]==UBCP_ERR_GPIO_IN_USE);
 invalid[0]=4;assert(request(0,0x81,invalid,2)==1&&out[0]==UBCP_ERR_GPIO_PIN_INVALID);
 uint8_t od[]={23,2};assert(request(0,0x80,od,2)==1&&out[0]==0&&modes[23]==GPIO_MODE_INPUT_OUTPUT_OD);
 levels[23]=0;read[0]=23;assert(request(0,0x82,read,1)==2&&out[1]==0);
 uint8_t int_en[]={27,3,10};assert(request(0,0x84,int_en,3)==1&&out[0]==0&&attached[27]);
 int_en[1]=5;assert(request(0,0x84,int_en,3)==1&&out[0]==2);
 int_en[1]=1;int_en[2]=0;assert(request(0,0x84,int_en,3)==1&&out[0]==2);
 uint8_t high_output[]={3,1};assert(request(1,0x80,high_output,2)==1&&out[0]==UBCP_ERR_GPIO_DIR_MISMATCH);
 uint8_t pull[]={3,1};assert(request(1,0x83,pull,2)==1&&out[0]==UBCP_ERR_GPIO_PIN_INVALID);
 int_en[1]=4;int_en[2]=10;assert(request(0,0x84,int_en,3)==1&&out[0]==0);
 levels[27]=1;interrupt_handler(&pins[1]);assert(!interrupts[27]&&pins[1].level_masked&&uxQueueMessagesWaiting(events)==1);
 sample_t sample;assert(xQueueReceive(events,&sample,0)&&sample.route==1&&sample.level==1&&sample.session==1);
 /* Debounce uses captured ISR time and never repeats a held level. */
 replies=0;assert(xQueueSend(events,&sample,0));tick();
 assert(replies==1&&reply_cmd==0x85&&reply_channel==10&&reply[0]==27&&reply[1]==4&&reply[2]==1&&reply_has_timestamp&&reply_timestamp==(uint32_t)sample.time);
 tick();assert(replies==1&&!interrupts[27]);levels[27]=0;tick();assert(interrupts[27]);
 int_en[1]=3;assert(request(0,0x84,int_en,3)==1&&out[0]==0);
 levels[27]=1;interrupt_handler(&pins[1]);levels[27]=0;tick();assert(replies==1); /* bounce */
 levels[27]=1;interrupt_handler(&pins[1]);tick();assert(replies==2&&reply[1]==1);
 pins[1].count=50;pins[1].window=clock_us;levels[27]=0;interrupt_handler(&pins[1]);tick();
 assert(replies==2&&pins[1].rate_masked&&!interrupts[27]&&flow_pauses);
 clock_us+=1000000;tick();assert(!pins[1].rate_masked&&interrupts[27]);
 /* Fifty real deliveries fit in one window; delivery51 is suppressed. */
 assert(subscribe(&pins[1],3,10)==0);replies=0;
 for(int i=0;i<50;i++){levels[27]=!(i&1);interrupt_handler(&pins[1]);tick();}
 assert(replies==50&&pins[1].count==50);
 levels[27]=1;interrupt_handler(&pins[1]);tick();assert(replies==50&&pins[1].rate_masked);tick();assert(flow_last==1);
 /* A storm on one input does not suppress a second pin or group. */
 assert(subscribe(&pins[3],1,1)==0);levels[35]=1;interrupt_handler(&pins[3]);tick();
 assert(replies==51&&reply_channel==11&&reply[0]==3&&reply[1]==1);
 assert(subscribe(&pins[1],3,10)==0);
 unsigned dropped_before=dropped,paused_before=flow_pauses;
 for(int i=0;i<EVENT_DEPTH+1;i++)interrupt_handler(&pins[1]);
 assert(uxQueueMessagesWaiting(events)==EVENT_DEPTH&&dropped==dropped_before+1);
 tick();assert(flow_pauses>paused_before&&uxQueueMessagesWaiting(events)==0);

 test_session=2;before=writes;assert(reset_subscriptions()==0&&pins[0].mode==2&&pins[1].mode==0&&!attached[27]&&!uxQueueMessagesWaiting(events)&&writes==before);
 stop();assert(!mod_gpio_available()&&!events&&!lock);
 task_fail=1;assert(init()==ESP_ERR_NO_MEM&&!events&&!lock&&!mod_gpio_available());
 return 0;
}
'''

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('compiler', nargs='?', default='cl' if os.name == 'nt' else 'cc')
    args = parser.parse_args()
    for name, source in [('I2C', I2C), ('GPIO', GPIO)]:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for filename in 'esp_err.h esp_timer.h freertos/FreeRTOS.h freertos/task.h freertos/queue.h freertos/semphr.h driver/gpio.h driver/i2c_master.h'.split():
                file = root / filename
                file.parent.mkdir(exist_ok=True)
                file.write_text('#include "mock.h"\n')
            (root / 'mock.h').write_text(MOCK)
            (root / 'test.c').write_text(source)
            if Path(args.compiler).stem.lower() == 'cl':
                command = [args.compiler, '/nologo', '/std:c11', '/experimental:c11atomics', '/utf-8', '/I.', '/I'+str(MAIN), 'test.c']
            else:
                command = [args.compiler, '-std=c11', '-I.', '-I'+str(MAIN), 'test.c', '-o', 'test']
            subprocess.run(command, cwd=root, check=True)
            subprocess.run([str(root / ('test.exe' if os.name == 'nt' else 'test'))], check=True)
        print(name + ' real driver protocol, isolation, ownership and cleanup: PASS')

if __name__ == '__main__':
    main()



