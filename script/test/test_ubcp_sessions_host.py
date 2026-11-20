"""Compile and run real UBCP transport/bus/frame code against deterministic I/O.
Usage: python script/test/test_ubcp_sessions_host.py --cc PATH_TO_COMPILER
For Zig: --cc PATH_TO_ZIG --zig. Uses temporary platform headers only.
"""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile

PLATFORM = r'''
#pragma once
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
typedef int esp_err_t;
#define ESP_OK 0
#define ESP_FAIL -1
#define ESP_ERR_INVALID_ARG 1
#define ESP_ERR_INVALID_STATE 2
#define ESP_ERR_NO_MEM 3
#define ESP_ERR_TIMEOUT 4
#define ESP_ERR_INVALID_SIZE 5
#define ESP_ERR_NOT_FOUND 6
#define pdTRUE 1
#define pdPASS 1
#define pdMS_TO_TICKS(x) (x)
#define portMAX_DELAY ((unsigned)-1)
typedef unsigned TickType_t;
typedef void *SemaphoreHandle_t;
typedef void *TaskHandle_t;
SemaphoreHandle_t xSemaphoreCreateMutex(void);
int xSemaphoreTake(SemaphoreHandle_t,unsigned);
int xSemaphoreGive(SemaphoreHandle_t);
unsigned xTaskGetTickCount(void);
void vTaskDelay(unsigned);
void vTaskDelete(void *);
int xTaskCreate(void (*)(void *),const char *,unsigned,void *,int,void **);
#define HEX_LOGE(...) ((void)0)
#define HEX_LOGW(...) ((void)0)
#define HEX_LOGI(...) ((void)0)
#define HEX_LOGD(...) ((void)0)
#define HEX_UBCP_FRAME_BUF_SIZE 2062
#define HEX_MCP_UART_NUM 1
#define HEX_MCP_UART_BAUD 115200
#define HEX_MCP_UART_RX_BUF_SIZE 4096
#define HEX_MCP_UART_TX_BUF_SIZE 2048
#define HEX_MCP_UART_TX_PIN 4
#define HEX_MCP_UART_RX_PIN 34
#define HEX_MCP_RECV_TASK_STACK 6144
#define HEX_MCP_RECV_TASK_PRIO 10
#define UART_DATA_8_BITS 8
#define UART_PARITY_DISABLE 0
#define UART_STOP_BITS_1 1
#define UART_HW_FLOWCTRL_DISABLE 0
#define UART_SCLK_APB 0
#define UART_PIN_NO_CHANGE -1
typedef struct { int baud_rate,data_bits,parity,stop_bits,flow_ctrl,source_clk; } uart_config_t;
int uart_wait_tx_done(int,unsigned);
int uart_flush_input(int);
int uart_write_bytes(int,const void *,size_t);
int uart_read_bytes(int,void *,size_t,unsigned);
int uart_driver_install(int,int,int,int,void *,int);
int uart_driver_delete(int);
int uart_param_config(int,const uart_config_t *);
int uart_set_pin(int,int,int,int,int);
#define AF_INET 2
#define SOCK_STREAM 1
#define IPPROTO_TCP 6
#define SOL_SOCKET 1
#define SO_REUSEADDR 2
#define SO_KEEPALIVE 3
#define TCP_KEEPIDLE 4
#define TCP_KEEPINTVL 5
#define TCP_KEEPCNT 6
#define INADDR_ANY 0
#define SHUT_RDWR 2
#define MSG_DONTWAIT 0
#define F_SETFL 0
#define O_NONBLOCK 0
#define htons(x) (x)
#define htonl(x) (x)
struct sockaddr { int dummy; };
struct sockaddr_in { int sin_family,sin_port; struct { unsigned s_addr; } sin_addr; };
int socket(int,int,int);
int setsockopt(int,int,int,const void *,unsigned);
int bind(int,const struct sockaddr *,unsigned);
int listen(int,int);
int fcntl(int,int,...);
int accept(int,struct sockaddr *,void *);
int shutdown(int,int);
int close(int);
int recv(int,void *,size_t,int);
int send(int,const void *,size_t,int);
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cc', default=os.environ.get('CC', 'cc'))
    parser.add_argument('--zig', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    with tempfile.TemporaryDirectory(prefix='hex-ubcp-host-') as directory:
        work = Path(directory)
        (work / 'platform.h').write_text(PLATFORM)
        for name in ['esp_err.h', 'freertos/FreeRTOS.h', 'freertos/task.h',
                     'freertos/semphr.h', 'driver/uart.h', 'lwip/sockets.h',
                     'hex_config.h', 'utils/hex_log.h', 'fcntl.h']:
            path = work / name
            path.parent.mkdir(exist_ok=True, parents=True)
            path.write_text('#include "platform.h"\n')
        binary = work / ('sessions.exe' if os.name == 'nt' else 'sessions')
        command = [args.cc] + (['cc'] if args.zig else []) + [
            '-std=c11', '-Wall', '-Wextra', '-Werror',
            '-Wno-unused-parameter', '-Wno-unused-variable',
            '-I', str(work), '-I', str(root / 'main'),
            str(root / 'script/test/host/test_ubcp_sessions.c'),
            str(root / 'main/core/msg_bus.c'),
            str(root / 'main/protocol/ubcp_frame.c'), '-o', str(binary)]
        subprocess.run(command, check=True)
        subprocess.run([str(binary)], check=True)


if __name__ == '__main__':
    main()
