#define DT_DRV_COMPAT zmk_behavior_key_loop

#include <zephyr/device.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/atomic.h>
#include <zephyr/logging/log.h>

#include <drivers/behavior.h>
#include <zmk/behavior.h>
#include <zmk/event_manager.h>
#include <zmk/events/keycode_state_changed.h>

LOG_MODULE_DECLARE(zmk, CONFIG_ZMK_LOG_LEVEL);

struct behavior_key_loop_config {
    uint32_t delay_ms;
};

struct behavior_key_loop_data {
    struct k_work_delayable work;
    atomic_t enabled;
    uint32_t keycode;
    uint32_t delay_ms;
    bool key_down;
};

static void key_loop_work_handler(struct k_work *work) {
    struct k_work_delayable *dwork = k_work_delayable_from_work(work);
    struct behavior_key_loop_data *data = CONTAINER_OF(dwork, struct behavior_key_loop_data, work);

    if (atomic_get(&data->enabled)) {
        data->key_down = !data->key_down;
        raise_zmk_keycode_state_changed_from_encoded(data->keycode, data->key_down,
                                                     k_uptime_get());
        k_work_reschedule(&data->work, K_MSEC(data->delay_ms));
    } else if (data->key_down) {
        data->key_down = false;
        raise_zmk_keycode_state_changed_from_encoded(data->keycode, false, k_uptime_get());
    }
}

static int behavior_key_loop_init(const struct device *dev) {
    const struct behavior_key_loop_config *cfg = dev->config;
    struct behavior_key_loop_data *data = dev->data;

    data->delay_ms = cfg->delay_ms;
    k_work_init_delayable(&data->work, key_loop_work_handler);
    return 0;
}

static int on_keymap_binding_pressed(struct zmk_behavior_binding *binding,
                                     struct zmk_behavior_binding_event event) {
    const struct device *dev = zmk_behavior_get_binding(binding->behavior_dev);
    struct behavior_key_loop_data *data = dev->data;

    if (atomic_get(&data->enabled)) {
        atomic_set(&data->enabled, 0);
    } else {
        data->keycode = binding->param1;
        atomic_set(&data->enabled, 1);
    }

    LOG_DBG("position %d keycode 0x%02X enabled %d", event.position, binding->param1,
            (int)atomic_get(&data->enabled));
    k_work_reschedule(&data->work, K_NO_WAIT);
    return ZMK_BEHAVIOR_OPAQUE;
}

static int on_keymap_binding_released(struct zmk_behavior_binding *binding,
                                      struct zmk_behavior_binding_event event) {
    return ZMK_BEHAVIOR_OPAQUE;
}

static const struct behavior_driver_api behavior_key_loop_driver_api = {
    .binding_pressed = on_keymap_binding_pressed,
    .binding_released = on_keymap_binding_released,
};

#define KEY_LOOP_INST(n)                                                                           \
    static struct behavior_key_loop_data behavior_key_loop_data_##n;                               \
    static const struct behavior_key_loop_config behavior_key_loop_config_##n = {                  \
        .delay_ms = DT_INST_PROP(n, delay_ms),                                                     \
    };                                                                                             \
    BEHAVIOR_DT_INST_DEFINE(n, behavior_key_loop_init, NULL, &behavior_key_loop_data_##n,          \
                            &behavior_key_loop_config_##n, POST_KERNEL,                            \
                            CONFIG_KERNEL_INIT_PRIORITY_DEFAULT, &behavior_key_loop_driver_api);

DT_INST_FOREACH_STATUS_OKAY(KEY_LOOP_INST)
