idf_component_register(
    SRCS
        "main.c"
        "protocol/ubcp_frame.c"
        "core/msg_bus.c"
        "core/device_profile.c"
        "core/spi_bus_manager.c"
        "core/topology.c"
        "transport/mcp_transport.c"
        "dap/dap_engine.c"
        "dap/swd_gpio.c"
        "dap/dap_server.c"
        "dap/dap_stream.c"
        "modules/mod_system.c"
        "modules/mod_uart.c"
        "modules/mod_network.c"
        "modules/mod_tcp.c"
        "modules/mod_udp.c"
        "modules/mod_ws.c"
        "modules/mod_can.c"
        "modules/mod_spi.c"
        "modules/mod_i2c.c"
        "modules/mod_gpio.c"
        "modules/mcp2518fd.c"
    INCLUDE_DIRS
        "."
    PRIV_REQUIRES
        driver
        esp_driver_gpio
        esp_driver_uart
        esp_driver_i2c
        esp_driver_spi
        esp_timer
        esp_rom
        esp_hw_support
        lwip
        esp_netif
        esp_wifi
        esp_event
        nvs_flash
        spi_flash
        esp_psram
)

# ESP-IDF reads the repository's version.txt into PROJECT_VER.
idf_build_get_property(hex_version PROJECT_VER)
if(NOT hex_version MATCHES "^(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)$")
    message(FATAL_ERROR "HEX-Bridge version must have three numeric components")
endif()
set(hex_version_parts ${CMAKE_MATCH_1} ${CMAKE_MATCH_2} ${CMAKE_MATCH_3})
foreach(part IN LISTS hex_version_parts)
    if(part GREATER 255)
        message(FATAL_ERROR "GET_INFO version components must fit in one byte")
    endif()
endforeach()
target_compile_definitions(${COMPONENT_LIB} PRIVATE
    HEX_FW_VERSION_MAJOR=${CMAKE_MATCH_1}
    HEX_FW_VERSION_MINOR=${CMAKE_MATCH_2}
    HEX_FW_VERSION_PATCH=${CMAKE_MATCH_3})
