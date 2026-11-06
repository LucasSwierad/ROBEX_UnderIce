import numpy as np

SECONDS_PER_MONTH = 30 * 86400  #this converts the datasheets aging spec from per month to per second
SOUND_SPEED = 1500.0  #m/s, the speed of sound in water, used to convert time error to range error

class SA65Clock:
    def __init__(self, seed=None, y0=None, aging_per_month=None,
                 adev_1s=3e-10, sync_sigma=1e-7, temp_coeff=5e-12, temp_ref=25.0):
        # Fixed settings 
        self.rng = np.random.default_rng(seed)  #seed starts the random number generatopr so the same seed gives the same clock
        self.y0 = self.rng.uniform(-5e-11, 5e-11) if y0 is None else y0 #Starting frequency error (how fast the clock runs), 
                                #if we don't set it its drawn at random from a uniform distribution between -5e-11 and 5e-11, which is the datasheet spec for initial frequency error

        if aging_per_month is None:
            aging_per_month = self.rng.uniform(-9e-10, 9e-10)       #how much the frequency error changes per month.
        self.aging = aging_per_month / SECONDS_PER_MONTH        #Convert aging rate to per second
        self.adev_1s = adev_1s             #Noise level set by the datasheets allan deviation of 3e-10 at 1s
        self.sync_sigma = sync_sigma        #Typical leftover error after a sync, set by the datasheet spec of 100ns
        self.temp_coeff = temp_coeff        #Frequency change per *C
        self.temp_ref = temp_ref            #The temperature with no temperature error

        self.x = 0.0  # Clock time error (seconds) - how far off the clock is from true time (positive means fast)
        self.elapsed = 0.0  #Seconds simulated so far, used to calculate aging and temperature error


    def step(self, dt, temp_c=None):
        """Simulate the clock for dt seconds, returning the new time error x. The temperature can be set to a constant value, or left as None to use the reference temperature."""

        #y is the total frequency error, from the starting offset, aging, and temperature. dt/2 uses the aging at the middle of the step which keeps large juumps accurate
        temp_c = self.temp_ref if temp_c is None else temp_c
        y = (self.y0 + self.aging * (self.elapsed + dt / 2)
             + self.temp_coeff * (temp_c - self.temp_ref))

        #y*dt is the predictable drift, and the last term is random noise. The noise scales with sqrt(dt) because random errors add up like a random walk. 
        # This also makes the allen deviation fall as 1/sqrt(tau)
        self.x += y * dt + self.adev_1s * np.sqrt(dt) * self.rng.standard_normal()
        self.elapsed += dt
        return self.x

    def sync(self):
        """Sets x to a small random value like the real !S command. It corrects the time but not the frequency so the clock will continue to drift."""
        self.x = self.rng.normal(0.0, self.sync_sigma)

    def power_cycle(self):
        """Shifts y0 by up to +-5e-10, the datasheets retrace specification."""
        self.y0 += self.rng.uniform(-5e-10, 5e-10)

    def read(self, true_time):
        """What this clock shows at a given true time."""
        return true_time + self.x

def measured_range(true_range, tx_clock_error, rx_clock_error, c=SOUND_SPEED):
    """Range an OWTT receiver computes: arrival stamp minus send stamp, times sound speed."""
    return c * (true_range / c + rx_clock_error - tx_clock_error)


def adev(x, tau0, m):
    """Overlapping Allan deviation of time error x at averaging time m*tau0.
    Tau0 is the time between samples, and m is how many samples make up the average time. Its the same calculation wed run on real drift tests"""
    d = x[2 * m:] - 2 * x[m:-m] + x[:-2 * m]
    return np.sqrt(np.mean(d ** 2) / (2 * (m * tau0) ** 2))


def self_check():
    """Compare the model with the data sheet."""
    clock = SA65Clock(seed=1, y0=0.0, aging_per_month=0.0)
    x = np.array([clock.step(1.0) for _ in range(400_000)])
    print("Allan deviation, model vs data sheet")
    for tau, spec in [(1, 3e-10), (10, 1e-10), (100, 3e-11), (1000, 1e-11)]:
        print(f"  tau={tau:>4} s   {adev(x, 1.0, tau):.2e}   spec {spec:.0e}")

    print("\nRange error between two clocks after sync, 1000 random pairs")
    print("  hours   median (m)   95th percentile (m)")
    for hours in (1, 6, 12, 24, 48):
        errors = []
        for seed in range(1000):
            a, b = SA65Clock(seed=2 * seed), SA65Clock(seed=2 * seed + 1)
            a.sync(), b.sync()
            a.step(hours * 3600), b.step(hours * 3600)
            errors.append(abs(measured_range(0.0, a.x, b.x)))
        print(f"  {hours:>5}   {np.median(errors):>10.4f}   {np.percentile(errors, 95):>19.4f}")


if __name__ == "__main__":
    self_check()