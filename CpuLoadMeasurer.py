# import math
# import numpy

from saleae.range_measurements import DigitalMeasurer

AVG_CPU_LOAD = 'cpu_load_avg'
MAX_CPU_LOAD = 'cpu_load_max'
MIN_CPU_LOAD = 'cpu_load_min'
MAX_TIMESTAMP = 'ts_max'
MIN_TIMESTAMP = 'ts_min'

CPU_LOAD_PERIOD = 1e-3

class CpuLoadMeasurer(DigitalMeasurer):
    supported_measurements = [AVG_CPU_LOAD, MAX_CPU_LOAD, MIN_CPU_LOAD, MAX_TIMESTAMP, MIN_TIMESTAMP]

    # Initialize your measurement extension here
    # Each measurement object will only be used once, so feel free to do all per-measurement initialization here
    def __init__(self, requested_measurements):
        super().__init__(requested_measurements)

        self.last_transition_time = None
        self.first_transition_time = None
        self.first_transition_type = None
        self.total_high_pulse_length = None
        self.total_low_pulse_length = None
        self.high_pulse_length = None
        self.low_pulse_length = None

        self.local_cpu_load_max = 0.0
        self.local_cpu_load_min = 100.0
        self.local_cpu_load_sum = 0.0
        self.local_cpu_load_num = 0.0
        self.max_ts = None
        self.min_ts = None
        self.td = 0.0

        self.partial_pulses = []

    # This method will be called one or more times per measurement with batches of data
    # data has the following interface
    #   * Iterate over to get transitions in the form of pairs of `Time`, Bitstate (`True` for high, `False` for low)
    # `Time` currently only allows taking a difference with another `Time`, to produce a `float` number of seconds
    def process_data(self, data):
        for t, bitstate in data:
            # Find the first transition type and time
            if self.first_transition_time == None:
                if bitstate:
                    self.first_transition_time = t
                    self.last_transition_time = t
                    self.first_transition_type = bitstate
                continue

            # Measure the length of the last pulse and save the current transition time for the next cycle
            if bitstate:
                self.low_pulse_length = t - self.last_transition_time
            else:
                self.high_pulse_length = t - self.last_transition_time
            self.last_transition_time = t

            # Measure sum of high and low pulses
            if bitstate == self.first_transition_type:
                # Check if our variable tallies are still valid, since we may be working on the next batch of data with variables reset
                self.partial_pulses.append([t, self.high_pulse_length, self.low_pulse_length])
                if ((self.total_high_pulse_length == None) and (self.total_low_pulse_length == None)):
                    self.total_high_pulse_length = self.high_pulse_length
                    self.total_low_pulse_length = self.low_pulse_length
                else:
                    # Now that entire period is complete, tally up the second pulse length
                    self.total_high_pulse_length += self.high_pulse_length

                    # Now that entire period is complete, tally up the first pulse length
                    self.total_low_pulse_length += self.low_pulse_length



                if float(t - self.first_transition_time) > CPU_LOAD_PERIOD:
                # Indexing starts from 1 because of trim the first sample after dt < CPU_LOAD_PERIOD
                    trim_idx = 0
                    partial_sum_high = 0.0
                    partial_sum_low = 0.0

                    for pulse_t, pulse_high, pulse_low in self.partial_pulses:
                        if float(t - pulse_t) > CPU_LOAD_PERIOD:
                            trim_idx += 1
                        else:
                            break

                    self.partial_pulses = self.partial_pulses[trim_idx:]
                    for pulse_t, pulse_high, pulse_low in self.partial_pulses:
                        partial_sum_high += float(pulse_high)
                        partial_sum_low += float(pulse_low)

                    # local_cpu_load = 100 * partial_sum_high / ((partial_sum_high + partial_sum_low) if partial_sum_high < CPU_LOAD_PERIOD else CPU_LOAD_PERIOD)
                    local_cpu_load = 100 * partial_sum_high / (partial_sum_high + partial_sum_low)
                    # local_cpu_load = 100 * partial_sum_high / CPU_LOAD_PERIOD
                    if self.local_cpu_load_max < local_cpu_load:
                        self.local_cpu_load_max = local_cpu_load
                        self.max_ts = t
                    if self.local_cpu_load_min > local_cpu_load:
                        self.local_cpu_load_min = local_cpu_load
                        self.min_ts = t
                    self.local_cpu_load_num += 1
                    self.local_cpu_load_sum += local_cpu_load



    # This method is called after all the relevant data has been passed to `process_data`
    # It returns a dictionary of the request_measurements values
    def measure(self):
        values = {}

        if AVG_CPU_LOAD in self.requested_measurements:
            # At least one full period is needed to calculate average CPU load
            if self.total_low_pulse_length is not None:
                # If first transition type was a rising edge (i.e. boolean TRUE), then the CPU load will be the
                # total first pulse type length divided by the total length of all complete periods combined
                values[AVG_CPU_LOAD] = 100 * (float(self.total_high_pulse_length) / float(self.total_high_pulse_length + self.total_low_pulse_length))

        if self.local_cpu_load_max != 0.0:
            if MAX_CPU_LOAD in self.requested_measurements:
                values[MAX_CPU_LOAD] = self.local_cpu_load_max
            if MAX_TIMESTAMP in self.requested_measurements:
                values[MAX_TIMESTAMP] = float(self.max_ts - self.first_transition_time)
        if self.local_cpu_load_min != 100.0:
            if MIN_CPU_LOAD in self.requested_measurements:
                values[MIN_CPU_LOAD] = self.local_cpu_load_min
            if MIN_TIMESTAMP in self.requested_measurements:
                values[MIN_TIMESTAMP] = float(self.min_ts - self.first_transition_time)

        return values
