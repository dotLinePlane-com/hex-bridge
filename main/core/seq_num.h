/**
 * @file seq_num.h
 * @brief 设备端事件序列号管理器
 *
 * 为设备主动上报的事件帧分配递增的序列号。
 * 使用原子操作保证多任务安全。
 * 序列号范围：0x0001-0xFFFE（0x0000 无效，0xFFFF 广播）
 */

#pragma once

#include <stdint.h>
#include <stdatomic.h>

static _Atomic uint16_t s_event_seq_num = 1;

/**
 * @brief 获取下一个事件序列号（线程安全）
 * @return 序列号 (0x0001-0xFFFE)
 */
static inline uint16_t seq_num_next(void)
{
    uint16_t seq = atomic_fetch_add(&s_event_seq_num, 1);
    /* 跳过 0x0000 和 0xFFFF */
    if (seq == 0x0000) {
        seq = atomic_fetch_add(&s_event_seq_num, 1);
    }
    if (seq == 0xFFFF) {
        /* 回绕到 1 */
        atomic_store(&s_event_seq_num, 1);
        seq = atomic_fetch_add(&s_event_seq_num, 1);
    }
    return seq;
}
