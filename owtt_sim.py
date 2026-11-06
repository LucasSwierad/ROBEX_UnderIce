import argparse
import holoocean

from csac_clock import SOUND_SPEED, SA65Clock

TICKS_PER_SEC = 1000
SEND_EVERY_TICKS = 2 *TICKS_PER_SEC
SEPARATION = 100.0

def agent(name, beacon_id, y):
    return {
        "agent_name": name,
        "agent_type": "HoveringAUV",
        "sensors": [{
            "sensor_type": "AcousticBeaconSensor",
            "location": [0, 0, 0],
            "configuration": { "id": beacon_id},
        }],
        "control_scheme": 0,
        "location": [0, y, -5],
    }

SCENARIO = {
    "name": "owtt_sa65",
    "world": "SimpleUnderwater",
    "package_name": "Ocean",
    "main_agent": "auv0",
    "ticks_per_sec": TICKS_PER_SEC,
    "agents": [agent("auv0", 0, 0), agent("auv1", 1, SEPARATION)],
}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--hours", type=float, default=0.0, help="hours since the clocks were synced")
    parser.add_argument("--temp", type=float, default=25, help="clock temperature in C")
    parser.add_argument("--seconds", type=float, default=20.0, help="simulated seconds to run")
    parser.add_argument("--seed", type=int, default=0, help="random seed for clock simulation")
    args = parser.parse_args()

    tx_clock = SA65Clock(seed=args.seed)
    rx_clock = SA65Clock(seed=args.seed + 1)
    tx_clock.sync()
    rx_clock.sync()
    tx_clock.step(args.hours * 3600, args.temp)
    rx_clock.step(args.hours * 3600, args.temp)

    dt = 1.0/TICKS_PER_SEC
    print(f"Clock error, receiver minus sender, after {args.hours} hours: {(rx_clock.x - tx_clock.x) * 1e6:+.3f} us")
    print(f" send time (s)    true range (m)    OWTT range (m)    clock error (mm)")

    with holoocean.make(scenario_cfg=SCENARIO) as env:
        env.reset()
        for tick in range(int(args.seconds * TICKS_PER_SEC)):
            true_time = tick * dt
            tx_clock.step(dt, args.temp)
            rx_clock.step(dt, args.temp)

            if tick % SEND_EVERY_TICKS == 0:
                # The payload is the send time as shown by the sender's clock, as on a real modem.
                # MSG_RESPU is used because it is the one-way message that reports the range r.
                env.send_acoustic_message(0, 1, "MSG_RESPU", (true_time, tx_clock.read(true_time)))

            state = env.tick()
            received = state["auv1"].get("AcousticBeaconSensor")
            if received is None:
                continue

            (send_time, tx_stamp), _, _, true_range = received[2], received[3], received[4], float(received[5])
            # HoloOcean delivers messages on a tick, about 5 ms or 7.5 m apart at 200 ticks per
            # second, which would swamp the clock error. The arrival time therefore comes from r.
            rx_stamp = rx_clock.read(send_time + true_range / SOUND_SPEED)
            owtt_range = SOUND_SPEED * (rx_stamp - tx_stamp)
            error_mm = (owtt_range - true_range) * 1000
            print(f"  {send_time:>13.2f}   {true_range:>14.4f}   {owtt_range:>14.4f}   {error_mm:>10.3f}")


if __name__ == "__main__":
    main()
