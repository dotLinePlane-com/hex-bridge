"""Compile the real command engine against GPIO/time mocks (no ESP32 needed).

Usage: python main/dap/test_dap_engine_host.py <native-C-compiler> [compiler args]
For Zig, pass zig.exe cc. Temporary headers/executable stay outside the project.
"""
import os
from pathlib import Path
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
HEADERS = {
    "esp_timer.h": "#include <stdint.h>\nint64_t esp_timer_get_time(void);\n",
    "esp_rom_sys.h": "void esp_rom_delay_us(unsigned);\n",
    "esp_mac.h": "#include <stdint.h>\n#define ESP_MAC_WIFI_STA 0\nint esp_read_mac(uint8_t *,int);\n",
    "freertos/FreeRTOS.h": "#pragma once\n",
    "freertos/task.h": "void vTaskDelay(unsigned);\n",
}
HARNESS = r'''
#include "dap_engine.h"
#include "swd_gpio.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static int64_t now;
static unsigned reads[40000], rd, nr, writes[40000], nw, releases;
static uint8_t q[1024], out[1024];
int64_t esp_timer_get_time(void) { return now; }
void esp_rom_delay_us(unsigned us) { now += us; }
void vTaskDelay(unsigned n) { now += n * 1000; }
int esp_read_mac(uint8_t *p,int unused) { (void)unused; memset(p, 0x12, 6); return 0; }
bool swd_gpio_connect(void) { return true; }
void swd_gpio_release(void) { releases++; }
bool swd_gpio_clock(uint32_t hz) { return hz >= 10000; }
void swd_gpio_drive(bool output) { (void)output; }
void swd_gpio_write_bit(unsigned bit) { now += 10; assert(nw < 40000); writes[nw++] = bit; }
unsigned swd_gpio_read_bit(void) { now += 10; assert(rd < nr); return reads[rd++]; }
void swd_gpio_cycle(void) { now += 10; }
uint8_t swd_gpio_pins(uint8_t v,uint8_t s) { (void)v; (void)s; return 0x83; }
bool swd_gpio_has_reset(void) { return false; }
static void reset_mock(void) { rd = nr = nw = 0; now = 0; }
static void bits(uint32_t v,unsigned n) { while(n--) { assert(nr < 40000); reads[nr++] = v & 1; v >>= 1; } }
static unsigned parity(uint32_t v) { unsigned p=0; while(v) { p ^= v & 1; v >>= 1; } return p; }
static void read_ok(uint32_t v) { bits(1,3); bits(v,32); bits(parity(v),1); }
static uint32_t get32(const uint8_t *p) { return p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24); }
static void header(unsigned offset,uint8_t req) {
  unsigned want[8] = {1, req&1, (req>>1)&1, (req>>2)&1, (req>>3)&1, parity(req&15),0,1};
  for(unsigned i=0;i<8;i++) assert(writes[offset+i]==want[i]);
}
int main(void) {
  uint8_t info_caps[]={0,0xf0}, info_size[]={0,0xff}, connect[]={2,1};
  assert(dap_execute(info_caps,2,out,sizeof out)==3 && out[2]==1);
  assert(dap_execute(info_size,2,out,sizeof out)==4 && out[2]==0 && out[3]==4);
  assert(dap_execute(connect,2,out,sizeof out)==2 && out[1]==1);
  uint8_t bad1[]={5,0,1,2},bad2[]={6,0,1,0,0},bad3[]={0x12,0},bad4[]={0x1d,1,0};
  const uint8_t *bad[]={bad1,bad2,bad3,bad4};size_t sizes[]={3,5,2,3};
  for(unsigned i=0;i<4;i++) { reset_mock(); assert(dap_execute(bad[i],sizes[i],out,sizeof out)==1 && out[0]==255);assert(nw==0); }
  uint8_t unknown[]={0x7f,0};assert(dap_execute(unknown,2,out,sizeof out)==1 && out[0]==255);
  reset_mock(); assert(dap_execute(bad1,sizeof bad1,out,2)==0 && nw==0);
  assert(dap_execute(q,0,out,sizeof out)==0);
  reset_mock(); read_ok(0x2ba01477);
  assert(dap_execute(bad1,sizeof bad1,out,sizeof out)==7 && out[1]==1 && out[2]==1 && get32(out+3)==0x2ba01477); header(0,2); assert(rd==nr);
  reset_mock(); read_ok(0xdeadbeef);read_ok(0x12345678);bad1[3]=3;
  assert(dap_execute(bad1,sizeof bad1,out,sizeof out)==7 && get32(out+3)==0x12345678);header(0,3);header(8,14);
  reset_mock(); bits(2,3);read_ok(42);bad1[3]=2;
  assert(dap_execute(bad1,sizeof bad1,out,sizeof out)==7 && out[2]==1 && get32(out+3)==42);
  reset_mock(); bits(4,3);
  assert(dap_execute(bad1,sizeof bad1,out,sizeof out)==3 && out[1]==0 && out[2]==4);
  reset_mock();read_ok(42);reads[nr-1]^=1;
  assert(dap_execute(bad1,sizeof bad1,out,sizeof out)==3 && out[2]==8);
  reset_mock();uint8_t write[]={5,0,1,0,0x78,0x56,0x34,0x12};bits(1,3);read_ok(0);
  assert(dap_execute(write,sizeof write,out,sizeof out)==3 && out[1]==1 && out[2]==1);header(0,0);header(41,14);
  for(unsigned i=0;i<32;i++) assert(writes[8+i]==((0x12345678U>>i)&1));assert(writes[40]==parity(0x12345678));
  reset_mock();uint8_t match[]={5,0,2,0x20,0xff,0,0,0,0x12,0x78,0,0,0};read_ok(0x12345678);
  assert(dap_execute(match,sizeof match,out,sizeof out)==3 && out[1]==2 && out[2]==1);
  reset_mock();read_ok(0x12345679);
  assert(dap_execute(match,sizeof match,out,sizeof out)==3 && out[1]==1 && out[2]==17);
  reset_mock();uint8_t block[]={6,0,255,0,2};for(unsigned i=0;i<255;i++) read_ok(0xab000000U+i);
  assert(dap_execute(block,sizeof block,out,sizeof out)==1024 && out[1]==255 && out[2]==0 && out[3]==1);
  assert(get32(out+4)==0xab000000U && get32(out+1020)==0xab0000feU && rd==nr && now>100000);
  reset_mock();block[4]=3;
  for(unsigned i=0;i<255;i++) { read_ok(0xdeadbeef);read_ok(0xcd000000U+i); }
  assert(dap_execute(block,sizeof block,out,sizeof out)==1024 && out[1]==255 && out[3]==1);
  assert(get32(out+4)==0xcd000000U && get32(out+1020)==0xcd0000feU && rd==nr && now>250000);
  header(0,3);header(8,14);header(16,3);header(24,14);
  reset_mock();uint8_t cfg[]={4,0,0xff,0xff,0,0};dap_execute(cfg,sizeof cfg,out,sizeof out);
  for(unsigned i=0;i<3000;i++) bits(2,3);
  assert(dap_execute(bad1,sizeof bad1,out,sizeof out)==3 && out[2]==2 && now<110000);
  uint8_t disconnect[]={3};unsigned before=releases;
  assert(dap_execute(disconnect,1,out,sizeof out)==2 && releases==before+1);
  reset_mock();assert(dap_execute(bad1,sizeof bad1,out,sizeof out)==3 && out[2]==8 && nw==0);
  /* Deterministic malformed packet/capacity fuzz while target is disconnected. */
  uint32_t random=0x12345678;uint8_t cmds[]={5,6,0x12,0x1d};
  for(unsigned i=0;i<5000;i++) {
    random=random*1664525U+1013904223U;size_t len=(random%1024)+1;
    for(size_t j=0;j<len;j++) { random=random*1664525U+1013904223U;q[j]=random>>24; }
    q[0]=cmds[i%4];size_t cap=(random>>16)%1025;
    assert(dap_execute(q,len,out,cap)<=cap);assert(nw==0);
  }
  puts("DAP engine host mock regressions: PASS");return 0;
}
'''

def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    with tempfile.TemporaryDirectory(prefix="hex_dap_host_") as tmp:
        root = Path(tmp)
        for name, content in HEADERS.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        harness = root / "test.c"
        harness.write_text(HARNESS)
        exe = root / ("dap_test.exe" if os.name == "nt" else "dap_test")
        subprocess.run([*sys.argv[1:], "-std=c11", "-Wall", "-Wextra", "-Werror",
                        "-I" + str(root), "-I" + str(HERE), str(HERE / "dap_engine.c"),
                        str(harness), "-o", str(exe)], check=True)
        subprocess.run([str(exe)], check=True)

if __name__ == "__main__":
    main()
