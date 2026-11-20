#pragma once
#include "esp_err.h"

/* Start once after mod_network initialization. The task follows network readiness
 * and generation changes independently of the UBCP controller on TCP 9500. */
esp_err_t dap_server_start(void);
