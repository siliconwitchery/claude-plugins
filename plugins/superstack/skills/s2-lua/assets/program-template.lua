-- S2 Module program template
-- Canonical shape: config constants → setup → handlers → main loop with sleep.
-- Code restarts from the top on every push/save/reboot.

-- 1. Config constants — tune here, then re-push (there is no remote config)
local SEND_INTERVAL_S = 600 -- seconds between sends (device.sleep uses seconds)
local SENSOR_PORT = "PORTA" -- Qwiic sensor on a 4-pin port (A/B/E/F only)

-- 2. One-time setup
device.power.set_vout(3.3) -- ports boot at 1.8 V; raise to 3.3 V before sensor use

-- Wait for a valid wall-clock time before timestamping anything.
-- time.get_unix_time() returns MILLISECONDS, and uptime until first sync.
local TIME_VALID_THRESHOLD = 1704067200000 -- 2024-01-01 in unix ms
while time.get_unix_time() < TIME_VALID_THRESHOLD do
    device.sleep(1)
end

-- 3. Optional event handlers
-- device.digital.assign_input_event("A0", function(pin, state)
--     print(pin .. " changed to " .. tostring(state))
-- end, { pull = "PULL_UP" })

-- Example sensor read: wrap bus transactions and check success
local function read_sensor()
    local result = device.i2c.write_read(0x76, "\xD0", 1, { port = SENSOR_PORT })

    if not result.success then
        print("sensor not responding")
        return nil
    end

    return result.value
end

-- 4. Main loop — always sleep, never busy-wait
while true do
    local ok, err = pcall(function()
        local value = read_sensor()

        if value ~= nil and network.connected() then
            -- Descriptive snake_case keys with units: the Superstack AI agent
            -- infers the data schema from these names.
            network.send_data{
                sensor_raw_value = value,
                battery_voltage = device.power.battery.get_voltage(),
            }
        end
    end)

    if not ok then
        print("error: " .. tostring(err))
    end

    device.sleep(SEND_INTERVAL_S)
end
