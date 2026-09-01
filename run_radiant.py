"""Run a reproducible 8-channel, 0.2-second simulated acquisition."""
import numpy as np
from radiant.acquisition import AcquisitionEngine


def main():
    engine = AcquisitionEngine()
    for chunk in range(2):
        indices = np.arange(chunk * 5000, (chunk + 1) * 5000)
        amplitudes = np.linspace(1.0, 4.5, 8)
        signals = np.sin(2 * np.pi * 1000 * indices[:, None] / 50_000) * amplitudes
        packet = engine.acquire(signals)
        print(f"sequence={packet.sequence} shape={packet.data.codes.shape} "
              f"first_sample={packet.first_sample} "
              f"start_ns={packet.timestamps_ns[0]} "
              f"clipped={np.count_nonzero(packet.data.clipped)}")
    print(f"ADC LSB: {engine.adc.lsb * 1000:.8f} mV")
    print("Simulation only; no host deadline or hardware timing claim.")


if __name__ == "__main__":
    main()
