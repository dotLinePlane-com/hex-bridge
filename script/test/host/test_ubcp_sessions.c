/* Deterministic tests compile production frame, bus and transport code with
 * mocked platform I/O. No timing races, physical ports or ESP32 are required. */
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "transport/mcp_transport.c"

static int mutex_count, uart_writes, tcp_writes, tx_waits, rx_flushes;
static int transition_on_bus_lock, partial_send, fail_send, dispatches;
static ubcp_frame_t delayed;
SemaphoreHandle_t xSemaphoreCreateMutex(void) { return (void *)(intptr_t)++mutex_count; }
int xSemaphoreTake(SemaphoreHandle_t mutex, unsigned wait) {
    (void)wait;
    if ((intptr_t)mutex == 1 && transition_on_bus_lock) {
        transition_on_bus_lock = 0;
        next_session();
    }
    return pdTRUE;
}
int xSemaphoreGive(SemaphoreHandle_t mutex) { (void)mutex; return 1; }
unsigned xTaskGetTickCount(void) { static unsigned tick; return ++tick; }
void vTaskDelay(unsigned ticks) { (void)ticks; }
void vTaskDelete(void *task) { (void)task; }
int xTaskCreate(void (*fn)(void *), const char *name, unsigned stack, void *arg, int prio, void **task) {
    (void)fn; (void)name; (void)stack; (void)arg; (void)prio; *task = (void *)1; return pdPASS;
}
int uart_wait_tx_done(int n, unsigned wait) { (void)n; assert(wait == portMAX_DELAY); ++tx_waits; return 0; }
int uart_flush_input(int n) { (void)n; ++rx_flushes; return 0; }
int uart_write_bytes(int n, const void *p, size_t len) { (void)n; (void)p; ++uart_writes; return (int)len; }
int uart_read_bytes(int n, void *p, size_t len, unsigned wait) { (void)n; (void)p; (void)len; (void)wait; return 0; }
int uart_driver_install(int n,int rx,int tx,int q,void *queue,int flags) { return 0; }
int uart_driver_delete(int n) { return 0; }
int uart_param_config(int n,const uart_config_t *c) { return 0; }
int uart_set_pin(int n,int tx,int rx,int rts,int cts) { return 0; }
int socket(int af,int type,int protocol) { return 100; }
int setsockopt(int fd,int level,int opt,const void *v,unsigned len) { return 0; }
int bind(int fd,const struct sockaddr *addr,unsigned len) { return 0; }
int listen(int fd,int backlog) { return 0; }
int fcntl(int fd,int command,...) { return 0; }
int accept(int fd,struct sockaddr *addr,void *len) { return -1; }
int shutdown(int fd,int how) { return 0; }
int close(int fd) { return 0; }
int recv(int fd,void *buf,size_t len,int flags) { errno = EAGAIN; return -1; }
int send(int fd,const void *buf,size_t len,int flags) {
    ++tcp_writes;
    if (fail_send && --fail_send == 0) { errno = ECONNRESET; return -1; }
    return partial_send && len > 3 ? 3 : (int)len;
}
static void defer(const ubcp_frame_t *req) { delayed = *req; ++dispatches; }
static void clear_counts(void) { uart_writes = tcp_writes = 0; }
int main(void) {
    assert(msg_bus_init() == ESP_OK); /* bus mutex = 1 */
    s_lock = xSemaphoreCreateMutex(); s_running = true;
    ubcp_parser_init(&s_parser,s_parse_buf,sizeof(s_parse_buf));
    const hex_module_t module = {.name="deferred",.cmd_range_start=0,.cmd_range_end=0,.handle_cmd=defer};
    assert(msg_bus_register_module(&module) == ESP_OK);
    ubcp_frame_t req = {.version=UBCP_VERSION,.flags=UBCP_FLAG_ACK,.seq_num=7,.cmd_code=0};
    uint8_t wire[64], second[64]; size_t len, other_len;
    req.session_id = mcp_transport_session_id();
    assert(ubcp_frame_build(&req,wire,sizeof(wire),&len) == ESP_OK);
    req.session_id += 100;
    assert(ubcp_frame_build(&req,second,sizeof(second),&other_len) == ESP_OK);
    assert(len == other_len && memcmp(wire,second,len) == 0);
    feed(wire,(int)len,mcp_transport_session_id());
    assert(dispatches == 1 && delayed.session_id == s_session);
    uint32_t original = delayed.session_id;
    next_session(); s_client = 42; clear_counts();
    assert(msg_bus_send_status_response(&delayed,0) == ESP_ERR_INVALID_STATE);
    assert(!uart_writes && !tcp_writes);
    puts("PASS delayed UART response rejected after TCP takeover");
    delayed.session_id = s_session;
    fallback(); clear_counts();
    assert(msg_bus_send_status_response(&delayed,0) == ESP_ERR_INVALID_STATE);
    assert(!uart_writes && !tcp_writes);
    puts("PASS delayed TCP response rejected after UART fallback");
    next_session(); s_client = 43; clear_counts();
    assert(msg_bus_send_status_response(&delayed,0) == ESP_ERR_INVALID_STATE);
    assert(!uart_writes && !tcp_writes);
    puts("PASS delayed TCP response rejected after remote reconnect");
    delayed.session_id = s_session;
    s_online = true;
    mcp_transport_set_network_ready(false); clear_counts();
    assert(!s_online && s_client == -1);
    assert(msg_bus_send_status_response(&delayed,0) == ESP_ERR_INVALID_STATE);
    assert(!uart_writes && !tcp_writes);
    puts("PASS IP loss drops delayed TCP response and restores UART");
    next_session(); s_client = 44;
    ubcp_frame_t event;
    ubcp_frame_make_event(&event,0x14,3,8);
    transition_on_bus_lock = 1; clear_counts();
    assert(msg_bus_send_frame(&event) == ESP_ERR_INVALID_STATE);
    assert(!uart_writes && !tcp_writes);
    puts("PASS event queued on bus mutex cannot cross ownership boundary");
    delayed.session_id = s_session;
    partial_send = 1; clear_counts();
    assert(msg_bus_send_status_response(&delayed,0) == ESP_OK);
    assert(tcp_writes > 1 && !uart_writes);
    puts("PASS partial TCP writes complete atomically to exclusive owner");
    fail_send = 2; original = s_session;
    assert(msg_bus_send_status_response(&delayed,0) == ESP_FAIL);
    assert(s_client == -1 && s_session != original && !uart_writes);
    fail_send = partial_send = 0;
    puts("PASS failed partial stream closes and restores UART without replay");
    clear_counts(); delayed.session_id = s_session;
    assert(msg_bus_send_status_response(&delayed,0) == ESP_OK);
    assert(uart_writes == 1 && !tcp_writes);
    puts("PASS fresh response delivered exclusively to fallback UART");
    dispatches = 0;
    feed(wire,6,s_session); next_session();
    feed(wire+6,(int)len-6,s_session);
    assert(dispatches == 0);
    feed(wire,(int)len,s_session);
    assert(dispatches == 1);
    assert(tx_waits && rx_flushes);
    puts("PASS parser drops half frame at session boundary and accepts fresh frame");
    return 0;
}
