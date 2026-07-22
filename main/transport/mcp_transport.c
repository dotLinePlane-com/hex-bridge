/**
 * @file mcp_transport.c
 * @brief MCP 传输层实现 — UART1 收发与帧解析
 *
 * 接收任务 (mcp_recv_task):
 *   从 UART1 逐字节读取 → 流式帧解析（反转义+CRC） → 分发到消息总线
 *
 * 发送:
 *   通过互斥锁保护的 uart_write_bytes 直接发送线路帧
 */

#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"
#include "driver/uart.h"
#include "transport/mcp_transport.h"
#include "protocol/ubcp_frame.h"
#include "core/msg_bus.h"
#include "hex_config.h"
#include "utils/hex_log.h"

static const char *TAG = "mcp_transport";

/* ========================================================================
 * 私有数据
 * ======================================================================== */

/** 帧解析器 */
static ubcp_parser_t s_parser;

/** 解析器逻辑帧缓冲区 */
static uint8_t s_parse_buf[HEX_UBCP_FRAME_BUF_SIZE + UBCP_CRC_SIZE];

/** 发送互斥锁 */
static SemaphoreHandle_t s_tx_mutex = NULL;

/** 接收任务句柄 */
static TaskHandle_t s_recv_task_handle = NULL;

/** 运行标志 */
static volatile bool s_running = false;

/* ========================================================================
 * UART 硬件初始化
 * ======================================================================== */

static esp_err_t uart_hw_init(uint32_t baud_rate)
{
    if (baud_rate == 0) {
        baud_rate = HEX_MCP_UART_BAUD;
    }

    uart_config_t uart_config = {
        .baud_rate  = (int)baud_rate,
        .data_bits  = UART_DATA_8_BITS,
        .parity     = UART_PARITY_DISABLE,
        .stop_bits  = UART_STOP_BITS_1,
        .flow_ctrl  = UART_HW_FLOWCTRL_DISABLE,
        .source_clk = UART_SCLK_APB,
    };

    esp_err_t err;

    err = uart_driver_install(HEX_MCP_UART_NUM,
                              HEX_MCP_UART_RX_BUF_SIZE,
                              HEX_MCP_UART_TX_BUF_SIZE,
                              0, NULL, 0);
    if (err != ESP_OK) {
        HEX_LOGE(TAG, "UART 驱动安装失败: 0x%x", err);
        return err;
    }

    err = uart_param_config(HEX_MCP_UART_NUM, &uart_config);
    if (err != ESP_OK) {
        HEX_LOGE(TAG, "UART 参数配置失败: 0x%x", err);
        return err;
    }

    err = uart_set_pin(HEX_MCP_UART_NUM,
                       HEX_MCP_UART_TX_PIN,
                       HEX_MCP_UART_RX_PIN,
                       UART_PIN_NO_CHANGE,
                       UART_PIN_NO_CHANGE);
    if (err != ESP_OK) {
        HEX_LOGE(TAG, "UART 引脚配置失败: 0x%x", err);
        return err;
    }

    return ESP_OK;
}

/* ========================================================================
 * 接收任务
 * ======================================================================== */

/**
 * @brief MCP 接收任务
 *
 * 从 UART1 批量读取字节，逐字节送入流式帧解析器。
 * 当解析出完整帧时，提取帧内容并分发到消息总线。
 */
static void mcp_recv_task(void *arg)
{
    uint8_t rx_buf[256]; /* 每次从 UART 读取的批量缓冲区 */

    HEX_LOGI(TAG, "MCP 接收任务启动");

    while (s_running) {
        /* 从 UART 读取可用数据，最多等待 100ms */
        int len = uart_read_bytes(HEX_MCP_UART_NUM, rx_buf, sizeof(rx_buf),
                                  pdMS_TO_TICKS(100));
        if (len <= 0) {
            continue;
        }

        /* 逐字节送入解析器 */
        for (int i = 0; i < len; i++) {
            ubcp_parse_result_t result = ubcp_parser_feed(&s_parser, rx_buf[i]);

            switch (result) {
            case UBCP_PARSE_FRAME_OK: {
                /* 解析出完整帧 */
                ubcp_frame_t frame;
                if (ubcp_parser_get_frame(&s_parser, &frame) == ESP_OK) {
                    /* 版本检查 */
                    if (frame.version != UBCP_VERSION) {
                        HEX_LOGW(TAG, "版本不匹配: 收到 0x%02X, 期望 0x%02X",
                                 frame.version, UBCP_VERSION);
                        msg_bus_send_status_response(&frame, UBCP_ERR_VERSION);
                    } else {
                        /* 分发到消息总线 */
                        msg_bus_dispatch(&frame);
                    }
                }
                ubcp_parser_reset(&s_parser);
                break;
            }

            case UBCP_PARSE_ERR_CRC:
                HEX_LOGW(TAG, "CRC 校验失败，丢弃帧");
                ubcp_parser_reset(&s_parser);
                break;

            case UBCP_PARSE_ERR_OVERFLOW:
                HEX_LOGW(TAG, "帧缓冲区溢出，丢弃帧");
                ubcp_parser_reset(&s_parser);
                break;

            case UBCP_PARSE_ERR_ESCAPE:
                HEX_LOGW(TAG, "转义序列错误，丢弃帧");
                ubcp_parser_reset(&s_parser);
                break;

            case UBCP_PARSE_ERR_TOO_SHORT:
                HEX_LOGW(TAG, "帧太短，丢弃");
                /* 解析器已内部重置 */
                break;

            case UBCP_PARSE_NEED_MORE:
            default:
                break;
            }
        }
    }

    HEX_LOGI(TAG, "MCP 接收任务退出");
    vTaskDelete(NULL);
}

/* ========================================================================
 * 公共接口
 * ======================================================================== */

esp_err_t mcp_transport_init(uint32_t baud_rate)
{
    esp_err_t err;

    if (baud_rate == 0) {
        baud_rate = HEX_MCP_UART_BAUD;
    }

    err = uart_hw_init(baud_rate);
    if (err != ESP_OK) {
        return err;
    }

    /* 初始化帧解析器 */
    ubcp_parser_init(&s_parser, s_parse_buf, sizeof(s_parse_buf));

    /* 创建发送互斥锁 */
    s_tx_mutex = xSemaphoreCreateMutex();
    if (s_tx_mutex == NULL) {
        HEX_LOGE(TAG, "发送互斥锁创建失败");
        return ESP_ERR_NO_MEM;
    }

    /* 启动接收任务 */
    s_running = true;
    BaseType_t ret = xTaskCreate(mcp_recv_task, "mcp_recv",
                                 HEX_MCP_RECV_TASK_STACK,
                                 NULL,
                                 HEX_MCP_RECV_TASK_PRIO,
                                 &s_recv_task_handle);
    if (ret != pdPASS) {
        HEX_LOGE(TAG, "接收任务创建失败");
        return ESP_ERR_NO_MEM;
    }

    HEX_LOGI(TAG, "MCP 传输层初始化完成 (UART%d, TX=GPIO%d, RX=GPIO%d, %lu bps)",
             HEX_MCP_UART_NUM, HEX_MCP_UART_TX_PIN, HEX_MCP_UART_RX_PIN,
             baud_rate);
    return ESP_OK;
}

esp_err_t mcp_transport_send(const uint8_t *data, size_t len)
{
    if (!s_running || s_tx_mutex == NULL) {
        return ESP_ERR_INVALID_STATE;
    }

    /* 获取互斥锁，防止多任务同时发送造成帧交错 */
    if (xSemaphoreTake(s_tx_mutex, pdMS_TO_TICKS(1000)) != pdTRUE) {
        HEX_LOGW(TAG, "发送互斥锁超时");
        return ESP_ERR_TIMEOUT;
    }

    int written = uart_write_bytes(HEX_MCP_UART_NUM, data, len);

    xSemaphoreGive(s_tx_mutex);

    if (written < 0) {
        HEX_LOGE(TAG, "UART 写入失败");
        return ESP_FAIL;
    }

    HEX_LOGD(TAG, "发送 %d 字节", written);
    return ESP_OK;
}

void mcp_transport_stop(void)
{
    s_running = false;

    /* 等待接收任务结束 */
    if (s_recv_task_handle != NULL) {
        vTaskDelay(pdMS_TO_TICKS(200));
        s_recv_task_handle = NULL;
    }

    /* 删除互斥锁 */
    if (s_tx_mutex != NULL) {
        vSemaphoreDelete(s_tx_mutex);
        s_tx_mutex = NULL;
    }

    /* 卸载 UART 驱动 */
    uart_driver_delete(HEX_MCP_UART_NUM);

    HEX_LOGI(TAG, "MCP 传输层已停止");
}
