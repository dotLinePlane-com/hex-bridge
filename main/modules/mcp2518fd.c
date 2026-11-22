/**
 * @file mcp2518fd.c
 * @brief MCP2518FD CAN FD 控制器 SPI 驱动实现
 *
 * 基于 Microchip 官方驱动 (drv_canfdspi) 移植到 ESP-IDF SPI Master。
 */

#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include "driver/spi_master.h"
#include "esp_log.h"
#include "core/device_profile.h"
#include "core/spi_bus_manager.h"
#include "hex_config.h"
#include "modules/mcp2518fd.h"

static const char *TAG = "mcp2518fd";

/* ========================================================================
 * SPI 设备句柄
 * ======================================================================== */

static spi_device_handle_t s_spi_dev = NULL;
static SemaphoreHandle_t s_spi_mutex = NULL;
static bool s_bus_retained;
static int can_spi_host(void) { return profile_spi_host(true) == 2 ? SPI2_HOST : SPI3_HOST; }

/* ========================================================================
 * 位时序表 (40 MHz 系统时钟)
 * ======================================================================== */

/* 仲裁段查找表：BaudRateIndex → (BRP, TSEG1, TSEG2, SJW)
 * 系统时钟 40 MHz (20MHz 晶振 + PLL)
 * TSEG1 = PropSeg + PhaseSeg1 - 1
 * TSEG2 = PhaseSeg2 - 1
 * SJW   = SJW - 1
 */
static const mcp2518fd_nom_timing_t s_nom_timing[] = {
    {99, 13, 4, 3},   /* 0x00: 10 kbps  */
    {49, 13, 4, 3},   /* 0x01: 20 kbps  */
    {19, 13, 4, 3},   /* 0x02: 50 kbps  */
    {9,  13, 4, 3},   /* 0x03: 100 kbps */
    {7,  13, 4, 3},   /* 0x04: 125 kbps */
    {3,  13, 4, 3},   /* 0x05: 250 kbps */
    {1,  13, 4, 3},   /* 0x06: 500 kbps (默认) */
    {0,  16, 6, 3},   /* 0x07: 800 kbps */
    {0,  13, 4, 3},   /* 0x08: 1000 kbps */
};

#define NOM_TIMING_COUNT (sizeof(s_nom_timing) / sizeof(s_nom_timing[0]))

/* FD 数据段查找表：FdBaudRateIndex → (BRP, TSEG1, TSEG2, SJW, TDCO, TDCEn)
 * 索引 0x00 = 不使用 FD
 */
static const mcp2518fd_data_timing_t s_data_timing[] = {
    {0, 0, 0, 0, 0, false},       /* 0x00: 不使用 FD */
    {0, 13, 4, 3, 0, false},      /* 0x01: 1 Mbps   */
    {0, 6, 1, 1, 0, true},        /* 0x02: 2 Mbps   */
    {0, 2, 0, 0, 0, true},        /* 0x03: 4 Mbps   */
    {0, 1, 0, 0, 0, true},        /* 0x04: 5 Mbps   */
};

#define DATA_TIMING_COUNT (sizeof(s_data_timing) / sizeof(s_data_timing[0]))

/* ========================================================================
 * 内部 SPI 事务函数
 * ======================================================================== */

static esp_err_t spi_transfer(const uint8_t *tx_buf, uint8_t *rx_buf,
                              size_t len)
{
    if (s_spi_dev == NULL) {
        return ESP_ERR_INVALID_STATE;
    }

    if (xSemaphoreTake(s_spi_mutex, pdMS_TO_TICKS(100)) != pdTRUE) {
        ESP_LOGW(TAG, "SPI 互斥锁超时");
        return ESP_ERR_TIMEOUT;
    }

    spi_transaction_t t = {0};
    t.length = len * 8;
    t.tx_buffer = tx_buf;
    if (rx_buf) {
        t.rx_buffer = rx_buf;
        t.rxlength = len * 8;
    }

    esp_err_t err = spi_device_acquire_bus(s_spi_dev, portMAX_DELAY);
    if (err == ESP_OK) {
        err = spi_device_transmit(s_spi_dev, &t);
        spi_device_release_bus(s_spi_dev);
    }

    xSemaphoreGive(s_spi_mutex);
    return err;
}

/* ========================================================================
 * 寄存器访问
 * ======================================================================== */

esp_err_t mcp2518fd_read_byte(uint16_t addr, uint8_t *rxd)
{
    uint8_t tx[3], rx[3];
    tx[0] = (uint8_t)((MCP2518FD_INS_READ << 4) + ((addr >> 8) & 0xF));
    tx[1] = (uint8_t)(addr & 0xFF);
    tx[2] = 0;

    esp_err_t err = spi_transfer(tx, rx, sizeof(tx));
    if (err == ESP_OK && rxd) {
        *rxd = rx[2];
    }
    return err;
}

esp_err_t mcp2518fd_write_byte(uint16_t addr, uint8_t txd)
{
    uint8_t tx[3];
    tx[0] = (uint8_t)((MCP2518FD_INS_WRITE << 4) + ((addr >> 8) & 0xF));
    tx[1] = (uint8_t)(addr & 0xFF);
    tx[2] = txd;

    return spi_transfer(tx, NULL, sizeof(tx));
}

esp_err_t mcp2518fd_read_word(uint16_t addr, uint32_t *rxd)
{
    uint8_t tx[6], rx[6];
    tx[0] = (uint8_t)((MCP2518FD_INS_READ << 4) + ((addr >> 8) & 0xF));
    tx[1] = (uint8_t)(addr & 0xFF);
    memset(&tx[2], 0, 4);

    esp_err_t err = spi_transfer(tx, rx, sizeof(tx));
    if (err == ESP_OK && rxd) {
        *rxd = 0;
        for (int i = 0; i < 4; i++) {
            *rxd |= ((uint32_t)rx[i + 2]) << (i * 8);
        }
    }
    return err;
}

esp_err_t mcp2518fd_write_word(uint16_t addr, uint32_t txd)
{
    uint8_t tx[6];
    tx[0] = (uint8_t)((MCP2518FD_INS_WRITE << 4) + ((addr >> 8) & 0xF));
    tx[1] = (uint8_t)(addr & 0xFF);
    for (int i = 0; i < 4; i++) {
        tx[i + 2] = (uint8_t)((txd >> (i * 8)) & 0xFF);
    }

    return spi_transfer(tx, NULL, sizeof(tx));
}

esp_err_t mcp2518fd_read_bytes(uint16_t addr, uint8_t *rxd, uint16_t n)
{
    uint8_t tx[3 + 256];
    if (n > 256) {
        n = 256;
    }
    tx[0] = (uint8_t)((MCP2518FD_INS_READ << 4) + ((addr >> 8) & 0xF));
    tx[1] = (uint8_t)(addr & 0xFF);
    memset(&tx[2], 0, n);

    esp_err_t err = spi_transfer(tx, tx, 2 + n);
    if (err == ESP_OK && rxd) {
        memcpy(rxd, &tx[2], n);
    }
    return err;
}

esp_err_t mcp2518fd_write_bytes(uint16_t addr, const uint8_t *txd, uint16_t n)
{
    uint8_t tx[3 + 256];
    if (n > 256) {
        n = 256;
    }
    tx[0] = (uint8_t)((MCP2518FD_INS_WRITE << 4) + ((addr >> 8) & 0xF));
    tx[1] = (uint8_t)(addr & 0xFF);
    if (txd) {
        memcpy(&tx[2], txd, n);
    } else {
        memset(&tx[2], 0, n);
    }

    return spi_transfer(tx, NULL, 2 + n);
}

/* ========================================================================
 * 振荡器控制
 * ======================================================================== */

esp_err_t mcp2518fd_osc_enable(void)
{
    uint8_t b0 = 0;
    esp_err_t err;

    for (int attempt = 0; attempt < 3; attempt++) {
        err = mcp2518fd_read_byte(MCP2518FD_REG_OSC, &b0);
        if (err != ESP_OK) {
            return err;
        }
        b0 &= ~((1 << 5) | (1 << 6) | (1 << 4) | (1 << 2) | (1 << 0));
        b0 |=  (0 << 5) | (0 << 6) | (0 << 4) | (0 << 2) | (0 << 0);
        err = mcp2518fd_write_byte(MCP2518FD_REG_OSC, b0);
        if (err != ESP_OK) {
            return err;
        }
        vTaskDelay(pdMS_TO_TICKS(5) + 1);

        uint8_t verify = 0;
        err = mcp2518fd_read_byte(MCP2518FD_REG_OSC, &verify);
        if (err == ESP_OK && (verify & 0x04) == 0) {
            break;
        }
        ESP_LOGW(TAG, "OSC write verify failed (attempt %d): wrote=0x%02X read=0x%02X",
                 attempt + 1, b0, verify);
    }

    uint32_t osc = 0;
    for (int i = 0; i < 150; i++) {
        err = mcp2518fd_read_word(MCP2518FD_REG_OSC, &osc);
        if (err != ESP_OK) {
            return err;
        }
        if (osc & (1u << 10)) {
            return ESP_OK;
        }
        vTaskDelay(pdMS_TO_TICKS(1) + 1);
    }
    ESP_LOGE(TAG, "振荡器未就绪 (OSCRDY=0), OSC=0x%08X", (unsigned)osc);
    return ESP_ERR_TIMEOUT;
}

/* ========================================================================
 * 收发器待机控制
 * ======================================================================== */

esp_err_t mcp2518fd_xstby_enable(void)
{
    /* IOCON 寄存器:
     * byte0: TRIS1(bit1) TRIS0(bit0) XSTBYEN(bit6)
     * byte2: LAT1(bit9) LAT0(bit8)
     * byte3: PinMode1(bit25) PinMode0(bit24)
     */

    /* 1. 读 IOCON 字节0 */
    uint8_t b0 = 0;
    esp_err_t err = mcp2518fd_read_byte(MCP2518FD_REG_IOCON, &b0);
    if (err != ESP_OK) {
        return err;
    }

    /* 2. 使能 XSTBYEN, GPIO0 设为输出 (TRIS0=0) */
    b0 |= (1 << 6);          /* XSTBYEN */
    b0 &= ~(1 << 0);         /* TRIS0 = 0 (输出) */
    b0 |= (1 << 1);          /* TRIS1 = 1 (输入, 保持 INT1) */
    err = mcp2518fd_write_byte(MCP2518FD_REG_IOCON, b0);
    if (err != ESP_OK) {
        return err;
    }

    /* 3. 读 IOCON 字节1 (LAT0/LAT1) */
    uint8_t b1 = 0;
    err = mcp2518fd_read_byte(MCP2518FD_REG_IOCON + 1, &b1);
    if (err != ESP_OK) {
        return err;
    }

    /* 4. LAT0=0 (STBY 低电平 = 正常工作模式) */
    b1 &= ~(1 << 0);         /* LAT0 = 0 */
    err = mcp2518fd_write_byte(MCP2518FD_REG_IOCON + 1, b1);
    if (err != ESP_OK) {
        return err;
    }

    /* 5. PinMode0=1 (GPIO 模式, 非 INT0), PinMode1=0 (INT1 中断模式) */
    uint8_t b3 = 0;
    err = mcp2518fd_read_byte(MCP2518FD_REG_IOCON + 3, &b3);
    if (err != ESP_OK) {
        return err;
    }
    b3 &= ~(1 << 1);         /* PM1 = 0 (INT1 = 中断模式) */
    b3 |= (1 << 0);          /* PM0 = 1 (INT0 = GPIO for XSTBY) */
    err = mcp2518fd_write_byte(MCP2518FD_REG_IOCON + 3, b3);
    if (err != ESP_OK) {
        return err;
    }

    ESP_LOGI(TAG, "XSTBY 已使能 (GPIO0 输出低 → 收发器正常模式)");
    return ESP_OK;
}

/* ========================================================================
 * 位时序表
 * ======================================================================== */

esp_err_t mcp2518fd_reset(void)
{
    uint8_t tx[2] = { (MCP2518FD_INS_RESET << 4), 0x00 };
    return spi_transfer(tx, NULL, sizeof(tx));
}

esp_err_t mcp2518fd_opmode_select(uint8_t mode)
{
    uint8_t d = 0;
    esp_err_t err = mcp2518fd_read_byte(MCP2518FD_REG_CiCON + 3, &d);
    if (err != ESP_OK) {
        return err;
    }
    d &= ~0x07;
    d |= (mode & 0x07);
    err = mcp2518fd_write_byte(MCP2518FD_REG_CiCON + 3, d);
    if (err != ESP_OK) {
        return err;
    }

    for (int i = 0; i < 50; i++) {
        if (mcp2518fd_opmode_get() == mode) {
            return ESP_OK;
        }
        vTaskDelay(pdMS_TO_TICKS(1) + 1);
    }
    ESP_LOGW(TAG, "opmode_select timeout: req=%u, cur=%u", mode, mcp2518fd_opmode_get());
    return ESP_ERR_TIMEOUT;
}

uint8_t mcp2518fd_opmode_get(void)
{
    uint8_t d = 0;
    if (mcp2518fd_read_byte(MCP2518FD_REG_CiCON + 2, &d) != ESP_OK) {
        return 0xFF;
    }
    return (d >> 5) & 0x07;
}

/* ========================================================================
 * 配置
 * ======================================================================== */

esp_err_t mcp2518fd_bit_time_config(const mcp2518fd_nom_timing_t *nom,
                                    const mcp2518fd_data_timing_t *data)
{
    if (nom) {
        uint32_t word = ((uint32_t)nom->brp << 24) |
                        ((uint32_t)nom->tseg1 << 16) |
                        ((uint32_t)nom->tseg2 << 8) |
                        (uint32_t)nom->sjw;
        esp_err_t err = mcp2518fd_write_word(MCP2518FD_REG_CiNBTCFG, word);
        if (err != ESP_OK) {
            return err;
        }
    }

    if (data) {
        uint32_t word = ((uint32_t)data->brp << 24) |
                        ((uint32_t)data->tseg1 << 16) |
                        ((uint32_t)data->tseg2 << 8) |
                        (uint32_t)data->sjw;
        esp_err_t err = mcp2518fd_write_word(MCP2518FD_REG_CiDBTCFG, word);
        if (err != ESP_OK) {
            return err;
        }

        /* TDC 配置 */
        uint32_t tdc = 0;
        if (data->tdc_enable) {
            tdc = (2 << 16) |            /* TDCMOD = AUTO (10) */
                  ((uint32_t)(data->tdc_offset & 0x7F) << 8);  /* TDCO */
        }
        err = mcp2518fd_write_word(MCP2518FD_REG_CiTDC, tdc);
        if (err != ESP_OK) {
            return err;
        }
    }

    return ESP_OK;
}

esp_err_t mcp2518fd_txq_config(uint8_t fifo_size, uint8_t payload_size,
                               uint8_t priority)
{
    if (fifo_size < 1 || fifo_size > 32) {
        return ESP_ERR_INVALID_ARG;
    }

    /* PLSIZE 编码：8→0, 12→1, 16→2, 20→3, 24→4, 32→5, 48→6, 64→7 */
    uint8_t plsize = 7;
    if (payload_size <= 8)       plsize = 0;
    else if (payload_size <= 12) plsize = 1;
    else if (payload_size <= 16) plsize = 2;
    else if (payload_size <= 20) plsize = 3;
    else if (payload_size <= 24) plsize = 4;
    else if (payload_size <= 32) plsize = 5;
    else if (payload_size <= 48) plsize = 6;
    else                         plsize = 7;

    uint32_t word = ((uint32_t)(fifo_size - 1) << 24) |   /* FSIZE */
                    ((uint32_t)plsize << 29) |            /* PLSIZE */
                    ((uint32_t)(priority & 0x1F) << 17) | /* TXPRI */
                    (1 << 7);                             /* TXEN */
    return mcp2518fd_write_word(MCP2518FD_REG_CiTXQCON, word);
}

esp_err_t mcp2518fd_rx_fifo_config(uint8_t channel, uint8_t fifo_size,
                                   uint8_t payload_size)
{
    if (channel != MCP2518FD_CH_FIFO1 && channel != MCP2518FD_CH_FIFO2) {
        return ESP_ERR_INVALID_ARG;
    }
    if (fifo_size < 1 || fifo_size > 32) {
        return ESP_ERR_INVALID_ARG;
    }

    uint8_t plsize = 7;
    if (payload_size <= 8)       plsize = 0;
    else if (payload_size <= 12) plsize = 1;
    else if (payload_size <= 16) plsize = 2;
    else if (payload_size <= 20) plsize = 3;
    else if (payload_size <= 24) plsize = 4;
    else if (payload_size <= 32) plsize = 5;
    else if (payload_size <= 48) plsize = 6;
    else                         plsize = 7;

    uint16_t reg = MCP2518FD_REG_CiTXQCON + (channel * MCP2518FD_FIFO_OFFSET);
    uint32_t word = ((uint32_t)(fifo_size - 1) << 24) |
                    ((uint32_t)plsize << 29) |
                    (0 << 7);   /* TXEN = 0 (RX FIFO) */
    return mcp2518fd_write_word(reg, word);
}

/* ========================================================================
 * 过滤器
 * ======================================================================== */

esp_err_t mcp2518fd_filter_object_config(uint8_t filter, uint16_t sid,
                                         uint32_t eid, bool exide)
{
    if (filter >= MCP2518FD_FILTER_COUNT) {
        return ESP_ERR_INVALID_ARG;
    }

    uint32_t word = (uint32_t)(sid & 0x7FF) |
                    ((eid & 0x3FFFF) << 11) |
                    (exide ? (1u << 30) : 0);

    uint16_t reg = MCP2518FD_REG_CiFLTOBJ + (filter * MCP2518FD_FILTER_OFFSET);
    return mcp2518fd_write_word(reg, word);
}

esp_err_t mcp2518fd_filter_mask_config(uint8_t filter, uint16_t msid,
                                       uint32_t meid, bool mide)
{
    if (filter >= MCP2518FD_FILTER_COUNT) {
        return ESP_ERR_INVALID_ARG;
    }

    uint32_t word = (uint32_t)(msid & 0x7FF) |
                    ((meid & 0x3FFFF) << 11) |
                    (mide ? (1u << 30) : 0);

    uint16_t reg = MCP2518FD_REG_CiMASK + (filter * MCP2518FD_FILTER_OFFSET);
    return mcp2518fd_write_word(reg, word);
}

esp_err_t mcp2518fd_filter_to_fifo_link(uint8_t filter, uint8_t channel,
                                        bool enable)
{
    if (filter >= MCP2518FD_FILTER_COUNT) {
        return ESP_ERR_INVALID_ARG;
    }
    if (channel != MCP2518FD_CH_FIFO1 && channel != MCP2518FD_CH_FIFO2) {
        return ESP_ERR_INVALID_ARG;
    }

    uint8_t byte = (channel & 0x1F) | (enable ? 0x80 : 0x00);
    return mcp2518fd_write_byte(MCP2518FD_REG_CiFLTCON + filter, byte);
}

/* ========================================================================
 * 发送
 * ======================================================================== */

static void tx_obj_encode(const mcp2518fd_tx_obj_t *obj, uint8_t *buf,
                          uint8_t data_len)
{
    buf[0] = (uint8_t)(obj->id & 0xFF);
    buf[1] = (uint8_t)((obj->id >> 8) & 0xFF);
    buf[2] = (uint8_t)((obj->id >> 16) & 0xFF);
    buf[3] = (uint8_t)((obj->id >> 24) & 0xFF);
    buf[4] = (uint8_t)(obj->ctrl & 0xFF);
    buf[5] = (uint8_t)((obj->ctrl >> 8) & 0xFF);
    buf[6] = (uint8_t)((obj->ctrl >> 16) & 0xFF);
    buf[7] = (uint8_t)((obj->ctrl >> 24) & 0xFF);
    memcpy(&buf[8], obj->data, data_len);
}

esp_err_t mcp2518fd_txq_load(const mcp2518fd_tx_obj_t *tx_obj,
                             uint8_t data_len)
{
    if (data_len > MCP2518FD_MAX_DATA_BYTES) {
        return ESP_ERR_INVALID_ARG;
    }

    /* 读取 TXQUA 获取下一个可写地址 */
    uint32_t ua = 0;
    esp_err_t err = mcp2518fd_read_word(MCP2518FD_REG_CiTXQUA, &ua);
    if (err != ESP_OK) {
        return err;
    }
    uint16_t addr = MCP2518FD_RAM_START + (ua & 0x0FFF);

    /* 构造报文对象 (8 字节头 + 数据，补齐 4 字节对齐) */
    uint8_t buf[8 + MCP2518FD_MAX_DATA_BYTES + 3];
    tx_obj_encode(tx_obj, buf, data_len);

    uint16_t n = 8 + data_len;
    while (n % 4) {
        buf[n++] = 0;
    }

    err = mcp2518fd_write_bytes(addr, buf, n);
    if (err != ESP_OK) {
        return err;
    }

    /* 设置 UINC + TXREQ (CON byte1 = 0x03) */
    return mcp2518fd_write_byte(MCP2518FD_REG_CiTXQCON + 1, 0x03);
}

esp_err_t mcp2518fd_txq_reset(void)
{
    /* 在配置模式下完整复位 TXQ:
     * 1. FRESET=1 复位整个 FIFO (等待硬件自动清零)
     * 2. TXQUA 归零
     * 3. 清除 TXREQ/UINC
     */
    esp_err_t err = mcp2518fd_write_byte(MCP2518FD_REG_CiTXQCON + 1,
                                         (1 << 2));   /* FRESET = bit10 -> byte1 bit2 */
    if (err != ESP_OK) {
        return err;
    }
    /* 等待 FRESET 硬件清零 (最多 10ms) */
    for (int i = 0; i < 10; i++) {
        uint8_t b = 0;
        if (mcp2518fd_read_byte(MCP2518FD_REG_CiTXQCON + 1, &b) != ESP_OK) {
            return ESP_FAIL;
        }
        if ((b & (1 << 2)) == 0) {
            break;
        }
        vTaskDelay(pdMS_TO_TICKS(1));
    }
    err = mcp2518fd_write_word(MCP2518FD_REG_CiTXQUA, 0);
    if (err != ESP_OK) {
        return err;
    }
    return mcp2518fd_write_byte(MCP2518FD_REG_CiTXQCON + 1, 0x00);
}

bool mcp2518fd_txq_not_full(void)
{
    uint8_t sta = 0;
    if (mcp2518fd_read_byte(MCP2518FD_REG_CiTXQSTA, &sta) != ESP_OK) {
        return false;
    }
    return (sta & 0x01) != 0;   /* TXQNIF */
}

esp_err_t mcp2518fd_txq_wait_empty(uint32_t timeout_ms)
{
    TickType_t start = xTaskGetTickCount();
    uint8_t sta = 0;

    while (1) {
        if (mcp2518fd_read_byte(MCP2518FD_REG_CiTXQSTA, &sta) != ESP_OK) {
            return ESP_FAIL;
        }
        if (sta & 0x04) {   /* TXQEIF: TXQ 为空 */
            return ESP_OK;
        }
        if ((xTaskGetTickCount() - start) > pdMS_TO_TICKS(timeout_ms)) {
            return ESP_ERR_TIMEOUT;
        }
        vTaskDelay(pdMS_TO_TICKS(5));
    }
}

uint8_t mcp2518fd_txq_usage(void)
{
    uint8_t sta = 0;
    if (mcp2518fd_read_byte(MCP2518FD_REG_CiTXQSTA + 1, &sta) != ESP_OK) {
        return 0;
    }
    return (sta >> 3) & 0x1F;   /* TXQCI */
}

/* ========================================================================
 * 接收
 * ======================================================================== */

bool mcp2518fd_rx_not_empty(uint8_t channel)
{
    if (channel != MCP2518FD_CH_FIFO1 && channel != MCP2518FD_CH_FIFO2) {
        return false;
    }
    uint16_t reg = MCP2518FD_REG_CiTXQSTA + (channel * MCP2518FD_FIFO_OFFSET);
    uint8_t sta = 0;
    if (mcp2518fd_read_byte(reg, &sta) != ESP_OK) {
        return false;
    }
    return (sta & 0x01) != 0;   /* RxNotEmptyIF */
}

esp_err_t mcp2518fd_rx_read(uint8_t channel, mcp2518fd_rx_obj_t *rx_obj,
                            uint8_t *data_len)
{
    if (rx_obj == NULL || data_len == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    if (channel != MCP2518FD_CH_FIFO1 && channel != MCP2518FD_CH_FIFO2) {
        return ESP_ERR_INVALID_ARG;
    }

    uint16_t reg = MCP2518FD_REG_CiTXQCON + (channel * MCP2518FD_FIFO_OFFSET);

    /* 读取 FIFOCON/STA/UA */
    uint32_t fifo_reg[3];
    esp_err_t err = mcp2518fd_read_bytes(reg, (uint8_t *)fifo_reg, 12);
    if (err != ESP_OK) {
        return err;
    }

    uint32_t ua = fifo_reg[2];
    uint16_t addr = MCP2518FD_RAM_START + (ua & 0x0FFF);

    /* 读取 8 字节头 + 64 字节数据 (76 字节，RAM 对齐) */
    uint8_t buf[8 + MCP2518FD_MAX_DATA_BYTES];
    err = mcp2518fd_read_bytes(addr, buf, sizeof(buf));
    if (err != ESP_OK) {
        return err;
    }

    /* 解析头 */
    rx_obj->id = (uint32_t)buf[0] | ((uint32_t)buf[1] << 8) |
                 ((uint32_t)buf[2] << 16) | ((uint32_t)buf[3] << 24);
    rx_obj->ctrl = (uint32_t)buf[4] | ((uint32_t)buf[5] << 8) |
                   ((uint32_t)buf[6] << 16) | ((uint32_t)buf[7] << 24);

    uint8_t dlc = rx_obj->ctrl & 0x0F;
    *data_len = mcp2518fd_dlc_to_bytes(dlc);

    if (*data_len > MCP2518FD_MAX_DATA_BYTES) {
        *data_len = MCP2518FD_MAX_DATA_BYTES;
    }
    memcpy(rx_obj->data, &buf[8], *data_len);

    /* UINC 释放已读消息 */
    return mcp2518fd_write_byte(reg + 1, 0x01);
}

uint8_t mcp2518fd_rx_usage(uint8_t channel)
{
    if (channel != MCP2518FD_CH_FIFO1 && channel != MCP2518FD_CH_FIFO2) {
        return 0;
    }
    uint16_t reg = MCP2518FD_REG_CiTXQSTA + (channel * MCP2518FD_FIFO_OFFSET);
    uint8_t sta = 0;
    if (mcp2518fd_read_byte(reg + 1, &sta) != ESP_OK) {
        return 0;
    }
    return (sta >> 3) & 0x1F;   /* FIFOCI */
}

/* ========================================================================
 * 状态
 * ======================================================================== */

esp_err_t mcp2518fd_tec_rec_get(uint8_t *tec, uint8_t *rec)
{
    uint32_t word = 0;
    esp_err_t err = mcp2518fd_read_word(MCP2518FD_REG_CiTREC, &word);
    if (err != ESP_OK) {
        return err;
    }
    if (rec) *rec = (uint8_t)(word & 0xFF);
    if (tec) *tec = (uint8_t)((word >> 8) & 0xFF);
    return ESP_OK;
}

uint8_t mcp2518fd_error_state_get(void)
{
    uint8_t d = 0;
    if (mcp2518fd_read_byte(MCP2518FD_REG_CiTREC + 2, &d) != ESP_OK) {
        return 0;
    }
    return d & 0x3F;
}

esp_err_t mcp2518fd_bus_diagnostics_get(uint32_t *bd0, uint32_t *bd1)
{
    uint32_t w[2];
    esp_err_t err = mcp2518fd_read_bytes(MCP2518FD_REG_CiBDIAG0,
                                         (uint8_t *)w, 8);
    if (err != ESP_OK) {
        return err;
    }
    if (bd0) *bd0 = w[0];
    if (bd1) *bd1 = w[1];
    return ESP_OK;
}

esp_err_t mcp2518fd_int_flags_get(uint16_t *flags)
{
    if (flags == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    uint8_t lo = 0, hi = 0;
    esp_err_t err = mcp2518fd_read_byte(MCP2518FD_REG_CiINT, &lo);
    if (err != ESP_OK) return err;
    err = mcp2518fd_read_byte(MCP2518FD_REG_CiINT + 1, &hi);
    if (err != ESP_OK) return err;
    *flags = (uint16_t)(lo | (hi << 8));
    return ESP_OK;
}

esp_err_t mcp2518fd_int_flags_clear(uint16_t flags)
{
    /* 写 0 清除，写 1 无效果 */
    uint8_t lo = (uint8_t)(~(flags & 0xFF));
    uint8_t hi = (uint8_t)(~((flags >> 8) & 0xFF));
    esp_err_t err = mcp2518fd_write_byte(MCP2518FD_REG_CiINT, lo);
    if (err != ESP_OK) return err;
    return mcp2518fd_write_byte(MCP2518FD_REG_CiINT + 1, hi);
}

esp_err_t mcp2518fd_int_enable(uint16_t flags)
{
    uint8_t lo = 0, hi = 0;
    esp_err_t err = mcp2518fd_read_byte(MCP2518FD_REG_CiINT + 2, &lo);
    if (err != ESP_OK) return err;
    err = mcp2518fd_read_byte(MCP2518FD_REG_CiINT + 3, &hi);
    if (err != ESP_OK) return err;

    lo |= (uint8_t)(flags & 0xFF);
    hi |= (uint8_t)((flags >> 8) & 0xFF);

    err = mcp2518fd_write_byte(MCP2518FD_REG_CiINT + 2, lo);
    if (err != ESP_OK) return err;
    return mcp2518fd_write_byte(MCP2518FD_REG_CiINT + 3, hi);
}

uint8_t mcp2518fd_icode_get(void)
{
    uint8_t d = 0;
    if (mcp2518fd_read_byte(MCP2518FD_REG_CiVEC, &d) != ESP_OK) {
        return 0xFF;
    }
    return d & 0x7F;
}

/* ========================================================================
 * DLC 转换
 * ======================================================================== */

uint8_t mcp2518fd_dlc_to_bytes(uint8_t dlc)
{
    static const uint8_t dlc_map[] = { 0, 1, 2, 3, 4, 5, 6, 7, 8,
                                       12, 16, 20, 24, 32, 48, 64 };
    if (dlc > 15) {
        return 0;
    }
    return dlc_map[dlc];
}

uint8_t mcp2518fd_bytes_to_dlc(uint8_t n)
{
    if (n <= 8)       return n;
    else if (n <= 12) return 9;
    else if (n <= 16) return 10;
    else if (n <= 20) return 11;
    else if (n <= 24) return 12;
    else if (n <= 32) return 13;
    else if (n <= 48) return 14;
    else              return 15;
}

/* ========================================================================
 * 查找表查询
 * ======================================================================== */

/**
 * @brief 获取仲裁段位时序 (按 BaudRateIndex)
 */
const mcp2518fd_nom_timing_t *mcp2518fd_nom_timing_get(uint8_t index);

const mcp2518fd_nom_timing_t *mcp2518fd_nom_timing_get(uint8_t index)
{
    if (index >= NOM_TIMING_COUNT) {
        return NULL;
    }
    return &s_nom_timing[index];
}

/**
 * @brief 获取 FD 数据段位时序 (按 FdBaudRateIndex)
 */
const mcp2518fd_data_timing_t *mcp2518fd_data_timing_get(uint8_t index);

const mcp2518fd_data_timing_t *mcp2518fd_data_timing_get(uint8_t index)
{
    if (index >= DATA_TIMING_COUNT) {
        return NULL;
    }
    return &s_data_timing[index];
}

/* ========================================================================
 * 初始化
 * ======================================================================== */

esp_err_t mcp2518fd_init(void)
{
    if (s_spi_dev != NULL) {
        return ESP_OK;
    }

    s_spi_mutex = xSemaphoreCreateMutex();
    if (s_spi_mutex == NULL) {
        ESP_LOGE(TAG, "互斥锁创建失败");
        return ESP_ERR_NO_MEM;
    }

    esp_err_t err = hex_spi_bus_retain(can_spi_host());
    if (err != ESP_OK) {
        vSemaphoreDelete(s_spi_mutex); s_spi_mutex = NULL;
        return err;
    }
    s_bus_retained = true;

    spi_device_interface_config_t devcfg = {
        .clock_speed_hz = profile_spi_clock(true),   /* 10 MHz */
        .mode           = 0,                  /* CPOL=0, CPHA=0 */
        .spics_io_num   = profile_pin(SIG_CAN_CS),
        .queue_size     = 4,
    };

    err = spi_bus_add_device(can_spi_host(), &devcfg, &s_spi_dev);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "SPI 设备添加失败: 0x%x", err);
        hex_spi_bus_release(can_spi_host());
        s_bus_retained = false;
        vSemaphoreDelete(s_spi_mutex);
        s_spi_mutex = NULL;
        return err;
    }

    ESP_LOGI(TAG, "MCP2518FD SPI 初始化完成 (10MHz, Mode0)");
    return ESP_OK;
}

esp_err_t mcp2518fd_probe(void)
{
    esp_err_t err = mcp2518fd_reset();
    if (err == ESP_OK) {
        /* Match OPEN's reset settling period, plus one tick so a tick-edge
         * wakeup cannot shorten it below 20 ms on CONFIG_FREERTOS_HZ=100. */
        vTaskDelay(pdMS_TO_TICKS(20) + 1);
        err = mcp2518fd_osc_enable();
    }
    /* Exercise both MOSI writes and MISO readback. Reading the reset-default
     * CONFIG mode alone cannot detect a disconnected MOSI wire. */
    if (err == ESP_OK) err = mcp2518fd_opmode_select(MCP2518FD_MODE_INTERNAL_LOOP);
    if (err == ESP_OK) err = mcp2518fd_opmode_select(MCP2518FD_MODE_CONFIG);
    return err;
}

esp_err_t mcp2518fd_deinit(void)
{
    if (!s_spi_mutex) return ESP_OK;
    xSemaphoreTake(s_spi_mutex, portMAX_DELAY);
    esp_err_t err = s_spi_dev ? spi_bus_remove_device(s_spi_dev) : ESP_OK;
    if (err != ESP_OK) { xSemaphoreGive(s_spi_mutex); return err; }
    s_spi_dev = NULL;
    if (s_bus_retained) {
        err = hex_spi_bus_release(can_spi_host());
        if (err == ESP_OK) s_bus_retained = false;
    }
    xSemaphoreGive(s_spi_mutex);
    if (err == ESP_OK) { vSemaphoreDelete(s_spi_mutex); s_spi_mutex = NULL; }
    return err;
}

esp_err_t mcp2518fd_get_dev_id(uint8_t *dev_id)
{
    uint8_t d = 0;
    esp_err_t err = mcp2518fd_read_byte(MCP2518FD_REG_DEVID, &d);
    if (err == ESP_OK && dev_id) {
        *dev_id = d;
    }
    return err;
}
