from dataclasses import dataclass
import math
import numpy as np


@dataclass(frozen=True)
class TimingExchange:
    """One four-timestamp timing exchange between master and DAQ node.

    t1/t4 are master/reference-domain timestamps. t2/t3 are node-local
    timestamps. The exchange model itself records the simulated forward and
    reverse path delays so validation can compare estimates against truth.
    """

    t1_master_ns: int
    t2_node_ns: int
    t3_node_ns: int
    t4_master_ns: int
    forward_delay_ns: int
    reverse_delay_ns: int

    @property
    def round_trip_ns(self):
        return self.t4_master_ns - self.t1_master_ns

    @property
    def path_asymmetry_ns(self):
        return self.forward_delay_ns - self.reverse_delay_ns


@dataclass(frozen=True)
class ExchangeEstimate:
    """Offset/delay estimate under the conventional symmetric-path assumption."""

    offset_ns: float
    mean_path_delay_ns: float
    round_trip_ns: int


def estimate_exchange(exchange):
    """Estimate node-master offset and one-way delay from a four-timestamp exchange.

    The equations assume forward and reverse propagation delays are equal. If
    the physical/simulated paths are asymmetric, half of that asymmetry biases
    the offset estimate; TIMING-003 deliberately exposes that limitation.
    """
    if not isinstance(exchange, TimingExchange):
        raise TypeError("exchange must be a TimingExchange")
    if exchange.t4_master_ns < exchange.t1_master_ns:
        raise ValueError("master timestamps must preserve exchange order")
    if exchange.t3_node_ns < exchange.t2_node_ns:
        raise ValueError("node timestamps must preserve exchange order")

    offset = ((exchange.t2_node_ns - exchange.t1_master_ns)
              + (exchange.t3_node_ns - exchange.t4_master_ns)) / 2.0
    delay = ((exchange.t2_node_ns - exchange.t1_master_ns)
             - (exchange.t3_node_ns - exchange.t4_master_ns)) / 2.0
    return ExchangeEstimate(float(offset), float(delay), exchange.round_trip_ns)


class NetworkDelayModel:
    """Seeded forward/reverse propagation-delay model for timing messages."""

    def __init__(self, forward_delay_ns=50_000, reverse_delay_ns=None,
                 jitter_std_ns=0.0, seed=0):
        if reverse_delay_ns is None:
            reverse_delay_ns = forward_delay_ns
        for name, value in (("forward_delay_ns", forward_delay_ns),
                            ("reverse_delay_ns", reverse_delay_ns)):
            if type(value) is not int or value < 0:
                raise ValueError(f"{name} must be a nonnegative integer")
        if (not isinstance(jitter_std_ns, (int, float))
                or not math.isfinite(jitter_std_ns) or jitter_std_ns < 0):
            raise ValueError("jitter_std_ns must be finite and nonnegative")
        if seed is not None and type(seed) is not int:
            raise ValueError("seed must be an integer or None")
        self.forward_delay_ns = forward_delay_ns
        self.reverse_delay_ns = reverse_delay_ns
        self.jitter_std_ns = float(jitter_std_ns)
        self.seed = seed
        self._rng = np.random.default_rng(seed)

    def reset(self):
        self._rng = np.random.default_rng(self.seed)

    def sample(self):
        if self.jitter_std_ns:
            jf, jr = np.rint(self._rng.normal(0.0, self.jitter_std_ns, 2)).astype(np.int64)
        else:
            jf = jr = 0
        forward = self.forward_delay_ns + int(jf)
        reverse = self.reverse_delay_ns + int(jr)
        # Physical propagation delay cannot be negative; clip rare Gaussian tails.
        return max(0, forward), max(0, reverse)


def simulate_exchange(master_send_ns, node_clock, network,
                      node_processing_ns=0):
    """Simulate one timing request/response exchange.

    ``master_send_ns`` and path delays live in ideal/reference time. Node
    receive/send timestamps are readings of ``node_clock`` at the corresponding
    reference instants. ``node_processing_ns`` is reference-domain residence
    time between receive and reply.
    """
    if type(master_send_ns) is not int or master_send_ns < 0:
        raise ValueError("master_send_ns must be a nonnegative integer")
    if type(node_processing_ns) is not int or node_processing_ns < 0:
        raise ValueError("node_processing_ns must be a nonnegative integer")
    if not hasattr(node_clock, "read"):
        raise TypeError("node_clock must provide read(reference_ns)")
    if not isinstance(network, NetworkDelayModel):
        raise TypeError("network must be a NetworkDelayModel")

    forward, reverse = network.sample()
    node_receive_ref = master_send_ns + forward
    node_send_ref = node_receive_ref + node_processing_ns
    master_receive = node_send_ref + reverse

    return TimingExchange(
        t1_master_ns=master_send_ns,
        t2_node_ns=node_clock.read(node_receive_ref),
        t3_node_ns=node_clock.read(node_send_ref),
        t4_master_ns=master_receive,
        forward_delay_ns=forward,
        reverse_delay_ns=reverse,
    )


def exchange_observation(exchange):
    """Return a representative master/local pair for affine clock fitting.

    Midpoints reduce each four-timestamp exchange to one paired observation.
    Under symmetric paths this removes fixed propagation delay. Asymmetry leaves
    the documented half-asymmetry bias.
    """
    estimate = estimate_exchange(exchange)
    master_mid = (exchange.t1_master_ns + exchange.t4_master_ns) // 2
    node_mid = int(round(master_mid + estimate.offset_ns))
    return master_mid, node_mid
